import re

from django.conf import settings
from django.db import models
from django.utils.functional import cached_property
from django.utils import timezone
from pgvector.django import CosineDistance, VectorField

from common.mixins import BaseModel


def _parse_year_month(date_str: str, default_month: int) -> tuple[int, int] | None:
    """Parse strings like YYYY-MM, YYYY.MM, YYYY/MM, or YYYY."""
    if not date_str or not isinstance(date_str, str):
        return None

    match = re.search(r"(?P<year>\d{4})(?:\D+(?P<month>\d{1,2}))?", date_str.strip())
    if not match:
        return None

    year = int(match.group("year"))
    month = match.group("month")
    parsed_month = default_month if month is None else int(month)

    if not 1 <= parsed_month <= 12:
        return None

    return year, parsed_month


def _month_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def _year_month_from_month_index(month_index: int) -> tuple[int, int]:
    year, month_offset = divmod(month_index, 12)
    return year, month_offset + 1


def _format_duration_months(total_months: int | None) -> str:
    if total_months is None or total_months <= 0:
        return ""

    years, months = divmod(total_months, 12)
    if years and months:
        return f"{years}년 {months}개월"
    if years:
        return f"{years}년"
    return f"{months}개월"


def _format_reference_date(date_str: str) -> str:
    if not date_str or not isinstance(date_str, str):
        return ""

    stripped = date_str.strip()
    if re.fullmatch(r"\d{4}", stripped):
        return f"{stripped}년"

    parsed = _parse_year_month(stripped, default_month=12)
    if parsed is None:
        return stripped

    year, month = parsed
    return f"{year}.{month:02d}"


def _format_reference_year_month(value: tuple[int, int] | None) -> str:
    if value is None:
        return ""
    year, month = value
    return f"{year}.{month:02d}"


def _format_year_month(value: tuple[int, int] | None) -> str:
    if value is None:
        return ""
    year, month = value
    return f"{year}-{month:02d}"


def _parse_duration_months(value: str) -> int | None:
    if not value or not isinstance(value, str):
        return None

    duration_matches = list(
        re.finditer(
            r"(?:(?P<years>\d+)\s*년\s*(?P<months>\d+)\s*개월)"
            r"|(?:(?P<years_only>\d+)\s*년)"
            r"|(?:(?P<months_only>\d+)\s*개월)",
            value,
        )
    )
    if not duration_matches:
        return None

    match = duration_matches[0]
    years = int(match.group("years") or match.group("years_only") or 0)
    months = int(match.group("months") or match.group("months_only") or 0)
    total_months = years * 12 + months
    return total_months or None


def _format_reference_date_long(date_str: str) -> str:
    if not date_str or not isinstance(date_str, str):
        return ""

    stripped = date_str.strip()
    if re.fullmatch(r"\d{4}", stripped):
        return f"{stripped}년"

    parsed = _parse_year_month(stripped, default_month=12)
    if parsed is None:
        return stripped

    year, month = parsed
    return f"{year}년 {month}월"


def _format_reference_date_short(date_str: str) -> str:
    if not date_str or not isinstance(date_str, str):
        return ""

    stripped = date_str.strip()
    if re.fullmatch(r"\d{4}", stripped):
        return stripped

    parsed = _parse_year_month(stripped, default_month=12)
    if parsed is None:
        return stripped

    year, month = parsed
    return f"{year}.{month}"


def _severity_label(severity: str) -> str:
    return {
        "RED": "중요",
        "YELLOW": "주의",
        "BLUE": "참고",
    }.get(severity, "참고")


def _severity_sort_key(severity: str) -> int:
    return {"RED": 0, "YELLOW": 1, "BLUE": 2}.get(severity, 99)


class Category(BaseModel):
    """직무 카테고리 (e.g. HR, Finance, Sales)."""

    name = models.CharField(max_length=100, unique=True)
    name_ko = models.CharField(max_length=100, blank=True)
    candidate_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "categories"
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return f"{self.name} ({self.name_ko})" if self.name_ko else self.name


