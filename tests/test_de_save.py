import pytest
from candidates.models import (
    Candidate,
    Career,
    Category,
    DiscrepancyReport,
    Resume,
    ValidationDiagnosis,
)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Finance", name_ko="재무")


def _make_pipeline_result(
    *, name="테스트", email="test@test.com", phone="010-0000-0000"
):
    return {
        "extracted": {
            "name": name,
            "email": email,
            "phone": phone,
            "birth_year": 1990,
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020.01",
                    "end_date": "2022.06",
                    "is_current": False,
                    "position": "개발자",
                    "order": 0,
                }
            ],
            "educations": [
                {
                    "institution": "서울대",
                    "degree": "학사",
                    "major": "컴퓨터",
                    "start_year": 2010,
                    "end_year": 2014,
                }
            ],
            "certifications": [],
            "language_skills": [],
        },
        "diagnosis": {
            "verdict": "pass",
            "overall_score": 0.9,
            "issues": [],
            "field_scores": {},
        },
        "attempts": 1,
        "retry_action": "none",
        "raw_text_used": "이력서 텍스트",
        "integrity_flags": [],
    }


def _make_primary_file(file_id="drive_001"):
    return {
        "file_name": "test_resume.pdf",
        "file_id": file_id,
        "mime_type": "application/pdf",
        "file_size": 1000,
    }


class TestSaveNewCandidate:
    def test_creates_new_candidate_when_no_match(self, category):
        from data_extraction.services.save import save_pipeline_result

        result = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="이력서 텍스트",
            category=category,
            primary_file=_make_primary_file(),
        )
        assert result is not None
        assert Candidate.objects.count() == 1
        assert Resume.objects.filter(candidate=result).count() == 1
        assert result.current_resume is not None
        assert result.current_resume.version == 1

    def test_sanitizes_multiple_phone_values_before_save(self, category):
        from data_extraction.services.save import save_pipeline_result

        result = _make_pipeline_result(
            phone="+966-5078-50224 / +82-10-9034-5062",
        )

        candidate = save_pipeline_result(
            pipeline_result=result,
            raw_text="이력서 텍스트",
            category=category,
            primary_file=_make_primary_file(),
        )

        assert candidate.phone == "+82-10-9034-5062"
        assert candidate.phone_normalized == "01090345062"

    def test_truncates_overlong_resume_reference_date_before_save(self, category):
        from data_extraction.services.save import save_pipeline_result

        result = _make_pipeline_result()
        result["extracted"]["resume_reference_date"] = (
            "2025-12-31 기준 최신 업데이트 문서 버전"
        )

        candidate = save_pipeline_result(
            pipeline_result=result,
            raw_text="이력서 텍스트",
            category=category,
            primary_file=_make_primary_file(),
        )

        assert len(candidate.resume_reference_date) <= 255

    def test_saves_text_only_resume_when_extraction_missing_but_raw_text_exists(
        self, category
    ):
        from data_extraction.services.save import save_pipeline_result

        pipeline_result = _make_pipeline_result()
        pipeline_result["extracted"] = None

        result = save_pipeline_result(
            pipeline_result=pipeline_result,
            raw_text="자기소개서 형식의 원문 텍스트",
            category=category,
            primary_file=_make_primary_file("drive_text_only"),
        )

        assert result is None
        resume = Resume.objects.get(drive_file_id="drive_text_only")
        assert resume.processing_status == Resume.ProcessingStatus.TEXT_ONLY
        assert resume.raw_text == "자기소개서 형식의 원문 텍스트"
        assert "stored raw text only" in resume.error_message
        assert resume.extraction_state.status == "text_only"
        assert resume.extraction_state.extraction_completed_at is not None


