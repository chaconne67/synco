from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from common.mixins import BaseModel


# ---------------------------------------------------------------------------
# Enums — Project
# ---------------------------------------------------------------------------


class JDSource(models.TextChoices):
    UPLOAD = "upload", "파일 업로드"
    DRIVE = "drive", "Google Drive"
    TEXT = "text", "텍스트 입력"


class ProjectPhase(models.TextChoices):
    SEARCHING = "searching", "서칭"
    SCREENING = "screening", "심사"


class ProjectStatus(models.TextChoices):
    OPEN = "open", "진행중"
    CLOSED = "closed", "종료"


class ProjectResult(models.TextChoices):
    SUCCESS = "success", "성공"
    FAIL = "fail", "실패"


# ---------------------------------------------------------------------------
# Enums — ActionType / ActionItem
# ---------------------------------------------------------------------------


class ActionChannel(models.TextChoices):
    IN_PERSON = "in_person", "대면"
    VIDEO = "video", "화상"
    PHONE = "phone", "전화"
    KAKAO = "kakao", "카톡"
    SMS = "sms", "문자"
    EMAIL = "email", "이메일"
    LINKEDIN = "linkedin", "LinkedIn"
    OTHER = "other", "기타"


class ActionOutputKind(models.TextChoices):
    NONE = "", "없음"
    SUBMISSION = "submission", "서류 패키지"
    INTERVIEW = "interview", "면접"
    MEETING = "meeting", "사전미팅"


class ActionItemStatus(models.TextChoices):
    PENDING = "pending", "대기"
    DONE = "done", "완료"
    SKIPPED = "skipped", "건너뜀"
    CANCELLED = "cancelled", "취소"


# ---------------------------------------------------------------------------
# Enums — Application
# ---------------------------------------------------------------------------


class DropReason(models.TextChoices):
    UNFIT = "unfit", "부적합"
    CANDIDATE_DECLINED = "candidate_declined", "후보자 거절/포기"
    CLIENT_REJECTED = "client_rejected", "클라이언트 탈락"
    OTHER = "other", "기타"


# ---------------------------------------------------------------------------
# State mapping — Application.current_state derives from latest ActionItem
# ---------------------------------------------------------------------------

STATE_FROM_ACTION_TYPE: dict[str, str] = {
    "pre_meeting": "pre_met",
    "submit_to_client": "submitted",
    "interview_round": "interviewing",
    "confirm_hire": "hired",
    # Phase 2: complete mapping for all 23 action types
}


# ---------------------------------------------------------------------------
# 업무 프로세스 8단계 — 엑셀 분석(01-excel-analysis §5) + synco 사전 미팅 추가
# 각 단계는 Completion Gate(ActionType)를 가지며, 그 액션 완료 시 단계 통과.
# ---------------------------------------------------------------------------

STAGES_ORDER = [
    ("sourcing",        "서칭"),
    ("contact",         "접촉"),
    ("resume",          "이력서 준비"),
    ("pre_meeting",     "사전 미팅"),
    ("prep_submission", "이력서 작성(제출용)"),
    ("client_submit",   "이력서 제출"),
    ("interview",       "면접"),
    ("hired",           "입사"),
]

# 후보자 카드 진행바에 표시할 단계 (서칭은 프로젝트 레벨이라 제외)
CARD_STAGES_ORDER = [
    (sid, label) for sid, label in STAGES_ORDER if sid != "sourcing"
]

# ActionType.code → stage_id. 단계 영향 없는 범용 활동은 매핑 없음.
STAGE_FROM_ACTION_TYPE: dict[str, str] = {
    "search_db":              "sourcing",
    "search_external":        "sourcing",
    "reach_out":              "contact",
    "re_reach_out":           "contact",
    "await_reply":            "contact",
    "share_jd":               "contact",
    "receive_resume":         "resume",
    "convert_resume":         "resume",
    "schedule_pre_meet":      "pre_meeting",
    "pre_meeting":            "pre_meeting",
    "prepare_submission":     "prep_submission",
    "submit_to_pm":           "prep_submission",
    "submit_to_client":       "client_submit",
    "await_doc_review":       "client_submit",
    "receive_doc_feedback":   "client_submit",
    "schedule_interview":     "interview",
    "interview_round":        "interview",
    "await_interview_result": "interview",
    "confirm_hire":           "hired",
    "await_onboarding":       "hired",
    # follow_up, escalate_to_boss, note → 지원 활동 (stage 진행에 영향 없음)
}

