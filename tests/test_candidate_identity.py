import pytest

from candidates.models import Candidate, Career, Category, Education, Resume


@pytest.fixture
def category(db):
    return Category.objects.create(name="HR", name_ko="인사")


@pytest.fixture
def existing_candidate(db, category):
    c = Candidate.objects.create(
        name="김철수",
        email="kim@example.com",
        phone="010-1234-5678",
        primary_category=category,
    )
    Resume.objects.create(
        candidate=c,
        file_name="김철수_v1.pdf",
        drive_file_id="drive_v1",
        drive_folder="HR",
        is_primary=True,
        version=1,
        processing_status=Resume.ProcessingStatus.PARSED,
    )
    return c


class TestIdentifyByEmail:
    def test_match_by_email(self, existing_candidate):
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"email": "kim@example.com", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is not None
        assert result.candidate == existing_candidate
        assert result.match_reason == "email"

    def test_no_match_different_email(self, existing_candidate):
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"email": "park@example.com", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is None

    def test_no_match_empty_email(self, existing_candidate):
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"email": "", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is None


class TestIdentifyByPhone:
    def test_match_by_phone_exact(self, existing_candidate):
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"phone": "010-1234-5678", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is not None
        assert result.candidate == existing_candidate
        assert result.match_reason == "phone"

    def test_match_by_phone_normalized(self, existing_candidate):
        """Different formatting but same number."""
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"phone": "01012345678", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is not None
        assert result.candidate == existing_candidate

    def test_no_match_different_phone(self, existing_candidate):
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"phone": "010-9999-8888", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is None

    def test_match_by_phone_korean_country_code(self, existing_candidate):
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"phone": "+82-10-1234-5678", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is not None
        assert result.candidate == existing_candidate
        assert result.match_reason == "phone"


class TestIdentifyNoAutoMergeByName:
    def test_same_name_different_person_no_merge(self, existing_candidate):
        """Same name but no email/phone match -> must NOT auto-merge."""
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"name": "김철수", "email": "", "phone": ""}
        result = identify_candidate(extracted)
        assert result is None

    def test_same_name_no_contact_info(self, existing_candidate):
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"name": "김철수"}
        result = identify_candidate(extracted)
        assert result is None


class TestIdentifyPreviousResume:
    def test_compared_resume_returned(self, existing_candidate):
        """Should return the latest parsed resume for cross-version comparison."""
        from candidates.services.candidate_identity import identify_candidate

        extracted = {"email": "kim@example.com", "name": "김철수"}
        result = identify_candidate(extracted)
        assert result is not None
        assert result.compared_resume is not None
        assert result.compared_resume.drive_file_id == "drive_v1"


class TestComparisonContext:
    def test_builds_previous_data_from_matched_candidate(self, db, category):
        from candidates.services.candidate_identity import build_candidate_comparison_context

        candidate = Candidate.objects.create(
            name="김철수",
            email="kim@example.com",
            phone="010-1234-5678",
            primary_category=category,
        )
        current_resume = Resume.objects.create(
            candidate=candidate,
            file_name="김철수_v2.pdf",
            drive_file_id="drive_v2",
            drive_folder="HR",
            is_primary=True,
            version=2,
            processing_status=Resume.ProcessingStatus.PARSED,
        )
        candidate.current_resume = current_resume
        candidate.save(update_fields=["current_resume", "updated_at"])
        Career.objects.create(
            candidate=candidate,
            company="A사",
            start_date="2020-01",
            end_date="2022-06",
            position="과장",
        )
        Education.objects.create(
            candidate=candidate,
            institution="서울대",
            degree="학사",
            major="경영",
            start_year=2010,
            end_year=2014,
        )

        context = build_candidate_comparison_context(
            {"email": "kim@example.com", "phone": "01012345678"}
        )

        assert context is not None
        assert context.candidate == candidate
        assert context.compared_resume == current_resume
        assert context.previous_data["careers"][0]["company"] == "A사"
        assert context.previous_data["educations"][0]["institution"] == "서울대"