class TestSaveUpdateExisting:
    def test_reuses_candidate_on_match(self, category):
        from data_extraction.services.save import save_pipeline_result

        c1 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        c2 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        assert c2.id == c1.id
        assert Candidate.objects.count() == 1
        assert Resume.objects.filter(candidate=c2).count() == 2

    def test_version_increments(self, category):
        from data_extraction.services.save import save_pipeline_result

        save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        c2 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        assert c2.current_resume.version == 2

    def test_current_resume_updated(self, category):
        from data_extraction.services.save import save_pipeline_result

        c1 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        old_resume = c1.current_resume
        c2 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        assert c2.current_resume != old_resume
        assert c2.current_resume.version == 2

    def test_successful_save_clears_previous_error_message(self, category):
        from data_extraction.services.save import save_pipeline_result

        candidate = Candidate.objects.create(
            name="실패후성공",
            validation_status=Candidate.ValidationStatus.NEEDS_REVIEW,
        )
        Resume.objects.create(
            candidate=candidate,
            file_name="retry.doc",
            drive_file_id="drive_retry_success",
            drive_folder=category.name,
            processing_status=Resume.ProcessingStatus.FAILED,
            error_message="Text quality: empty",
        )

        save_pipeline_result(
            pipeline_result=_make_pipeline_result(name="실패후성공"),
            raw_text="성공한 이력서 텍스트",
            category=category,
            primary_file=_make_primary_file("drive_retry_success"),
        )

        resume = Resume.objects.get(drive_file_id="drive_retry_success")
        assert resume.processing_status == Resume.ProcessingStatus.STRUCTURED
        assert resume.error_message == ""

    def test_only_latest_resume_remains_primary(self, category):
        from data_extraction.services.save import save_pipeline_result

        c1 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )

        primary_resumes = Resume.objects.filter(candidate=c1, is_primary=True)
        assert primary_resumes.count() == 1
        assert primary_resumes.first().drive_file_id == "drive_002"

    def test_careers_rebuilt_on_update(self, category):
        from data_extraction.services.save import save_pipeline_result

        c1 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        assert Career.objects.filter(candidate=c1).count() == 1
        result2 = _make_pipeline_result()
        result2["extracted"]["careers"].append(
            {
                "company": "B사",
                "start_date": "2022.07",
                "end_date": "2024.01",
                "is_current": False,
                "position": "시니어",
                "order": 1,
            }
        )
        c2 = save_pipeline_result(
            pipeline_result=result2,
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        assert Career.objects.filter(candidate=c2).count() == 2

    def test_education_status_persisted_from_extracted(self, category):
        """이력서의 학력 상태(졸업/중퇴/수료/편입)가 Education.status에 저장된다."""
        from candidates.models import Education
        from data_extraction.services.save import save_pipeline_result

        result = _make_pipeline_result()
        result["extracted"]["educations"] = [
            {
                "institution": "서울대",
                "degree": "학사",
                "major": "컴퓨터",
                "start_year": 2010,
                "end_year": 2014,
                "status": "졸업",
            },
            {
                "institution": "연세대",
                "degree": "석사",
                "major": "AI",
                "start_year": 2014,
                "end_year": 2015,
                "status": "수료",
            },
        ]
        candidate = save_pipeline_result(
            pipeline_result=result,
            raw_text="이력서 텍스트",
            category=category,
            primary_file=_make_primary_file("drive_status"),
        )
        statuses = dict(
            Education.objects.filter(candidate=candidate).values_list(
                "institution", "status"
            )
        )
        assert statuses == {"서울대": "졸업", "연세대": "수료"}

    def test_education_status_blank_when_missing(self, category):
        """status가 누락된 경우 빈 문자열로 저장된다 (마이그레이션 default)."""
        from candidates.models import Education
        from data_extraction.services.save import save_pipeline_result

        candidate = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="이력서 텍스트",
            category=category,
            primary_file=_make_primary_file("drive_no_status"),
        )
        edu = Education.objects.get(candidate=candidate)
        assert edu.status == ""

    def test_validation_diagnosis_per_resume(self, category):
        from data_extraction.services.save import save_pipeline_result

        save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        assert ValidationDiagnosis.objects.count() == 2


class TestComparedResumeSaved:
    def test_compared_resume_set_on_update(self, category):
        from data_extraction.services.save import save_pipeline_result

        save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        report = DiscrepancyReport.objects.order_by("-created_at").first()
        assert report.compared_resume is not None
        assert report.compared_resume.drive_file_id == "drive_001"

    def test_compared_resume_none_on_first_import(self, category):
        from data_extraction.services.save import save_pipeline_result

        save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        report = DiscrepancyReport.objects.first()
        assert report.compared_resume is None


