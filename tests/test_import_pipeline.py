import pytest

from candidates.models import Candidate, Category, Resume


@pytest.fixture
def accounting_category(db):
    return Category.objects.create(name="Accounting", name_ko="회계")


class TestPipelineIdempotency:
    def test_skip_existing_resume(self, db, accounting_category):
        Resume.objects.create(
            file_name="강솔찬.85.현대.doc",
            drive_file_id="existing_id",
            drive_folder="Accounting",
            processing_status=Resume.ProcessingStatus.STRUCTURED,
        )
        assert Resume.objects.filter(drive_file_id="existing_id").exists()

    def test_failed_resume_not_reprocessed(self, db, accounting_category):
        Resume.objects.create(
            file_name="test.doc",
            drive_file_id="failed_id",
            drive_folder="Accounting",
            processing_status=Resume.ProcessingStatus.FAILED,
        )
        existing = set(
            Resume.objects.filter(drive_file_id__in=["failed_id"]).values_list(
                "drive_file_id", flat=True
            )
        )
        assert "failed_id" in existing


class TestCandidateCreation:
    def test_create_candidate_from_extracted(self, db, accounting_category):
        candidate = Candidate.objects.create(
            name="강솔찬",
            birth_year=1985,
            current_company="현대엠시트",
            primary_category=accounting_category,
            validation_status=Candidate.ValidationStatus.AUTO_CONFIRMED,
            confidence_score=0.92,
            raw_extracted_json={"name": "강솔찬"},
        )
        candidate.categories.add(accounting_category)
        assert candidate.name == "강솔찬"
        assert candidate.validation_status == "auto_confirmed"
        assert accounting_category in candidate.categories.all()


class TestCandidateUpdateOnReimport:
    """Verify that re-importing with same email reuses the Candidate."""

    def test_same_email_reuses_candidate(self, db, accounting_category):
        from candidates.services.integrity.save import save_pipeline_result

        pipeline_result = {
            "extracted": {
                "name": "강솔찬",
                "email": "kang@example.com",
                "phone": "010-1234-5678",
                "birth_year": 1985,
                "current_company": "현대",
                "careers": [],
                "educations": [],
                "certifications": [],
                "language_skills": [],
            },
            "diagnosis": {"verdict": "pass", "overall_score": 0.9, "issues": [], "field_scores": {}},
            "attempts": 1,
            "retry_action": "none",
            "raw_text_used": "텍스트",
            "integrity_flags": [],
        }
        file1 = {"file_name": "강솔찬_v1.pdf", "file_id": "id_v1", "mime_type": "application/pdf"}
        file2 = {"file_name": "강솔찬_v2.pdf", "file_id": "id_v2", "mime_type": "application/pdf"}

        c1 = save_pipeline_result(
            pipeline_result=pipeline_result,
            raw_text="v1",
            category=accounting_category,
            primary_file=file1,
        )
        c2 = save_pipeline_result(
            pipeline_result=pipeline_result,
            raw_text="v2",
            category=accounting_category,
            primary_file=file2,
        )
        assert c1.id == c2.id
        assert Candidate.objects.count() == 1
        assert Resume.objects.filter(candidate=c1).count() == 2
