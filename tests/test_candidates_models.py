import pytest
from django.db import IntegrityError
from django.utils import timezone

from candidates.models import (
    Candidate,
    Career,
    Category,
    Certification,
    DiscrepancyReport,
    Education,
    ExtractionLog,
    LanguageSkill,
    Resume,
)


# --- Category ---


class TestCategory:
    @pytest.mark.django_db
    def test_create_category(self):
        cat = Category.objects.create(name="TestCat", name_ko="테스트")
        assert cat.name == "TestCat"
        assert cat.name_ko == "테스트"
        assert cat.candidate_count == 0
        assert cat.id is not None  # UUID PK

    @pytest.mark.django_db
    def test_unique_name(self):
        Category.objects.create(name="UniqueTest")
        with pytest.raises(IntegrityError):
            Category.objects.create(name="UniqueTest")

    @pytest.mark.django_db
    def test_str_with_ko(self):
        cat = Category.objects.create(name="HR", name_ko="인사")
        assert str(cat) == "HR (인사)"

    @pytest.mark.django_db
    def test_str_without_ko(self):
        cat = Category.objects.create(name="HR", name_ko="")
        assert str(cat) == "HR"


# --- Candidate ---


class TestCandidate:
    @pytest.mark.django_db
    def test_create_with_category(self):
        cat = Category.objects.create(name="Sales", name_ko="영업")
        candidate = Candidate.objects.create(
            name="김철수",
            current_company="테스트주식회사",
            current_position="과장",
            primary_category=cat,
        )
        candidate.categories.add(cat)
        assert candidate.name == "김철수"
        assert candidate.primary_category == cat
        assert cat in candidate.categories.all()

    @pytest.mark.django_db
    def test_default_status(self):
        candidate = Candidate.objects.create(name="이영희")
        assert candidate.status == "active"

    @pytest.mark.django_db
    def test_default_validation_status(self):
        candidate = Candidate.objects.create(name="박민수")
        assert candidate.validation_status == "needs_review"

    @pytest.mark.django_db
    def test_str_name_only(self):
        candidate = Candidate.objects.create(name="김철수")
        assert str(candidate) == "김철수"

    @pytest.mark.django_db
    def test_str_with_company_and_position(self):
        candidate = Candidate.objects.create(
            name="김철수",
            current_company="삼성전자",
            current_position="부장",
        )
        assert str(candidate) == "김철수 / 삼성전자 / 부장"

    @pytest.mark.django_db
    def test_json_fields_default(self):
        candidate = Candidate.objects.create(name="테스트")
        assert candidate.core_competencies == []
        assert candidate.raw_extracted_json == {}
        assert candidate.field_confidences == {}

    @pytest.mark.django_db
    def test_phone_normalized_is_populated_on_create(self):
        candidate = Candidate.objects.create(
            name="전화정규화",
            phone="+82-10-1234-5678 / 02-123-4567",
        )

        assert candidate.phone_normalized == "01012345678"

    @pytest.mark.django_db
    def test_phone_normalized_updates_when_phone_saved_with_update_fields(self):
        candidate = Candidate.objects.create(
            name="전화변경",
            phone="010-1111-2222",
        )

        candidate.phone = "+82-10-9999-8888"
        candidate.save(update_fields=["phone", "updated_at"])
        candidate.refresh_from_db()

        assert candidate.phone_normalized == "01099998888"

    @pytest.mark.django_db
    def test_total_experience_display_uses_merged_career_periods(self, monkeypatch):
        monkeypatch.setattr(
            timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
        )
        candidate = Candidate.objects.create(name="경력합산", total_experience_years=8)
        Career.objects.create(
            candidate=candidate,
            company="첫회사",
            start_date="2020-01",
            end_date="2021-12",
        )
        Career.objects.create(
            candidate=candidate,
            company="둘째회사",
            start_date="2021-06",
            end_date="2023-03",
        )
        Career.objects.create(
            candidate=candidate,
            company="현재회사",
            start_date="2023-05",
            end_date="",
            is_current=True,
        )

        assert candidate.computed_total_experience_months == 75
        assert candidate.total_experience_display == "6년 3개월"
        assert candidate.extracted_total_experience_display == "8년"
        assert candidate.has_experience_discrepancy is True

    @pytest.mark.django_db
    def test_experience_notice_uses_resume_reference_date_before_flagging_discrepancy(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
        )
        candidate = Candidate.objects.create(
            name="기준일반영",
            total_experience_years=10,
            resume_reference_date="2021-12",
            resume_reference_date_source=Candidate.ResumeReferenceDateSource.FILE_MODIFIED_TIME,
        )
        Career.objects.create(
            candidate=candidate,
            company="첫회사",
            start_date="2012-01",
            end_date="2016-12",
        )
        Career.objects.create(
            candidate=candidate,
            company="현재회사",
            start_date="2017-01",
            end_date="",
            is_current=True,
        )

        assert candidate.reference_total_experience_display == "10년"
        assert candidate.total_experience_display == "14년 4개월"
        assert candidate.has_experience_discrepancy is False
        # info-level notice removed — both values now shown inline in 총 경력 field
        assert candidate.experience_notice_tone == ""
        assert candidate.experience_notice_text == ""

    @pytest.mark.django_db
    def test_experience_notice_can_infer_reference_date_from_current_career(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
        )
        candidate = Candidate.objects.create(
            name="추정기준일",
            total_experience_years=10,
        )
        Career.objects.create(
            candidate=candidate,
            company="첫회사",
            start_date="2012-01",
            end_date="2016-12",
        )
        Career.objects.create(
            candidate=candidate,
            company="현재회사",
            start_date="2017-01",
            end_date="",
            is_current=True,
        )

        assert (
            candidate.effective_resume_reference_source
            == Candidate.ResumeReferenceDateSource.INFERRED
        )
        assert candidate.effective_resume_reference_date_display == "2021.12"
        assert candidate.has_experience_discrepancy is False
        # info-level notice removed — both values now shown inline in 총 경력 field
        assert candidate.experience_notice_tone == ""
        assert candidate.experience_notice_text == ""

    @pytest.mark.django_db
    def test_total_experience_caps_future_end_dates(self, monkeypatch):
        monkeypatch.setattr(
            timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
        )
        candidate = Candidate.objects.create(name="미래날짜")
        Career.objects.create(
            candidate=candidate,
            company="오타회사",
            start_date="2024-01",
            end_date="2029-04",
        )

        assert candidate.computed_total_experience_months == 28
        assert candidate.total_experience_display == "2년 4개월"
        assert candidate.capped_future_career_count == 1

    @pytest.mark.django_db
    def test_total_experience_falls_back_to_extracted_years_without_valid_careers(self):
        candidate = Candidate.objects.create(
            name="추출값만존재", total_experience_years=11
        )
        Career.objects.create(
            candidate=candidate,
            company="불완전경력",
            start_date="미정",
            end_date="2023-06",
        )

        assert candidate.computed_total_experience_months is None
        assert candidate.total_experience_display == "11년"
        assert candidate.ignored_career_count == 1

    @pytest.mark.django_db
    def test_total_experience_uses_duration_hint_from_raw_text(self):
        candidate = Candidate.objects.create(
            name="기간보정",
            raw_text=(
                "|2004/06/21 ~ |야후코리아 |\n"
                "|(1 년7 개월) |부서명 : 파이낸스 (사원) |\n"
            ),
        )
        career = Career.objects.create(
            candidate=candidate,
            company="야후코리아",
            start_date="2004-06-21",
            end_date="",
            is_current=False,
        )

        assert career.uses_duration_inference() is True
        assert career.end_date_display == "2005-12"
        assert career.duration_display == "1년 7개월"
        assert candidate.computed_total_experience_months == 19
        assert candidate.duration_adjusted_career_count == 1
        assert candidate.ignored_career_count == 0
        assert (
            "기간 정보가 있는 경력 1건은 종료일을 보정해 총 경력 계산에 반영했습니다."
            in (candidate.experience_review_notice_items[0]["detail"])
        )

    @pytest.mark.django_db
    def test_total_experience_prefers_structured_inference_fields(self):
        candidate = Candidate.objects.create(name="구조화보정")
        career = Career.objects.create(
            candidate=candidate,
            company="야후코리아",
            start_date="2004-06-21",
            end_date="",
            duration_text="1년 7개월",
            end_date_inferred="2005-12",
            date_evidence="2004/06/21 ~ / (1년 7개월)",
            date_confidence=0.88,
            is_current=False,
        )

        assert career.inferred_duration_months == 19
        assert career.inferred_end_year_month == (2005, 12)
        assert career.end_date_display == "2005-12"
        assert candidate.computed_total_experience_months == 19
        assert candidate.duration_adjusted_career_count == 1

    @pytest.mark.django_db
    def test_experience_review_notice_items_use_reference_severity_for_info_cases(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
        )
        candidate = Candidate.objects.create(
            name="안내용후보",
            total_experience_years=10,
        )
        Career.objects.create(
            candidate=candidate,
            company="첫회사",
            start_date="2012-01",
            end_date="2016-12",
        )
        Career.objects.create(
            candidate=candidate,
            company="현재회사",
            start_date="2017-01",
            end_date="",
            is_current=True,
        )

        items = candidate.experience_review_notice_items
        # info-level experience notice removed — shown inline in 총 경력 field
        experience_ref_items = [
            i for i in items if i.get("type") == "EXPERIENCE_REFERENCE_NOTICE"
        ]
        assert experience_ref_items == []

    @pytest.mark.django_db
    def test_review_notice_items_merge_report_and_experience_fallback(
        self, monkeypatch
    ):
        monkeypatch.setattr(
            timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
        )
        candidate = Candidate.objects.create(name="통합노출", total_experience_years=8)
        Career.objects.create(
            candidate=candidate,
            company="현재회사",
            start_date="2018-01",
            end_date="",
            is_current=True,
        )
        Career.objects.create(
            candidate=candidate,
            company="불완전경력",
            start_date="미정",
            end_date="2023-06",
        )
        DiscrepancyReport.objects.create(
            candidate=candidate,
            report_type=DiscrepancyReport.ReportType.SELF_CONSISTENCY,
            integrity_score=0.97,
            summary="참고 1건",
            alerts=[
                {
                    "type": "MISSING_UNDERGRAD",
                    "severity": "BLUE",
                    "field": "educations",
                    "layer": "self_consistency",
                    "detail": "학력 정보가 석사 이상만 있고 학부 정보가 보이지 않습니다.",
                }
            ],
        )

        items = candidate.review_notice_items

        assert len(items) == 2
        assert candidate.review_notice_blue_count == 2
        assert any("학부 정보가 보이지 않습니다" in item["detail"] for item in items)
        assert any("총 경력 계산에서 제외" in item["detail"] for item in items)