class TestNoMergeByNameOnly:
    def test_different_email_creates_new_candidate(self, category):
        from data_extraction.services.save import save_pipeline_result

        save_pipeline_result(
            pipeline_result=_make_pipeline_result(
                name="김철수", email="kim1@test.com", phone="010-1111-1111"
            ),
            raw_text="v1",
            category=category,
            primary_file=_make_primary_file("drive_001"),
        )
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(
                name="김철수", email="kim2@test.com", phone="010-2222-2222"
            ),
            raw_text="v2",
            category=category,
            primary_file=_make_primary_file("drive_002"),
        )
        assert Candidate.objects.count() == 2


class TestIncompleteExtractionPersistence:
    """Only text-bearing incomplete extraction should surface as Candidate."""

    def test_save_failed_resume_records_resume_state_without_candidate(self, db):
        from data_extraction.services.save import save_failed_resume

        file_info = {
            "file_name": "홍길동_90.pdf",
            "file_id": "fail_001",
            "mime_type": "application/pdf",
            "file_size": 500,
        }
        candidate = save_failed_resume(
            file_info,
            "HR",
            "Download failed: 404",
            filename_meta={"name": "홍길동", "birth_year": 1990},
        )
        assert candidate is None
        assert Candidate.objects.count() == 0
        resume = Resume.objects.get(drive_file_id="fail_001")
        assert resume.candidate is None
        assert resume.processing_status == Resume.ProcessingStatus.FAILED
        assert resume.extraction_state.status == "failed"

    def test_save_failed_resume_clears_existing_candidate_link(self, db):
        from data_extraction.services.save import save_failed_resume

        existing = Candidate.objects.create(name="기존후보")
        Resume.objects.create(
            candidate=existing,
            file_name="test.pdf",
            drive_file_id="fail_002",
            processing_status=Resume.ProcessingStatus.TEXT_ONLY,
        )
        file_info = {
            "file_name": "test.pdf",
            "file_id": "fail_002",
            "mime_type": "application/pdf",
            "file_size": 500,
        }
        candidate = save_failed_resume(file_info, "HR", "Text extraction failed")
        resume = Resume.objects.get(drive_file_id="fail_002")
        assert candidate is None
        assert resume.candidate is None
        assert resume.is_primary is False
        assert resume.processing_status == Resume.ProcessingStatus.FAILED
        assert "Text extraction failed" in resume.error_message
        assert resume.extraction_state.status == "failed"
        assert "Text extraction failed" in resume.extraction_state.last_error

    def test_save_text_only_creates_candidate_with_raw_text(self, db):
        from data_extraction.services.save import save_text_only_resume

        file_info = {
            "file_name": "김철수_85.docx",
            "file_id": "text_001",
            "mime_type": "application/vnd.openxmlformats",
            "file_size": 1200,
        }
        candidate = save_text_only_resume(
            file_info,
            "Engineering",
            raw_text="이력서 원문 텍스트 내용",
            error_msg="LLM extraction failed",
            filename_meta={"name": "김철수", "birth_year": 1985},
        )
        assert Candidate.objects.count() == 1
        assert candidate.name == "김철수"
        resume = Resume.objects.get(drive_file_id="text_001")
        assert resume.processing_status == Resume.ProcessingStatus.TEXT_ONLY
        assert resume.raw_text == "이력서 원문 텍스트 내용"
        assert candidate.current_resume == resume
        assert resume.extraction_state.status == "text_only"

    def test_text_only_name_falls_back_to_filename(self, db):
        from data_extraction.services.save import save_text_only_resume

        file_info = {
            "file_name": "resume_unknown.pdf",
            "file_id": "text_005",
            "mime_type": "application/pdf",
            "file_size": 500,
        }
        candidate = save_text_only_resume(
            file_info,
            "HR",
            raw_text="원문 텍스트",
            error_msg="Structured extraction failed",
        )
        assert candidate.name == "resume_unknown.pdf"

    def test_text_only_name_uses_filename_meta(self, db):
        from data_extraction.services.save import save_text_only_resume

        file_info = {
            "file_name": "홍길동_90.pdf",
            "file_id": "text_006",
            "mime_type": "application/pdf",
            "file_size": 500,
        }
        candidate = save_text_only_resume(
            file_info,
            "HR",
            raw_text="원문 텍스트",
            error_msg="Structured extraction failed",
            filename_meta={"name": "홍길동"},
        )
        assert candidate.name == "홍길동"

    def test_save_pipeline_result_empty_raw_text_does_not_create_candidate(self, category):
        from data_extraction.services.save import save_pipeline_result

        pipeline_result = _make_pipeline_result()
        pipeline_result["extracted"] = None

        result = save_pipeline_result(
            pipeline_result=pipeline_result,
            raw_text="",
            category=category,
            primary_file=_make_primary_file("drive_placeholder"),
        )
        assert result is None
        assert Candidate.objects.count() == 0
        resume = Resume.objects.get(drive_file_id="drive_placeholder")
        assert resume.candidate is None
        assert resume.processing_status == Resume.ProcessingStatus.FAILED


