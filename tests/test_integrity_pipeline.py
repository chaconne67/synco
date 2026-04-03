import pytest
from unittest.mock import patch

from candidates.services.integrity.pipeline import run_integrity_pipeline


MOCK_RAW_DATA = {
    "name": "테스트",
    "name_en": None,
    "birth_year": 1990,
    "gender": None,
    "email": "test@test.com",
    "phone": "010-1234-5678",
    "address": None,
    "total_experience_years": 5,
    "resume_reference_date": None,
    "careers": [
        {"company": "A사", "start_date": "2020.01", "end_date": "2022.06",
         "is_current": False, "source_section": "경력란", "duration_text": None, "duties": None},
    ],
    "educations": [
        {"institution": "서울대", "degree": "학사", "major": "컴퓨터", "start_year": 2010,
         "end_year": 2014, "is_abroad": False, "status": "졸업", "source_section": "학력란"},
    ],
    "certifications": [],
    "language_skills": [],
}

MOCK_CAREER_RESULT = {
    "careers": [
        {"company": "A사", "start_date": "2020-01", "end_date": "2022-06", "is_current": False, "order": 0},
    ],
    "flags": [],
}

MOCK_EDU_RESULT = {
    "educations": [
        {"institution": "서울대", "degree": "학사", "major": "컴퓨터",
         "start_year": 2010, "end_year": 2014, "is_abroad": False},
    ],
    "flags": [],
}


class TestPipelineSuccess:
    @patch("candidates.services.integrity.pipeline.normalize_education_group")
    @patch("candidates.services.integrity.pipeline.normalize_career_group")
    @patch("candidates.services.integrity.pipeline.extract_raw_data")
    @patch("candidates.services.integrity.pipeline.validate_step1")
    def test_full_pipeline(self, mock_v1, mock_s1, mock_s2c, mock_s2e):
        mock_v1.return_value = []
        mock_s1.return_value = MOCK_RAW_DATA
        mock_s2c.return_value = MOCK_CAREER_RESULT
        mock_s2e.return_value = MOCK_EDU_RESULT

        result = run_integrity_pipeline("이력서 텍스트")

        assert result is not None
        assert result["name"] == "테스트"
        assert len(result["careers"]) == 1
        assert result["careers"][0]["order"] == 0
        assert len(result["educations"]) == 1
        assert result["integrity_flags"] == []

    @patch("candidates.services.integrity.pipeline.normalize_education_group")
    @patch("candidates.services.integrity.pipeline.normalize_career_group")
    @patch("candidates.services.integrity.pipeline.extract_raw_data")
    @patch("candidates.services.integrity.pipeline.validate_step1")
    def test_flags_collected(self, mock_v1, mock_s1, mock_s2c, mock_s2e):
        mock_v1.return_value = []
        mock_s1.return_value = MOCK_RAW_DATA
        mock_s2c.return_value = {
            "careers": [{"company": "A사", "start_date": "2020-01", "end_date": "2022-06", "is_current": False, "order": 0}],
            "flags": [{"type": "DATE_CONFLICT", "severity": "RED", "field": "start_date",
                        "detail": "test", "chosen": "a", "alternative": "b", "reasoning": "test"}],
        }
        mock_s2e.return_value = MOCK_EDU_RESULT

        result = run_integrity_pipeline("이력서 텍스트")
        assert len(result["integrity_flags"]) == 1
        assert result["integrity_flags"][0]["type"] == "DATE_CONFLICT"


class TestPipelineFailure:
    @patch("candidates.services.integrity.pipeline.extract_raw_data")
    def test_step1_failure(self, mock_s1):
        mock_s1.return_value = None
        assert run_integrity_pipeline("텍스트") is None


class TestPipelineRetry:
    @patch("candidates.services.integrity.pipeline.normalize_education_group")
    @patch("candidates.services.integrity.pipeline.normalize_career_group")
    @patch("candidates.services.integrity.pipeline.extract_raw_data")
    @patch("candidates.services.integrity.pipeline.validate_step1")
    def test_step1_retry_on_warning(self, mock_v1, mock_s1, mock_s2c, mock_s2e):
        mock_v1.return_value = [{"severity": "warning", "message": "일문 섹션 누락"}]
        mock_s1.side_effect = [MOCK_RAW_DATA, MOCK_RAW_DATA]
        mock_s2c.return_value = MOCK_CAREER_RESULT
        mock_s2e.return_value = MOCK_EDU_RESULT

        result = run_integrity_pipeline("텍스트")
        assert result is not None
        assert result["pipeline_meta"]["retries"] == 1
        assert mock_s1.call_count == 2


class TestCrossVersion:
    @patch("candidates.services.integrity.pipeline.normalize_education_group")
    @patch("candidates.services.integrity.pipeline.normalize_career_group")
    @patch("candidates.services.integrity.pipeline.extract_raw_data")
    @patch("candidates.services.integrity.pipeline.validate_step1")
    def test_cross_version_flags_included(self, mock_v1, mock_s1, mock_s2c, mock_s2e):
        mock_v1.return_value = []
        mock_s1.return_value = MOCK_RAW_DATA
        mock_s2c.return_value = MOCK_CAREER_RESULT
        mock_s2e.return_value = MOCK_EDU_RESULT

        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2022-06"},
                {"company": "B사", "start_date": "2018-01", "end_date": "2019-12"},
            ],
            "educations": [],
        }
        result = run_integrity_pipeline("텍스트", previous_data=previous)
        assert result is not None
        cv_flags = [f for f in result["integrity_flags"] if f["type"] == "CAREER_DELETED"]
        assert len(cv_flags) >= 1
