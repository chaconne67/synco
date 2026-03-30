import pytest
from django.db import IntegrityError

from candidates.models import (
    Candidate,
    Career,
    Category,
    Certification,
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