class TestNormalizeSkillsForSave:
    def test_new_format_passthrough(self):
        from data_extraction.services.save import _normalize_skills_for_save

        skills = [{"name": "SCM", "description": "공급망 관리"}]
        result = _normalize_skills_for_save(skills)
        assert result == [{"name": "SCM", "description": "공급망 관리"}]

    def test_legacy_string_format(self):
        from data_extraction.services.save import _normalize_skills_for_save

        skills = ["Python", "SAP"]
        result = _normalize_skills_for_save(skills)
        assert result == [
            {"name": "Python", "description": None},
            {"name": "SAP", "description": None},
        ]

    def test_mixed_format(self):
        from data_extraction.services.save import _normalize_skills_for_save

        skills = ["Python", {"name": "SCM", "description": "공급망 관리"}]
        result = _normalize_skills_for_save(skills)
        assert result == [
            {"name": "Python", "description": None},
            {"name": "SCM", "description": "공급망 관리"},
        ]

    def test_empty_list(self):
        from data_extraction.services.save import _normalize_skills_for_save

        assert _normalize_skills_for_save([]) == []


class TestSanitizeFlagDetail:
    """Developer terms in AI flag details should be replaced with Korean."""

    def test_replaces_is_current(self):
        from data_extraction.services.save import _sanitize_flag_detail

        result = _sanitize_flag_detail("is_current가 true이지만 end_date가 존재")
        assert "is_current" not in result
        assert "현재 재직 여부" in result
        assert "end_date" not in result
        assert "종료일" in result

    def test_replaces_boolean_values(self):
        from data_extraction.services.save import _sanitize_flag_detail

        result = _sanitize_flag_detail("값이 true입니다")
        assert "true" not in result
        assert "예" in result

    def test_replaces_false(self):
        from data_extraction.services.save import _sanitize_flag_detail

        result = _sanitize_flag_detail("값이 false입니다")
        assert "false" not in result
        assert "아니오" in result

    def test_replaces_null(self):
        from data_extraction.services.save import _sanitize_flag_detail

        result = _sanitize_flag_detail("필드가 null입니다")
        assert "null" not in result
        assert "미입력" in result

    def test_replaces_boolean_keyword(self):
        from data_extraction.services.save import _sanitize_flag_detail

        result = _sanitize_flag_detail("boolean 타입 필드")
        assert "boolean" not in result
        assert "참/거짓 값" in result

    def test_no_change_for_clean_text(self):
        from data_extraction.services.save import _sanitize_flag_detail

        text = "경력 기간이 겹칩니다"
        result = _sanitize_flag_detail(text)
        assert result == text

    def test_convert_flags_uses_sanitizer(self):
        from data_extraction.services.save import _convert_flags_to_alerts

        flags = [
            {
                "type": "DATE_CONFLICT",
                "severity": "YELLOW",
                "field": "is_current",
                "detail": "is_current가 true이지만 end_date가 존재",
                "chosen": "true",
                "alternative": "false",
                "reasoning": "test",
            },
        ]
        alerts = _convert_flags_to_alerts(flags)
        assert len(alerts) == 1
        assert "is_current" not in alerts[0]["detail"]
        assert "현재 재직 여부" in alerts[0]["detail"]
