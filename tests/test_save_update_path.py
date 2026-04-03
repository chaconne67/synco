import pytest
from candidates.models import (
    Candidate, Career, Category, DiscrepancyReport, Education, Resume, ValidationDiagnosis,
)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Finance", name_ko="재무")


def _make_pipeline_result(*, name="테스트", email="test@test.com", phone="010-0000-0000"):
    return {
        "extracted": {
            "name": name, "email": email, "phone": phone,
            "birth_year": 1990,
            "careers": [{"company": "A사", "start_date": "2020.01", "end_date": "2022.06",
                         "is_current": False, "position": "개발자", "order": 0}],
            "educations": [{"institution": "서울대", "degree": "학사", "major": "컴퓨터",
                            "start_year": 2010, "end_year": 2014}],
            "certifications": [], "language_skills": [],
        },
        "diagnosis": {"verdict": "pass", "overall_score": 0.9, "issues": [], "field_scores": {}},
        "attempts": 1, "retry_action": "none", "raw_text_used": "이력서 텍스트",
        "integrity_flags": [],
    }


def _make_primary_file(file_id="drive_001"):
    return {"file_name": "test_resume.pdf", "file_id": file_id,
            "mime_type": "application/pdf", "file_size": 1000}


class TestSaveNewCandidate:
    def test_creates_new_candidate_when_no_match(self, category):
        from candidates.services.integrity.save import save_pipeline_result
        result = save_pipeline_result(
            pipeline_result=_make_pipeline_result(),
            raw_text="이력서 텍스트", category=category,
            primary_file=_make_primary_file(),
        )
        assert result is not None
        assert Candidate.objects.count() == 1
        assert Resume.objects.filter(candidate=result).count() == 1
        assert result.current_resume is not None
        assert result.current_resume.version == 1


class TestSaveUpdateExisting:
    def test_reuses_candidate_on_match(self, category):
        from candidates.services.integrity.save import save_pipeline_result
        c1 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v1",
            category=category, primary_file=_make_primary_file("drive_001"),
        )
        c2 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v2",
            category=category, primary_file=_make_primary_file("drive_002"),
        )
        assert c2.id == c1.id
        assert Candidate.objects.count() == 1
        assert Resume.objects.filter(candidate=c2).count() == 2

    def test_version_increments(self, category):
        from candidates.services.integrity.save import save_pipeline_result
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v1",
            category=category, primary_file=_make_primary_file("drive_001"),
        )
        c2 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v2",
            category=category, primary_file=_make_primary_file("drive_002"),
        )
        assert c2.current_resume.version == 2

    def test_current_resume_updated(self, category):
        from candidates.services.integrity.save import save_pipeline_result
        c1 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v1",
            category=category, primary_file=_make_primary_file("drive_001"),
        )
        old_resume = c1.current_resume
        c2 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v2",
            category=category, primary_file=_make_primary_file("drive_002"),
        )
        assert c2.current_resume != old_resume
        assert c2.current_resume.version == 2

    def test_only_latest_resume_remains_primary(self, category):
        from candidates.services.integrity.save import save_pipeline_result
        c1 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v1",
            category=category, primary_file=_make_primary_file("drive_001"),
        )
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v2",
            category=category, primary_file=_make_primary_file("drive_002"),
        )

        primary_resumes = Resume.objects.filter(candidate=c1, is_primary=True)
        assert primary_resumes.count() == 1
        assert primary_resumes.first().drive_file_id == "drive_002"

    def test_careers_rebuilt_on_update(self, category):
        from candidates.services.integrity.save import save_pipeline_result
        c1 = save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v1",
            category=category, primary_file=_make_primary_file("drive_001"),
        )
        assert Career.objects.filter(candidate=c1).count() == 1
        result2 = _make_pipeline_result()
        result2["extracted"]["careers"].append(
            {"company": "B사", "start_date": "2022.07", "end_date": "2024.01",
             "is_current": False, "position": "시니어", "order": 1}
        )
        c2 = save_pipeline_result(
            pipeline_result=result2, raw_text="v2",
            category=category, primary_file=_make_primary_file("drive_002"),
        )
        assert Career.objects.filter(candidate=c2).count() == 2

    def test_validation_diagnosis_per_resume(self, category):
        from candidates.services.integrity.save import save_pipeline_result
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v1",
            category=category, primary_file=_make_primary_file("drive_001"),
        )
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v2",
            category=category, primary_file=_make_primary_file("drive_002"),
        )
        assert ValidationDiagnosis.objects.count() == 2


class TestComparedResumeSaved:
    def test_compared_resume_set_on_update(self, category):
        from candidates.services.integrity.save import save_pipeline_result
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v1",
            category=category, primary_file=_make_primary_file("drive_001"),
        )
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v2",
            category=category, primary_file=_make_primary_file("drive_002"),
        )
        report = DiscrepancyReport.objects.order_by("-created_at").first()
        assert report.compared_resume is not None
        assert report.compared_resume.drive_file_id == "drive_001"

    def test_compared_resume_none_on_first_import(self, category):
        from candidates.services.integrity.save import save_pipeline_result
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(), raw_text="v1",
            category=category, primary_file=_make_primary_file("drive_001"),
        )
        report = DiscrepancyReport.objects.first()
        assert report.compared_resume is None


class TestNoMergeByNameOnly:
    def test_different_email_creates_new_candidate(self, category):
        from candidates.services.integrity.save import save_pipeline_result
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(name="김철수", email="kim1@test.com", phone="010-1111-1111"),
            raw_text="v1", category=category, primary_file=_make_primary_file("drive_001"),
        )
        save_pipeline_result(
            pipeline_result=_make_pipeline_result(name="김철수", email="kim2@test.com", phone="010-2222-2222"),
            raw_text="v2", category=category, primary_file=_make_primary_file("drive_002"),
        )
        assert Candidate.objects.count() == 2