# --- Resume ---


class TestResume:
    @pytest.mark.django_db
    def test_create_resume(self):
        resume = Resume.objects.create(
            file_name="이력서_김철수.pdf",
            drive_file_id="abc123",
        )
        assert resume.file_name == "이력서_김철수.pdf"
        assert resume.processing_status == "pending"
        assert resume.candidate is None  # nullable FK

    @pytest.mark.django_db
    def test_unique_drive_file_id(self):
        Resume.objects.create(file_name="a.pdf", drive_file_id="unique1")
        with pytest.raises(IntegrityError):
            Resume.objects.create(file_name="b.pdf", drive_file_id="unique1")

    @pytest.mark.django_db
    def test_str(self):
        resume = Resume.objects.create(
            file_name="이력서.docx",
            drive_file_id="xyz",
        )
        assert str(resume) == "이력서.docx"


# --- Relations ---


class TestRelations:
    @pytest.fixture
    def candidate(self, db):
        return Candidate.objects.create(
            name="관계테스트",
            current_company="테스트사",
        )

    def test_candidate_resumes(self, candidate):
        Resume.objects.create(
            candidate=candidate,
            file_name="resume1.pdf",
            drive_file_id="r1",
        )
        Resume.objects.create(
            candidate=candidate,
            file_name="resume2.pdf",
            drive_file_id="r2",
        )
        assert candidate.resumes.count() == 2

    def test_candidate_careers(self, candidate):
        Career.objects.create(
            candidate=candidate,
            company="삼성전자",
            position="과장",
            start_date="2020.01",
            end_date="2023.12",
        )
        assert candidate.careers.count() == 1
        career = candidate.careers.first()
        assert career.company == "삼성전자"

    def test_candidate_educations(self, candidate):
        Education.objects.create(
            candidate=candidate,
            institution="서울대학교",
            degree="학사",
            major="경영학",
            end_year=2015,
        )
        assert candidate.educations.count() == 1

    def test_candidate_certifications(self, candidate):
        Certification.objects.create(
            candidate=candidate,
            name="CPA",
            issuer="금융감독원",
            acquired_date="2020.05",
        )
        assert candidate.certifications.count() == 1

    def test_candidate_language_skills(self, candidate):
        LanguageSkill.objects.create(
            candidate=candidate,
            language="영어",
            test_name="TOEIC",
            score="950",
        )
        assert candidate.language_skills.count() == 1

    def test_extraction_log(self, candidate):
        resume = Resume.objects.create(
            candidate=candidate,
            file_name="test.pdf",
            drive_file_id="log_test",
        )
        log = ExtractionLog.objects.create(
            candidate=candidate,
            resume=resume,
            action=ExtractionLog.Action.AUTO_EXTRACT,
            field_name="name",
            old_value="",
            new_value="관계테스트",
            confidence=0.95,
        )
        assert candidate.extraction_logs.count() == 1
        assert log.action == "auto_extract"
        assert log.confidence == 0.95
        assert str(log) == "자동 추출 - name"


class TestCareer:
    @pytest.fixture
    def candidate(self, db):
        return Candidate.objects.create(name="경력테스트")

    @pytest.mark.django_db
    def test_duration_display_with_explicit_end_date(self, candidate):
        career = Career.objects.create(
            candidate=candidate,
            company="테스트회사",
            start_date="2020-01",
            end_date="2023-06",
        )

        assert career.duration_months == 42
        assert career.duration_display == "3년 6개월"

    @pytest.mark.django_db
    def test_duration_display_for_current_job(self, candidate, monkeypatch):
        monkeypatch.setattr(
            timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
        )
        career = Career.objects.create(
            candidate=candidate,
            company="현재회사",
            start_date="2025.02",
            end_date="",
            is_current=True,
        )

        assert career.duration_months == 15
        assert career.duration_display == "1년 3개월"

    @pytest.mark.django_db
    def test_duration_display_returns_empty_for_invalid_dates(self, candidate):
        career = Career.objects.create(
            candidate=candidate,
            company="날짜오류회사",
            start_date="미정",
            end_date="2023-06",
        )

        assert career.duration_months is None
        assert career.duration_display == ""