# 각 stage의 completion gate (이 ActionType이 완료되면 단계 통과)
# 원칙: gate는 "단계 완료를 의미하는 가장 자연스러운 액션". share_jd/await_reply 는 reach_out 중
#       자연 발생하는 부산물이므로 독립 gate가 아니라 선택적 보조 액션으로 둠.
STAGE_GATES: dict[str, str | None] = {
    "sourcing":        None,              # Application 생성 자체가 gate
    "contact":         "reach_out",       # 연락 한 번 성공 = 접촉 완료
    "resume":          "receive_resume",
    "pre_meeting":     "pre_meeting",
    "prep_submission": "submit_to_pm",
    "client_submit":   "submit_to_client",
    "interview":       "interview_round",
    "hired":           "confirm_hire",
}

# 건너뛰기 placeholder ActionType code — update_action_labels 커맨드가 seed
STAGE_SKIPPED_ACTION_CODE = "stage_skipped"


# ===========================================================================
# Project
# ===========================================================================


class Project(BaseModel):
    """의뢰 건 (헤드헌팅 프로젝트)."""

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="projects",
    )
    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="projects",
    )
    title = models.CharField(max_length=300)
    jd_text = models.TextField(blank=True)
    jd_file = models.FileField(upload_to="projects/jd/", blank=True)
    jd_source = models.CharField(max_length=20, choices=JDSource.choices, blank=True)
    jd_drive_file_id = models.CharField(max_length=255, blank=True)
    jd_raw_text = models.TextField(blank=True)
    jd_analysis = models.JSONField(default=dict, blank=True)

    # --- New fields (FINAL-SPEC 2.1) ---
    phase = models.CharField(
        max_length=20,
        choices=ProjectPhase.choices,
        default=ProjectPhase.SEARCHING,
        db_index=True,
    )
    # Auto-derived field. Phase 2 signal: compute_project_phase.
    # Rule: if any active Application has a completed submit_to_client
    # ActionItem → screening. All dropped → back to searching.
    # See FINAL-SPEC 3.1 / 6.2.

    status = models.CharField(
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.OPEN,
        db_index=True,
    )
    deadline = models.DateField(null=True, blank=True)
    annual_salary = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        null=True,
        blank=True,
        help_text="포지션 연봉 (원)",
    )
    fee_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="수수료율 (%, 예: 20.00)",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    result = models.CharField(
        max_length=20,
        choices=ProjectResult.choices,
        blank=True,
        default="",
    )
    note = models.TextField(blank=True)

    assigned_consultants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="assigned_projects",
    )
    requirements = models.JSONField(default=dict, blank=True)
    posting_text = models.TextField(blank=True)
    posting_file_name = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_projects",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["phase", "status"]),
            models.Index(fields=["deadline"]),
            models.Index(fields=["organization", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(status="open", closed_at__isnull=False),
                name="project_open_implies_no_closed_at",
            ),
            models.CheckConstraint(
                check=~models.Q(status="open") | models.Q(result=""),
                name="project_open_implies_empty_result",
            ),
            models.CheckConstraint(
                check=models.Q(result="") | models.Q(status="closed"),
                name="project_result_implies_closed",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_closed(self) -> bool:
        return self.status == ProjectStatus.CLOSED

    @property
    def days_elapsed(self) -> int:
        return (timezone.now().date() - self.created_at.date()).days

    @property
    def expected_fee(self):
        """예상 수수료 매출 (원). annual_salary·fee_percent 둘 다 있을 때만 계산."""
        if self.annual_salary is None or self.fee_percent is None:
            return None
        return int(self.annual_salary * self.fee_percent / 100)


# ===========================================================================
# ActionType (DB table — replaces old TextChoices enum)
# ===========================================================================


class ActionType(BaseModel):
    """액션 종류 마스터 테이블. 관리자 페이지에서 추가/비활성화 가능."""

    code = models.CharField(max_length=40, unique=True)
    label_ko = models.CharField(max_length=100)
    phase = models.CharField(max_length=20, blank=True, default="")
    default_channel = models.CharField(
        max_length=20,
        choices=ActionChannel.choices,
        blank=True,
        default="",
    )
    output_kind = models.CharField(
        max_length=20,
        choices=ActionOutputKind.choices,
        blank=True,
        default="",
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_protected = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    suggests_next = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self) -> str:
        return f"{self.code} ({self.label_ko})"


# ===========================================================================
# Application
# ===========================================================================


class ApplicationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(dropped_at__isnull=True, hired_at__isnull=True)

    def submitted(self):
        return (
            self.active()
            .filter(
                action_items__action_type__code="submit_to_client",
                action_items__status=ActionItemStatus.DONE,
            )
            .distinct()
        )

    def for_project(self, project):
        return self.filter(project=project)


class Application(BaseModel):
    """프로젝트-후보자 매칭. 진행 상태는 ActionItem에서 파생."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="applications",
    )
    candidate = models.ForeignKey(
        "candidates.Candidate",
        on_delete=models.CASCADE,
        related_name="applications",
    )
    notes = models.TextField(blank=True)
    hired_at = models.DateTimeField(null=True, blank=True)
    dropped_at = models.DateTimeField(null=True, blank=True)
    drop_reason = models.CharField(
        max_length=30,
        choices=DropReason.choices,
        blank=True,
        default="",
    )
    drop_note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_applications",
    )

    objects = ApplicationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "candidate"],
                name="unique_application_per_project_candidate",
            ),
            models.UniqueConstraint(
                fields=["project"],
                condition=models.Q(hired_at__isnull=False),
                name="unique_hired_per_project",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "dropped_at", "hired_at"]),
            models.Index(fields=["candidate"]),
        ]

    def __str__(self) -> str:
        return f"{self.project} - {self.candidate}"

    @property
    def is_active(self) -> bool:
        return self.dropped_at is None and self.hired_at is None

    @property
    def current_state(self) -> str:
        """UI display state derived from latest completed ActionItem."""
        if self.dropped_at:
            return "dropped"
        if self.hired_at:
            return "hired"
        latest_done = (
            self.action_items.filter(status=ActionItemStatus.DONE)
            .order_by("-completed_at")
            .first()
        )
        if not latest_done:
            return "matched"
        return STATE_FROM_ACTION_TYPE.get(latest_done.action_type.code, "in_progress")

    @property
    def stages_passed(self) -> set[str]:
        """이 Application이 통과한 단계들 (gate 완료 또는 건너뛰기 placeholder 기록 기준)."""
        passed = {"sourcing"}  # Application 존재 자체가 서칭 통과
        if self.hired_at:
            # hired는 모든 앞 단계 통과 + 입사까지 통과
            return {s for s, _ in STAGES_ORDER}

        done_actions = self.action_items.filter(status=ActionItemStatus.DONE)
        # prefetch 이용 가능 시 in-memory 필터
        if "action_items" in getattr(self, "_prefetched_objects_cache", {}):
            done_actions = [
                a for a in self._prefetched_objects_cache["action_items"]
                if a.status == ActionItemStatus.DONE
            ]

        for action in done_actions:
            code = action.action_type.code
            if code == STAGE_SKIPPED_ACTION_CODE:
                skipped_id = (action.result or "").strip()
                if skipped_id in dict(STAGES_ORDER):
                    passed.add(skipped_id)
            else:
                stage_id = STAGE_FROM_ACTION_TYPE.get(code)
                if stage_id and STAGE_GATES.get(stage_id) == code:
                    passed.add(stage_id)
        return passed

    @property
    def current_stage(self) -> str | None:
        """현재 진행 단계 ID. hired면 'hired', dropped면 None."""
        if self.dropped_at:
            return None
        if self.hired_at:
            return "hired"
        passed = self.stages_passed
        for stage_id, _ in STAGES_ORDER:
            if stage_id not in passed:
                return stage_id
        return "hired"

    @property
    def current_stage_label(self) -> str:
        """현재 단계의 표시 이름."""
        stage_id = self.current_stage
        if not stage_id:
            return ""
        return dict(STAGES_ORDER).get(stage_id, "")

    @property
    def current_stage_action_codes(self) -> list[str]:
        """현재 단계에 속하는 ActionType.code 리스트 (UI에서 할 일 필터링용)."""
        sid = self.current_stage
        if not sid:
            return []
        return [code for code, s in STAGE_FROM_ACTION_TYPE.items() if s == sid]

    @property
    def current_stage_gate_action(self):
        """현재 단계의 gate ActionType 인스턴스. 없으면 None (sourcing은 gate 없음)."""
        code = STAGE_GATES.get(self.current_stage)
        if not code:
            return None
        return ActionType.objects.filter(code=code).first()

    @property
    def current_stage_pending_actions(self):
        """현재 단계에 속하는 pending ActionItem 리스트."""
        codes = set(self.current_stage_action_codes)
        if not codes:
            return []
        if "action_items" in getattr(self, "_prefetched_objects_cache", {}):
            return [
                a for a in self._prefetched_objects_cache["action_items"]
                if a.status == ActionItemStatus.PENDING
                and a.action_type.code in codes
            ]
        return list(
            self.action_items.filter(
                status=ActionItemStatus.PENDING,
                action_type__code__in=codes,
            ).select_related("action_type")
        )

    @property
    def pending_actions(self):
        """Pending ActionItems. Works with prefetch_related cache."""
        # If action_items were prefetched, filter in Python to avoid N+1
        if "action_items" in getattr(self, "_prefetched_objects_cache", {}):
            return [
                ai
                for ai in self.action_items.all()
                if ai.status == ActionItemStatus.PENDING
            ]
        return self.action_items.filter(status=ActionItemStatus.PENDING)


# ===========================================================================
# ActionItem
# ===========================================================================


class ActionItemQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=ActionItemStatus.PENDING)

    def done(self):
        return self.filter(status=ActionItemStatus.DONE)

    def overdue(self):
        return self.pending().filter(due_at__lt=timezone.now())

    def due_soon(self, days: int = 3):
        soon = timezone.now() + timedelta(days=days)
        return self.pending().filter(due_at__lte=soon, due_at__gte=timezone.now())

    def for_user(self, user):
        return self.filter(assigned_to=user)


class ActionItem(BaseModel):
    """헤드헌터 업무의 기본 단위. Application에 여러 개 달림."""

    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="action_items",
    )
    action_type = models.ForeignKey(
        ActionType,
        on_delete=models.PROTECT,
        related_name="items",
    )
    title = models.CharField(max_length=300)
    channel = models.CharField(
        max_length=20,
        choices=ActionChannel.choices,
        blank=True,
        default="",
    )
    scheduled_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ActionItemStatus.choices,
        default=ActionItemStatus.PENDING,
        db_index=True,
    )
    result = models.TextField(blank=True)
    note = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_action_items",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_action_items",
    )
    parent_action = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    objects = ActionItemQuerySet.as_manager()

    class Meta:
        ordering = ["due_at", "created_at"]
        indexes = [
            models.Index(fields=["application", "status"]),
            models.Index(fields=["assigned_to", "status", "due_at"]),
            models.Index(fields=["action_type", "status"]),
            models.Index(
                fields=["application", "status", "-completed_at"]
            ),  # E1-8: current_state query support
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_overdue(self) -> bool:
        if self.status != ActionItemStatus.PENDING:
            return False
        if self.due_at is None:
            return False
        return self.due_at < timezone.now()


# ===========================================================================
# Submission (modified — now hangs off ActionItem)
# ===========================================================================


class SubmissionTemplate(models.TextChoices):
    XD_KO = "xd_ko", "엑스다임 국문"
    XD_KO_EN = "xd_ko_en", "엑스다임 국영문"
    XD_EN = "xd_en", "엑스다임 영문"
    CUSTOM = "custom", "고객사 커스텀"


class Submission(BaseModel):
    """고객사 제출 서류. ActionItem(submit_to_client)에 1:1 연결."""

    # Phase 2: clean()/save() validates action_type.code == "submit_to_client"
    action_item = models.OneToOneField(
        ActionItem,
        on_delete=models.CASCADE,
        related_name="submission",
    )
    consultant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="submissions",
    )
    template = models.CharField(
        max_length=20,
        choices=SubmissionTemplate.choices,
        blank=True,
        default="",
    )
    document_file = models.FileField(upload_to="submissions/", blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    client_feedback = models.TextField(blank=True)
    client_feedback_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Submission: {self.action_item.title}"


# ===========================================================================
# SubmissionDraft (unchanged)
# ===========================================================================


class DraftStatus(models.TextChoices):
    PENDING = "pending", "대기"
    DRAFT_GENERATED = "draft_generated", "초안 생성됨"
    CONSULTATION_ADDED = "consultation_added", "상담 입력됨"
    FINALIZED = "finalized", "AI 정리 완료"
    REVIEWED = "reviewed", "검토 완료"
    CONVERTED = "converted", "변환 완료"


class OutputLanguage(models.TextChoices):
    KO = "ko", "국문"
    EN = "en", "영문"
    KO_EN = "ko_en", "국영문"


class OutputFormat(models.TextChoices):
    WORD = "word", "Word"
    PDF = "pdf", "PDF"


DEFAULT_MASKING_CONFIG = {
    "salary": True,
    "birth_detail": True,
    "contact": True,
    "current_company": False,
}


class SubmissionDraft(BaseModel):
    """AI 문서 생성 파이프라인 초안."""

    submission = models.OneToOneField(
        Submission,
        on_delete=models.CASCADE,
        related_name="draft",
    )
    # template은 Submission.template을 참조 — 중복 저장하지 않음
    status = models.CharField(
        max_length=30,
        choices=DraftStatus.choices,
        default=DraftStatus.PENDING,
    )

    # 1단계: AI 초안
    auto_draft_json = models.JSONField(default=dict, blank=True)
    auto_corrections = models.JSONField(default=list, blank=True)

    # 2단계: 상담
    consultation_input = models.TextField(blank=True)
    consultation_audio = models.FileField(upload_to="drafts/audio/", blank=True)
    consultation_transcript = models.TextField(blank=True)
    consultation_summary = models.JSONField(default=dict, blank=True)

    # 3단계: AI 최종 정리
    final_content_json = models.JSONField(default=dict, blank=True)

    # 4단계: 변환 설정
    masking_config = models.JSONField(default=dict, blank=True)
    output_format = models.CharField(
        max_length=10,
        choices=OutputFormat.choices,
        default=OutputFormat.WORD,
    )
    output_language = models.CharField(
        max_length=10,
        choices=OutputLanguage.choices,
        default=OutputLanguage.KO,
    )
    output_file = models.FileField(upload_to="drafts/output/", blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Draft: {self.submission} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        # masking_config 기본값 보장
        if not self.masking_config:
            self.masking_config = DEFAULT_MASKING_CONFIG.copy()
        super().save(*args, **kwargs)


# ===========================================================================
# Interview (modified — now hangs off ActionItem)
# ===========================================================================


class Interview(BaseModel):
    """면접 단계. ActionItem(interview_round)에 1:1 연결."""

    class Type(models.TextChoices):
        IN_PERSON = "대면", "대면"
        VIDEO = "화상", "화상"
        PHONE = "전화", "전화"

    class Result(models.TextChoices):
        PENDING = "대기", "대기"
        PASSED = "합격", "합격"
        ON_HOLD = "보류", "보류"
        FAILED = "탈락", "탈락"

    # Phase 2: clean()/save() validates action_type.code == "interview_round"
    action_item = models.OneToOneField(
        ActionItem,
        on_delete=models.CASCADE,
        related_name="interview",
    )
    round = models.PositiveSmallIntegerField()
    scheduled_at = models.DateTimeField()
    type = models.CharField(max_length=20, choices=Type.choices)
    location = models.CharField(max_length=500, blank=True)
    result = models.CharField(
        max_length=20,
        choices=Result.choices,
        default=Result.PENDING,
    )
    feedback = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["round"]

    def __str__(self) -> str:
        return f"{self.action_item.title} - {self.round}차 면접"

    def clean(self):
        """Validate no duplicate round within the same Application."""
        super().clean()
        if self.action_item_id:
            dup = (
                Interview.objects.filter(
                    action_item__application=self.action_item.application,
                    round=self.round,
                )
                .exclude(pk=self.pk)
                .exists()
            )
            if dup:
                raise ValidationError(
                    f"이 Application에 이미 {self.round}차 면접이 존재합니다."
                )


# ===========================================================================
# MeetingRecord (modified — now hangs off ActionItem)
# ===========================================================================


class MeetingRecord(BaseModel):
    """미팅 녹음 분석 레코드. ActionItem(pre_meeting)에 1:1 연결."""

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "업로드됨"
        TRANSCRIBING = "transcribing", "전사 중"
        ANALYZING = "analyzing", "분석 중"
        READY = "ready", "분석 완료"
        APPLIED = "applied", "반영 완료"
        FAILED = "failed", "실패"

    # Phase 2: clean()/save() validates action_type.code == "pre_meeting"
    action_item = models.OneToOneField(
        ActionItem,
        on_delete=models.CASCADE,
        related_name="meeting_record",
    )
    audio_file = models.FileField(upload_to="meetings/audio/")
    transcript = models.TextField(blank=True)
    analysis_json = models.JSONField(default=dict, blank=True)
    edited_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
    )
    error_message = models.TextField(blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applied_meeting_records",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_meeting_records",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Meeting: {self.action_item.title} ({self.status})"


# ===========================================================================
# ProjectApproval (unchanged)
# ===========================================================================


class ConflictType(models.TextChoices):
    HIGH = "높은중복", "높은 중복 가능성"
    MEDIUM = "참고정보", "참고 정보"


class ProjectApproval(BaseModel):
    """충돌 감지 승인 요청."""

    class Status(models.TextChoices):
        PENDING = "대기", "대기"
        APPROVED = "승인", "승인"
        JOINED = "합류", "합류"
        REJECTED = "반려", "반려"

    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approvals",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="approval_requests",
    )
    conflict_project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conflict_approvals",
    )
    conflict_score = models.FloatField(default=0.0)
    conflict_type = models.CharField(
        max_length=20,
        choices=ConflictType.choices,
        blank=True,
        default="",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    message = models.TextField(blank=True)
    admin_response = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_decisions",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Approval: {self.project} ({self.status})"


# ===========================================================================
# ProjectContext (unchanged)
# ===========================================================================


class ProjectContext(BaseModel):
    """업무 연속성 컨텍스트."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="contexts",
    )
    consultant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="project_contexts",
    )
    last_step = models.CharField(max_length=100, blank=True)
    pending_action = models.CharField(max_length=100, blank=True)
    draft_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "consultant"],
                name="unique_context_per_project_consultant",
            )
        ]

    def __str__(self) -> str:
        return f"Context: {self.project} - {self.consultant}"