class Candidate(BaseModel):
    """후보자 (헤드헌팅 대상)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "활동중"
        PLACED = "placed", "배치완료"
        INACTIVE = "inactive", "비활성"

    class Source(models.TextChoices):
        DRIVE_IMPORT = "drive_import", "드라이브 임포트"
        MANUAL = "manual", "직접 입력"
        REFERRAL = "referral", "추천"

    class ValidationStatus(models.TextChoices):
        AUTO_CONFIRMED = "auto_confirmed", "자동 확인"
        NEEDS_REVIEW = "needs_review", "검토 필요"
        CONFIRMED = "confirmed", "확인 완료"
        FAILED = "failed", "실패"

    class RecommendationStatus(models.TextChoices):
        PENDING = "pending", "미결정"
        RECOMMENDED = "recommended", "추천"
        NOT_RECOMMENDED = "not_recommended", "비추천"
        ON_HOLD = "on_hold", "보류"

    class ResumeReferenceDateSource(models.TextChoices):
        DOCUMENT_TEXT = "document_text", "문서 표기"
        FILE_MODIFIED_TIME = "file_modified_time", "파일 수정일"
        INFERRED = "inferred", "추정"

    # Basic info
    name = models.CharField(max_length=100)
    name_en = models.CharField(max_length=200, blank=True)
    birth_year = models.SmallIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=10, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=255, blank=True)
    phone_normalized = models.CharField(max_length=20, blank=True, db_index=True)
    address = models.CharField(max_length=500, blank=True)

    # Current representative resume
    current_resume = models.ForeignKey(
        "candidates.Resume",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="current_for_candidate",
    )

    # Categories
    categories = models.ManyToManyField(
        Category,
        blank=True,
        related_name="candidates",
    )
    primary_category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_candidates",
    )

    # Professional info
    total_experience_years = models.SmallIntegerField(null=True, blank=True)
    resume_reference_date = models.CharField(max_length=255, blank=True)
    resume_reference_date_source = models.CharField(
        max_length=30,
        choices=ResumeReferenceDateSource.choices,
        blank=True,
    )
    resume_reference_date_evidence = models.TextField(blank=True)
    current_company = models.CharField(max_length=255, blank=True)
    current_position = models.CharField(max_length=255, blank=True)
    current_salary = models.IntegerField(null=True, blank=True, help_text="만원")
    desired_salary = models.IntegerField(null=True, blank=True, help_text="만원")
    core_competencies = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True)

    # Status
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    source = models.CharField(
        max_length=15,
        choices=Source.choices,
        default=Source.MANUAL,
    )

    # Detail fields (JSONField for low-count data from raw_extracted_json)
    salary_detail = models.JSONField(
        default=dict,
        blank=True,
        help_text="Normalized salary info: {current: {base, bonus, incentive, benefits, total}, desired: {amount, note}}",
    )
    military_service = models.JSONField(
        default=dict,
        blank=True,
        help_text="{branch, rank, start_date, end_date, status, unit, note}",
    )
    self_introduction = models.TextField(blank=True)
    family_info = models.JSONField(
        default=dict,
        blank=True,
        help_text="{marital_status, spouse_age, children_count, children_detail, note}",
    )
    overseas_experience = models.JSONField(
        default=list,
        blank=True,
        help_text="[{country, purpose, start_date, end_date, duration, type}]",
    )
    awards = models.JSONField(
        default=list,
        blank=True,
        help_text="[{name, issuer, date, project}]",
    )
    patents = models.JSONField(
        default=list,
        blank=True,
        help_text="[{title, type, country, date, number}]",
    )
    projects = models.JSONField(
        default=list,
        blank=True,
        help_text="[{name, role, description, start_date, end_date, budget}]",
    )
    trainings = models.JSONField(
        default=list,
        blank=True,
        help_text="[{name, institution, date, duration}]",
    )

    # 4대 카테고리 기술 스택 + etc 필드
    skills = models.JSONField(
        default=list,
        blank=True,
        help_text='["Python", "Oracle", "SAP", ...]',
    )
    personal_etc = models.JSONField(
        default=list,
        blank=True,
        help_text="[{type, description}]",
    )
    education_etc = models.JSONField(
        default=list,
        blank=True,
        help_text="[{type, title, institution, date, description}]",
    )
    career_etc = models.JSONField(
        default=list,
        blank=True,
        help_text="[{type, name, company, role, start_date, end_date, technologies[], description}]",
    )
    skills_etc = models.JSONField(
        default=list,
        blank=True,
        help_text="[{type, title, description, date}]",
    )

    # AI extraction metadata
    raw_text = models.TextField(blank=True)
    validation_status = models.CharField(
        max_length=20,
        choices=ValidationStatus.choices,
        default=ValidationStatus.NEEDS_REVIEW,
    )

    # Recommendation (headhunter manual judgment)
    recommendation_status = models.CharField(
        max_length=20,
        choices=RecommendationStatus.choices,
        default=RecommendationStatus.PENDING,
        db_index=True,
    )

    raw_extracted_json = models.JSONField(default=dict, blank=True)
    confidence_score = models.FloatField(null=True, blank=True)
    field_confidences = models.JSONField(default=dict, blank=True)

    # Organization ownership (DB sharing network)
    owned_by = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_candidates",
    )

    class Meta:
        db_table = "candidates"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["status"], name="idx_candidate_status"),
            models.Index(fields=["birth_year"], name="idx_candidate_birth_year"),
            models.Index(
                fields=["total_experience_years"],
                name="idx_candidate_exp_years",
            ),
            models.Index(fields=["email"], name="idx_candidate_email"),
            models.Index(
                fields=["validation_status"],
                name="idx_candidate_valid_status",
            ),
        ]

    def __str__(self):
        parts = [self.name]
        if self.current_company:
            parts.append(self.current_company)
        if self.current_position:
            parts.append(self.current_position)
        return " / ".join(parts)

    def save(self, *args, **kwargs):
        from candidates.services.candidate_identity import normalize_phone_for_matching

        self.phone_normalized = normalize_phone_for_matching(self.phone)

        update_fields = kwargs.get("update_fields")
        if update_fields is not None and (
            "phone" in update_fields or "phone_normalized" in update_fields
        ):
            kwargs["update_fields"] = set(update_fields) | {"phone_normalized"}

        return super().save(*args, **kwargs)

    def _build_experience_metrics(
        self,
        reference_year_month: tuple[int, int] | None = None,
    ) -> dict:
        if reference_year_month is None:
            current_date = timezone.localdate()
            reference_year_month = (current_date.year, current_date.month)

        current_month_index = _month_index(*reference_year_month)

        raw_intervals: list[tuple[int, int]] = []
        ignored_careers = 0
        capped_future_dates = 0
        duration_adjusted_careers = 0

        for career in self.careers.all():
            start = _parse_year_month(career.start_date, default_month=1)
            if start is None:
                ignored_careers += 1
                continue

            start_index = _month_index(*start)
            if start_index > current_month_index:
                ignored_careers += 1
                continue

            end = career.effective_end_year_month(reference_year_month)
            if end is None:
                ignored_careers += 1
                continue

            end_index = _month_index(*end)
            if end_index > current_month_index:
                end_index = current_month_index
                capped_future_dates += 1

            if career.uses_duration_inference(reference_year_month):
                duration_adjusted_careers += 1

            if end_index < start_index:
                ignored_careers += 1
                continue

            raw_intervals.append((start_index, end_index))

        if not raw_intervals:
            return {
                "total_months": None,
                "reference_span_months": None,
                "ignored_careers": ignored_careers,
                "capped_future_dates": capped_future_dates,
                "duration_adjusted_careers": duration_adjusted_careers,
            }

        merged_intervals: list[list[int]] = []
        for start_index, end_index in sorted(raw_intervals):
            if not merged_intervals or start_index > merged_intervals[-1][1] + 1:
                merged_intervals.append([start_index, end_index])
                continue
            merged_intervals[-1][1] = max(merged_intervals[-1][1], end_index)

        total_months = sum(
            end_index - start_index + 1 for start_index, end_index in merged_intervals
        )
        earliest_start = min(start_index for start_index, _ in raw_intervals)
        reference_span_months = current_month_index - earliest_start + 1

        return {
            "total_months": total_months,
            "reference_span_months": reference_span_months,
            "ignored_careers": ignored_careers,
            "capped_future_dates": capped_future_dates,
            "duration_adjusted_careers": duration_adjusted_careers,
        }

    @cached_property
    def _merged_experience_intervals(self) -> list[tuple[int, int]]:
        current_date = timezone.localdate()
        current_month_index = _month_index(current_date.year, current_date.month)
        raw_intervals: list[tuple[int, int]] = []

        for career in self.careers.all():
            start = _parse_year_month(career.start_date, default_month=1)
            if start is None:
                continue

            start_index = _month_index(*start)
            if start_index > current_month_index:
                continue

            end = career.effective_end_year_month(
                (current_date.year, current_date.month)
            )
            if end is None:
                continue
            end_index = min(_month_index(*end), current_month_index)

            if end_index < start_index:
                continue

            raw_intervals.append((start_index, end_index))

        if not raw_intervals:
            return []

        merged_intervals: list[list[int]] = []
        for start_index, end_index in sorted(raw_intervals):
            if not merged_intervals or start_index > merged_intervals[-1][1] + 1:
                merged_intervals.append([start_index, end_index])
                continue
            merged_intervals[-1][1] = max(merged_intervals[-1][1], end_index)

        return [(start, end) for start, end in merged_intervals]

    @cached_property
    def _experience_metrics(self) -> dict:
        return self._build_experience_metrics()

    @cached_property
    def _experience_metrics_at_resume_reference(self) -> dict:
        if self.effective_resume_reference_year_month is None:
            return {
                "total_months": None,
                "reference_span_months": None,
                "ignored_careers": 0,
                "capped_future_dates": 0,
            }
        return self._build_experience_metrics(
            self.effective_resume_reference_year_month
        )

    @property
    def resume_reference_year_month(self) -> tuple[int, int] | None:
        return _parse_year_month(self.resume_reference_date, default_month=12)

    @property
    def resume_reference_date_display(self) -> str:
        return _format_reference_date(self.resume_reference_date)

    @cached_property
    def inferred_resume_reference_year_month(self) -> tuple[int, int] | None:
        extracted = self.extracted_total_experience_months
        computed = self.computed_total_experience_months
        if extracted is None or computed is None or extracted >= computed:
            return None

        if not any(
            career.is_current and not career.end_date.strip()
            for career in self.careers.all()
        ):
            return None

        remaining = extracted
        for start_index, end_index in self._merged_experience_intervals:
            interval_months = end_index - start_index + 1
            if remaining <= interval_months:
                target_index = start_index + remaining - 1
                year, month_zero = divmod(target_index, 12)
                return year, month_zero + 1
            remaining -= interval_months

        return None

    @property
    def effective_resume_reference_year_month(self) -> tuple[int, int] | None:
        return (
            self.resume_reference_year_month
            or self.inferred_resume_reference_year_month
        )

    @property
    def effective_resume_reference_date_display(self) -> str:
        if self.resume_reference_date_display:
            return self.resume_reference_date_display
        return _format_reference_year_month(self.inferred_resume_reference_year_month)

    @property
    def effective_resume_reference_source(self) -> str:
        if self.resume_reference_date_source:
            return self.resume_reference_date_source
        if self.inferred_resume_reference_year_month:
            return self.ResumeReferenceDateSource.INFERRED
        return ""

    @property
    def computed_total_experience_months(self) -> int | None:
        return self._experience_metrics["total_months"]

    @property
    def computed_total_experience_display(self) -> str:
        return _format_duration_months(self.computed_total_experience_months)

    @property
    def reference_total_experience_months(self) -> int | None:
        return self._experience_metrics_at_resume_reference["total_months"]

    @property
    def reference_total_experience_display(self) -> str:
        return _format_duration_months(self.reference_total_experience_months)

    @property
    def extracted_total_experience_months(self) -> int | None:
        if self.total_experience_years is None:
            return None
        return self.total_experience_years * 12

    @property
    def extracted_total_experience_display(self) -> str:
        if self.total_experience_years is None:
            return ""
        return f"{self.total_experience_years}년"

    @property
    def total_experience_display(self) -> str:
        return (
            self.computed_total_experience_display
            or self.extracted_total_experience_display
        )

    @property
    def experience_discrepancy_months(self) -> int | None:
        computed = (
            self.reference_total_experience_months
            or self.computed_total_experience_months
        )
        extracted = self.extracted_total_experience_months
        if computed is None or extracted is None:
            return None
        return abs(computed - extracted)

    @property
    def has_experience_discrepancy(self) -> bool:
        discrepancy = self.experience_discrepancy_months
        return discrepancy is not None and discrepancy >= 12

    @property
    def experience_reference_span_display(self) -> str:
        return _format_duration_months(
            self._experience_metrics["reference_span_months"]
        )

    @property
    def current_vs_reference_experience_gap_months(self) -> int | None:
        current = self.computed_total_experience_months
        reference = self.reference_total_experience_months
        if current is None or reference is None:
            return None
        return max(0, current - reference)

    @property
    def experience_notice_tone(self) -> str:
        return ""

    @property
    def experience_notice_text(self) -> str:
        return ""

    @property
    def ignored_career_count(self) -> int:
        return self._experience_metrics["ignored_careers"]

    @property
    def capped_future_career_count(self) -> int:
        return self._experience_metrics["capped_future_dates"]

    @property
    def duration_adjusted_career_count(self) -> int:
        return self._experience_metrics["duration_adjusted_careers"]

    @property
    def needs_experience_review(self) -> bool:
        return bool(self.experience_review_notice_items)

    @property
    def experience_review_notice_items(self) -> list[dict]:
        items: list[dict] = []

        if self.capped_future_career_count:
            severity = "YELLOW" if self.capped_future_career_count >= 2 else "BLUE"
            items.append(
                {
                    "severity": severity,
                    "label": _severity_label(severity),
                    "detail": (
                        f"미래 날짜 {self.capped_future_career_count}건은 현재 기준으로 보정해 계산했습니다."
                    ),
                    "summary": f"미래 날짜 보정 {self.capped_future_career_count}건",
                    "type": "EXPERIENCE_FUTURE_DATE_ADJUSTED",
                }
            )

        if self.duration_adjusted_career_count:
            items.append(
                {
                    "severity": "BLUE",
                    "label": _severity_label("BLUE"),
                    "detail": (
                        f"기간 정보가 있는 경력 {self.duration_adjusted_career_count}건은 "
                        "종료일을 보정해 총 경력 계산에 반영했습니다."
                    ),
                    "summary": f"종료일 보정 {self.duration_adjusted_career_count}건",
                    "type": "EXPERIENCE_DURATION_ADJUSTED",
                }
            )

        if self.ignored_career_count:
            severity = "YELLOW" if self.ignored_career_count >= 2 else "BLUE"
            items.append(
                {
                    "severity": severity,
                    "label": _severity_label(severity),
                    "detail": (
                        f"날짜와 기간 정보가 모두 부족한 경력 {self.ignored_career_count}건은 "
                        "총 경력 계산에서 제외했습니다."
                    ),
                    "summary": f"불완전 경력 제외 {self.ignored_career_count}건",
                    "type": "EXPERIENCE_INCOMPLETE_CAREER_IGNORED",
                }
            )

        deduped: dict[tuple[str, str], dict] = {}
        for item in items:
            key = (item.get("type", ""), item.get("detail", ""))
            existing = deduped.get(key)
            if existing is None or _severity_sort_key(
                item["severity"]
            ) < _severity_sort_key(existing["severity"]):
                deduped[key] = item

        return sorted(
            deduped.values(),
            key=lambda item: (
                _severity_sort_key(item["severity"]),
                item.get("detail", ""),
            ),
        )

    @property
    def review_notice_items(self) -> list[dict]:
        report = self.latest_self_consistency_report
        items = []
        if report and report.total_alert_count:
            items.extend(report.notice_items)
        items.extend(self.experience_review_notice_items)

        deduped: dict[tuple[str, str], dict] = {}
        for item in items:
            key = (item.get("type", ""), item.get("detail", ""))
            existing = deduped.get(key)
            if existing is None or _severity_sort_key(
                item["severity"]
            ) < _severity_sort_key(existing["severity"]):
                deduped[key] = item

        return sorted(
            deduped.values(),
            key=lambda item: (
                _severity_sort_key(item["severity"]),
                item.get("detail", ""),
            ),
        )

    @property
    def has_review_notices(self) -> bool:
        return bool(self.review_notice_items)

    @property
    def review_notice_summary(self) -> str:
        items = self.review_notice_items
        if not items:
            return ""

        counts = {"RED": 0, "YELLOW": 0, "BLUE": 0}
        for item in items:
            severity = item.get("severity")
            if severity in counts:
                counts[severity] += 1

        parts = []
        for severity in ("RED", "YELLOW", "BLUE"):
            if counts[severity]:
                parts.append(f"{_severity_label(severity)} {counts[severity]}건")

        summary = ", ".join(parts)
        first_detail = items[0].get("detail")
        if first_detail:
            return f"{summary}. {first_detail}"
        return summary

    def _review_notice_count(self, severity: str) -> int:
        return sum(
            1 for item in self.review_notice_items if item.get("severity") == severity
        )

    @property
    def review_notice_red_count(self) -> int:
        return self._review_notice_count("RED")

    @property
    def review_notice_yellow_count(self) -> int:
        return self._review_notice_count("YELLOW")

    @property
    def review_notice_blue_count(self) -> int:
        return self._review_notice_count("BLUE")

    @property
    def top_review_notice_detail(self) -> str:
        items = self.review_notice_items
        return items[0]["detail"] if items else ""

    @property
    def review_notice_card_summary(self) -> str:
        items = self.review_notice_items
        if not items:
            return ""
        return " · ".join(item.get("summary", item["detail"]) for item in items)

    @property
    def latest_self_consistency_report(self):
        prefetched = getattr(self, "prefetched_self_consistency_reports", None)
        if prefetched is not None:
            return prefetched[0] if prefetched else None

        return (
            self.discrepancy_reports.filter(
                report_type=DiscrepancyReport.ReportType.SELF_CONSISTENCY
            )
            .order_by("-created_at")
            .first()
        )


class Resume(BaseModel):
    """이력서 파일 메타데이터 및 원문."""

    class ProcessingStatus(models.TextChoices):
        PENDING = "pending", "대기"
        DOWNLOADED = "downloaded", "다운로드 완료"
        TEXT_ONLY = "text_only", "텍스트만 저장"
        STRUCTURED = "structured", "구조화 완료"
        FAILED = "failed", "실패"

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="resumes",
    )
    file_name = models.CharField(max_length=300)
    drive_file_id = models.CharField(max_length=100, unique=True)
    drive_folder = models.CharField(max_length=500, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    file_size = models.IntegerField(null=True, blank=True)
    raw_text = models.TextField(blank=True)
    is_primary = models.BooleanField(default=False)
    version = models.SmallIntegerField(default=1)
    processing_status = models.CharField(
        max_length=15,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
    )
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "resumes"
        ordering = ["-is_primary", "-version"]

    def __str__(self):
        return self.file_name


class Education(BaseModel):
    """학력."""

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="educations",
    )
    institution = models.CharField(max_length=255)
    degree = models.CharField(max_length=100, blank=True)
    major = models.CharField(max_length=255, blank=True)
    gpa = models.CharField(max_length=100, blank=True)
    start_year = models.IntegerField(null=True, blank=True)
    end_year = models.IntegerField(null=True, blank=True)
    is_abroad = models.BooleanField(default=False)

    class Meta:
        db_table = "educations"
        ordering = ["-end_year"]

    def __str__(self):
        return f"{self.institution} {self.degree} {self.major}".strip()


class Career(BaseModel):
    """경력."""

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="careers",
    )
    company = models.CharField(max_length=255)
    company_en = models.CharField(max_length=255, blank=True)
    position = models.CharField(max_length=255, blank=True)
    department = models.CharField(max_length=255, blank=True)
    start_date = models.CharField(max_length=255, blank=True)
    end_date = models.CharField(max_length=255, blank=True)
    duration_text = models.CharField(max_length=255, blank=True)
    end_date_inferred = models.CharField(max_length=255, blank=True)
    date_evidence = models.TextField(blank=True)
    date_confidence = models.FloatField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    duties = models.TextField(blank=True)
    inferred_capabilities = models.TextField(
        blank=True,
        help_text="AI가 직책/부서/경력 수준을 바탕으로 추정한 수행 가능 역량",
    )
    achievements = models.TextField(blank=True)
    reason_left = models.CharField(max_length=500, blank=True)
    salary = models.IntegerField(null=True, blank=True, help_text="만원")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "careers"
        ordering = ["-is_current", "order"]
        indexes = [
            models.Index(fields=["company"], name="idx_career_company"),
        ]

    def __str__(self):
        return f"{self.company} - {self.position}"

    @staticmethod
    def _parse_year_month(date_str: str, default_month: int) -> tuple[int, int] | None:
        """Parse career dates stored as strings into a (year, month) tuple."""
        return _parse_year_month(date_str, default_month)

    @cached_property
    def inferred_duration_months(self) -> int | None:
        structured_duration = _parse_duration_months(self.duration_text)
        if structured_duration is not None:
            return structured_duration

        raw_text = (self.candidate.raw_text or "").strip()
        if not raw_text or not self.company:
            return None

        start = self._parse_year_month(self.start_date, default_month=1)
        date_tokens: list[str] = []
        if start is not None:
            year, month = start
            date_tokens = [
                f"{year}/{month:02d}",
                f"{year}-{month:02d}",
                f"{year}.{month:02d}",
                f"{year}/{month}",
                f"{year}-{month}",
                f"{year}.{month}",
            ]

        company_terms = [self.company]
        if self.company_en:
            company_terms.append(self.company_en)

        fallback_duration: int | None = None
        for term in company_terms:
            for match in re.finditer(re.escape(term), raw_text, re.IGNORECASE):
                snippet_start = max(0, match.start() - 180)
                snippet_end = min(len(raw_text), match.end() + 220)
                snippet = raw_text[snippet_start:snippet_end]
                local_company_index = match.start() - snippet_start
                duration_matches = list(
                    re.finditer(
                        r"(?:(?P<years>\d+)\s*년\s*(?P<months>\d+)\s*개월)"
                        r"|(?:(?P<years_only>\d+)\s*년)"
                        r"|(?:(?P<months_only>\d+)\s*개월)",
                        snippet,
                    )
                )
                if not duration_matches:
                    continue
                closest_match = min(
                    duration_matches,
                    key=lambda duration_match: abs(
                        duration_match.start() - local_company_index
                    ),
                )
                years = int(
                    closest_match.group("years")
                    or closest_match.group("years_only")
                    or 0
                )
                months = int(
                    closest_match.group("months")
                    or closest_match.group("months_only")
                    or 0
                )
                duration = years * 12 + months
                if duration <= 0:
                    continue
                if fallback_duration is None:
                    fallback_duration = duration
                if not date_tokens or any(token in snippet for token in date_tokens):
                    return duration

        return fallback_duration

    @cached_property
    def inferred_end_year_month(self) -> tuple[int, int] | None:
        explicit_inference = self._parse_year_month(
            self.end_date_inferred, default_month=12
        )
        if explicit_inference is not None:
            return explicit_inference

        start = self._parse_year_month(self.start_date, default_month=1)
        inferred_duration = self.inferred_duration_months
        if start is None or inferred_duration is None:
            return None

        start_index = _month_index(*start)
        end_index = start_index + inferred_duration - 1
        return _year_month_from_month_index(end_index)

    def effective_end_year_month(
        self,
        reference_year_month: tuple[int, int] | None = None,
    ) -> tuple[int, int] | None:
        if reference_year_month is None:
            today = timezone.localdate()
            reference_year_month = (today.year, today.month)

        if self.is_current and not self.end_date.strip():
            return reference_year_month

        explicit_end = self._parse_year_month(self.end_date, default_month=12)
        if explicit_end is not None:
            return explicit_end
        if self.is_current:
            return None
        return self.inferred_end_year_month

    def uses_duration_inference(
        self,
        reference_year_month: tuple[int, int] | None = None,
    ) -> bool:
        return (
            not self.is_current
            and not self.end_date.strip()
            and (
                self._parse_year_month(self.end_date_inferred, default_month=12)
                is not None
                or self.inferred_duration_months is not None
            )
            and self.effective_end_year_month(reference_year_month) is not None
        )

    @property
    def start_date_display(self) -> str:
        return _format_year_month(
            self._parse_year_month(self.start_date, default_month=1)
        ) or (self.start_date or "")

    @property
    def end_date_display(self) -> str:
        if self.is_current and not self.end_date.strip():
            return "현재"
        explicit_end = self._parse_year_month(self.end_date, default_month=12)
        if explicit_end is not None:
            return _format_year_month(explicit_end)
        inferred_end = self.effective_end_year_month()
        if inferred_end is not None:
            return _format_year_month(inferred_end)
        return self.end_date or ""

    @property
    def duration_months(self) -> int | None:
        """Return the inclusive career duration in months."""
        start = self._parse_year_month(self.start_date, default_month=1)
        if start is None:
            return None

        end = self.effective_end_year_month()

        if end is None:
            return None

        total_months = (end[0] - start[0]) * 12 + (end[1] - start[1]) + 1
        if total_months <= 0:
            return None

        return total_months

    @property
    def duration_display(self) -> str:
        """Return a human-readable duration like '3년 6개월'."""
        return _format_duration_months(self.duration_months)


class Certification(BaseModel):
    """자격증."""

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="certifications",
    )
    name = models.CharField(max_length=255)
    issuer = models.CharField(max_length=255, blank=True)
    acquired_date = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "certifications"
        ordering = ["-acquired_date"]

    def __str__(self):
        return self.name


class LanguageSkill(BaseModel):
    """어학."""

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="language_skills",
    )
    language = models.CharField(max_length=100)
    test_name = models.CharField(max_length=100, blank=True)
    score = models.CharField(max_length=255, blank=True)
    level = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "language_skills"

    def __str__(self):
        parts = [self.language]
        if self.test_name and self.score:
            parts.append(f"{self.test_name} {self.score}")
        elif self.level:
            parts.append(self.level)
        return " - ".join(parts)


class ExtractionLog(BaseModel):
    """AI 추출/사람 편집 이력."""

    class Action(models.TextChoices):
        AUTO_EXTRACT = "auto_extract", "자동 추출"
        HUMAN_EDIT = "human_edit", "사람 편집"
        HUMAN_CONFIRM = "human_confirm", "사람 확인"
        HUMAN_REJECT = "human_reject", "사람 거부"

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="extraction_logs",
    )
    resume = models.ForeignKey(
        Resume,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="extraction_logs",
    )
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
    )
    field_name = models.CharField(max_length=50, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "extraction_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} - {self.field_name}"


class SearchSession(BaseModel):
    """음성/텍스트 검색 세션 (multi-turn)."""

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="search_sessions",
    )
    is_active = models.BooleanField(default=True)
    current_filters = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "search_sessions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Session({self.user}, active={self.is_active})"


class SearchTurn(BaseModel):
    """검색 세션 내 개별 턴."""

    class InputType(models.TextChoices):
        VOICE = "voice", "음성"
        TEXT = "text", "텍스트"

    session = models.ForeignKey(
        SearchSession,
        on_delete=models.CASCADE,
        related_name="turns",
    )
    turn_number = models.PositiveIntegerField()
    input_type = models.CharField(
        max_length=10,
        choices=InputType.choices,
        default=InputType.TEXT,
    )
    user_text = models.TextField()
    ai_response = models.TextField(blank=True)
    filters_applied = models.JSONField(default=dict, blank=True)
    result_count = models.IntegerField(default=0)

    class Meta:
        db_table = "search_turns"
        ordering = ["turn_number"]

    def __str__(self):
        return f"Turn {self.turn_number}: {self.user_text[:30]}"


class CandidateEmbedding(BaseModel):
    """후보자 임베딩 벡터 (Gemini 3072-dim)."""

    candidate = models.OneToOneField(
        Candidate,
        on_delete=models.CASCADE,
        related_name="embedding",
    )
    embedding = VectorField(dimensions=3072)
    text_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "candidate_embeddings"

    def __str__(self):
        return f"Embedding({self.candidate.name})"

    @staticmethod
    def cosine_distance_expression(query_vector):
        return CosineDistance("embedding", query_vector)


class DiscrepancyReport(BaseModel):
    """후보자 무결성/불일치 진단 결과."""

    class ReportType(models.TextChoices):
        SELF_CONSISTENCY = "self_consistency", "내부 일관성"
        CROSS_VERSION = "cross_version", "버전 간 비교"

    candidate = models.ForeignKey(
        "Candidate",
        on_delete=models.CASCADE,
        related_name="discrepancy_reports",
    )
    source_resume = models.ForeignKey(
        "Resume",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_discrepancy_reports",
    )
    compared_resume = models.ForeignKey(
        "Resume",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="compared_discrepancy_reports",
    )
    report_type = models.CharField(
        max_length=20,
        choices=ReportType.choices,
        default=ReportType.SELF_CONSISTENCY,
    )
    integrity_score = models.FloatField(default=1.0)
    summary = models.TextField(blank=True)
    alerts = models.JSONField(default=list)
    llm_assessment = models.TextField(blank=True)
    scan_version = models.CharField(max_length=20, default="v1")

    class Meta:
        db_table = "discrepancy_reports"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["candidate", "report_type"],
                name="idx_discrepancy_candidate_type",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_report_type_display()} - "
            f"{self.candidate.name} ({self.integrity_score})"
        )

    def _alert_count(self, severity: str) -> int:
        return sum(
            1
            for alert in self.alerts
            if isinstance(alert, dict) and alert.get("severity") == severity
        )

    @property
    def red_alert_count(self) -> int:
        return self._alert_count("RED")

    @property
    def yellow_alert_count(self) -> int:
        return self._alert_count("YELLOW")

    @property
    def blue_alert_count(self) -> int:
        return self._alert_count("BLUE")

    @property
    def total_alert_count(self) -> int:
        return self.red_alert_count + self.yellow_alert_count + self.blue_alert_count

    @property
    def has_actionable_alerts(self) -> bool:
        return self.red_alert_count > 0 or self.yellow_alert_count > 0

    @property
    def top_alert_detail(self) -> str:
        for alert in self.alerts:
            if isinstance(alert, dict) and alert.get("detail"):
                return alert["detail"]
        return ""

    @property
    def notice_items(self) -> list[dict]:
        items = []
        for alert in self.alerts:
            if not isinstance(alert, dict) or not alert.get("detail"):
                continue
            severity = alert.get("severity", "BLUE")
            detail = alert["detail"]
            summary = alert.get("summary") or (
                detail[:30] + "…" if len(detail) > 30 else detail
            )
            items.append(
                {
                    "severity": severity,
                    "label": _severity_label(severity),
                    "detail": detail,
                    "summary": summary,
                    "type": alert.get("type", ""),
                }
            )
        return items


class ValidationDiagnosis(BaseModel):
    """추출 검증 진단 결과. 재시도 이력 추적."""

    candidate = models.ForeignKey(
        "Candidate",
        on_delete=models.CASCADE,
        related_name="diagnoses",
    )
    resume = models.ForeignKey(
        "Resume",
        on_delete=models.CASCADE,
        related_name="diagnoses",
    )
    attempt_number = models.PositiveIntegerField(default=1)
    verdict = models.CharField(max_length=10)  # pass / fail
    overall_score = models.FloatField()
    issues = models.JSONField(default=list)
    field_scores = models.JSONField(default=dict)
    retry_action = models.CharField(max_length=30, blank=True)

    class Meta:
        db_table = "validation_diagnoses"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Attempt {self.attempt_number}: {self.verdict} ({self.overall_score})"


REASON_CODES = {
    # 학력
    "edu_undergrad_missing": "학부 미기재 (대학원만 기재)",
    "edu_campus_suspicious": "캠퍼스 미기재 또는 의심",
    "edu_admission_year_missing": "입학년도 미기재 (편입 의심)",
    "edu_non_degree_program": "비정규 과정 (전산원 등)",
    # 경력
    "career_deleted": "경력 삭제 의심",
    "career_consolidated": "경력 통합 의심",
    "career_content_mismatch": "업무 내용 불일치 (면접 확인)",
    "career_gap_suspicious": "경력 공백 의심",
    # 신상
    "birth_year_mismatch": "출생연도 불일치",
    # 기타
    "other": "기타",
}


class CandidateComment(BaseModel):
    """후보자 검수 코멘트. 판정 변경 이력 포함."""

    class InputMethod(models.TextChoices):
        TEXT = "text", "텍스트"
        VOICE = "voice", "음성"

    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="candidate_comments",
    )

    # Recommendation snapshot at the time of this comment
    recommendation_status = models.CharField(
        max_length=20,
        choices=Candidate.RecommendationStatus.choices,
    )

    # Reason codes (multiple selection)
    reason_codes = models.JSONField(
        default=list,
        blank=True,
        help_text='["edu_undergrad_missing", "career_deleted", ...]',
    )

    # Free text
    content = models.TextField(blank=True)

    # Input method
    input_method = models.CharField(
        max_length=10,
        choices=InputMethod.choices,
        default=InputMethod.TEXT,
    )

    class Meta:
        db_table = "candidate_comments"
        ordering = ["-created_at"]

    def __str__(self):
        status = self.get_recommendation_status_display()
        return f"{self.candidate.name} - {status} ({self.created_at:%Y-%m-%d})"

    @property
    def reason_labels(self) -> list[str]:
        return [REASON_CODES.get(code, code) for code in self.reason_codes]
