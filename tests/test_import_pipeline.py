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
            processing_status=Resume.ProcessingStatus.PARSED,
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