# ===========================================================================
# Notification (unchanged)
# ===========================================================================


class Notification(BaseModel):
    """알림 시스템."""

    class Type(models.TextChoices):
        APPROVAL_REQUEST = "approval_request", "승인 요청"
        AUTO_GENERATED = "auto_generated", "자동 생성"
        REMINDER = "reminder", "리마인더"
        NEWS = "news", "뉴스"

    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        SENT = "sent", "전송됨"
        READ = "read", "읽음"
        ACTED = "acted", "처리됨"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=30, choices=Type.choices)
    title = models.CharField(max_length=300)
    body = models.TextField()
    action_url = models.URLField(blank=True)
    telegram_message_id = models.CharField(max_length=100, blank=True)
    telegram_chat_id = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    callback_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


# ===========================================================================
# PostingSite (unchanged)
# ===========================================================================


class PostingSiteChoice(models.TextChoices):
    JOBKOREA = "jobkorea", "잡코리아"
    SARAMIN = "saramin", "사람인"
    INCRUIT = "incruit", "인크루트"
    LINKEDIN = "linkedin", "LinkedIn"
    WANTED = "wanted", "원티드"
    CATCH = "catch", "캐치"
    OTHER = "other", "기타"


class PostingSite(BaseModel):
    """포스팅 사이트별 게시 현황."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="posting_sites",
    )
    site = models.CharField(
        max_length=20,
        choices=PostingSiteChoice.choices,
    )
    posted_at = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    applicant_count = models.PositiveIntegerField(default=0)
    url = models.URLField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "site"],
                name="unique_posting_site_per_project",
            )
        ]

    def __str__(self) -> str:
        return f"{self.project} - {self.get_site_display()}"


# ===========================================================================
# AutoAction (preserved — action_type choices removed per Phase 6 plan)
# ===========================================================================


class ActionStatusChoice(models.TextChoices):
    PENDING = "pending", "대기"
    APPLIED = "applied", "적용됨"
    DISMISSED = "dismissed", "무시됨"


class AutoAction(BaseModel):
    """이벤트 기반 자동 생성물."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="auto_actions",
    )
    trigger_event = models.CharField(max_length=100)
    # choices removed — was old ActionType(TextChoices).
    # Phase 6 will redesign this model entirely.
    action_type = models.CharField(max_length=30)
    title = models.CharField(max_length=300)
    data = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ActionStatusChoice.choices,
        default=ActionStatusChoice.PENDING,
    )
    due_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_auto_actions",
    )
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applied_auto_actions",
    )
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dismissed_auto_actions",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"AutoAction: {self.title} ({self.status})"


# ===========================================================================
# News (unchanged)
# ===========================================================================


class NewsSourceType(models.TextChoices):
    RSS = "rss", "RSS/뉴스"
    YOUTUBE = "youtube", "YouTube"
    BLOG = "blog", "블로그"


class NewsCategory(models.TextChoices):
    HIRING = "hiring", "채용"
    HR = "hr", "인사"
    INDUSTRY = "industry", "업계동향"
    ECONOMY = "economy", "경제/실업"


class SummaryStatus(models.TextChoices):
    PENDING = "pending", "대기"
    COMPLETED = "completed", "완료"
    FAILED = "failed", "실패"


class NewsSource(BaseModel):
    """뉴스 소스 (RSS 피드)."""

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="news_sources",
    )
    name = models.CharField(max_length=200)
    url = models.URLField()
    type = models.CharField(
        max_length=20,
        choices=NewsSourceType.choices,
        default=NewsSourceType.RSS,
    )
    category = models.CharField(
        max_length=20,
        choices=NewsCategory.choices,
    )
    is_active = models.BooleanField(default=True)
    last_fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class NewsArticle(BaseModel):
    """뉴스 기사."""

    source = models.ForeignKey(
        NewsSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
    )
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    raw_content = models.TextField(blank=True)
    url = models.URLField(unique=True)
    published_at = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    category = models.CharField(
        max_length=20,
        choices=NewsCategory.choices,
        blank=True,
    )
    summary_status = models.CharField(
        max_length=20,
        choices=SummaryStatus.choices,
        default=SummaryStatus.PENDING,
    )

    class Meta:
        ordering = ["-published_at"]

    def __str__(self) -> str:
        return self.title


class NewsArticleRelevance(BaseModel):
    """기사-프로젝트 관련도 (정규화 조인 모델)."""

    article = models.ForeignKey(
        NewsArticle,
        on_delete=models.CASCADE,
        related_name="relevances",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="news_relevances",
    )
    score = models.FloatField()
    matched_terms = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-score"]
        constraints = [
            models.UniqueConstraint(
                fields=["article", "project"],
                name="unique_article_project_relevance",
            )
        ]

    def __str__(self) -> str:
        return f"{self.article.title} -> {self.project.title} ({self.score:.2f})"


# ===========================================================================
# ResumeUpload (unchanged)
# ===========================================================================


class ResumeUpload(BaseModel):
    """이력서 업로드 및 추출 추적."""

    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        DOCX = "docx", "Word (DOCX)"
        DOC = "doc", "Word (DOC)"

    class Source(models.TextChoices):
        MANUAL = "manual", "수동 업로드"
        EMAIL = "email", "이메일"

    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        EXTRACTING = "extracting", "추출중"
        EXTRACTED = "extracted", "추출완료"
        LINKED = "linked", "후보자 연결됨"
        DUPLICATE = "duplicate", "중복"
        FAILED = "failed", "실패"
        DISCARDED = "discarded", "폐기"

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="resume_uploads",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resume_uploads",
    )
    file = models.FileField(upload_to="resumes/uploads/")
    file_name = models.CharField(max_length=500)
    file_type = models.CharField(max_length=10, choices=FileType.choices)
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.MANUAL
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    candidate = models.ForeignKey(
        "candidates.Candidate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resume_uploads",
    )
    extraction_result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    last_attempted_at = models.DateTimeField(null=True, blank=True)

    # Email source fields
    email_subject = models.CharField(max_length=500, blank=True)
    email_from = models.EmailField(blank=True)
    email_message_id = models.CharField(max_length=255, blank=True)
    email_attachment_id = models.CharField(max_length=255, blank=True)

    # Upload batch tracking
    upload_batch = models.UUIDField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resume_uploads",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "email_message_id", "email_attachment_id"],
                condition=models.Q(source="email"),
                name="unique_email_attachment_per_org",
            ),
        ]

    def __str__(self) -> str:
        return f"ResumeUpload: {self.file_name} ({self.get_status_display()})"
