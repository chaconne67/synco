import pytest
from unittest.mock import patch

from candidates.services.integrity.step2_normalize import (
    CAREER_SYSTEM_PROMPT,
    EDUCATION_SYSTEM_PROMPT,
    normalize_career_group,
    normalize_education_group,
    normalize_skills,
)


class TestStep2Prompt:
    def test_career_prompt_has_key_principles(self):
        assert "부산물" in CAREER_SYSTEM_PROMPT
        assert "거짓 경보" in CAREER_SYSTEM_PROMPT
        assert "채용 담당자" in CAREER_SYSTEM_PROMPT

    def test_education_prompt_has_key_principles(self):
        assert "솔직하게" in EDUCATION_SYSTEM_PROMPT
        assert "편입" in EDUCATION_SYSTEM_PROMPT


class TestNormalizeCareerGroup:
    @patch("candidates.services.integrity.step2_normalize._call_gemini")
    def test_multiple_careers_returned(self, mock_call):
        mock_call.return_value = {
            "careers": [
                {"company": "A사", "start_date": "2022-01", "end_date": None, "is_current": True, "order": 0},
                {"company": "B사", "start_date": "2020-01", "end_date": "2021-12", "is_current": False, "order": 1},
            ],
            "flags": [],
        }
        entries = [
            {"company": "A사", "start_date": "2022.01", "end_date": "현재", "source_section": "경력란"},
            {"company": "B사", "start_date": "2020.01", "end_date": "2021.12", "source_section": "경력란"},
        ]
        result = normalize_career_group(entries, "전체 경력")
        assert len(result["careers"]) == 2
        assert result["flags"] == []

    @patch("candidates.services.integrity.step2_normalize._call_gemini")
    def test_date_conflict_detected(self, mock_call):
        mock_call.return_value = {
            "careers": [
                {"company": "카모스테크", "start_date": "1999-02", "end_date": "2003-07", "is_current": False, "order": 0},
            ],
            "flags": [{
                "type": "DATE_CONFLICT",
                "severity": "RED",
                "field": "careers.start_date",
                "detail": "시작일 7년 차이",
                "chosen": "1999-02",
                "alternative": "1992-02",
                "reasoning": "다수의 섹션이 1999년, 1개 섹션만 1992년",
            }],
        }
        entries = [
            {"company": "카모스테크", "start_date": "1999.2", "source_section": "국문"},
            {"company": "カモステック", "start_date": "1992.2", "source_section": "일문"},
        ]
        result = normalize_career_group(entries, "전체 경력")
        assert len(result["flags"]) == 1
        assert result["flags"][0]["type"] == "DATE_CONFLICT"

    @patch("candidates.services.integrity.step2_normalize._call_gemini")
    def test_single_career_fallback(self, mock_call):
        """LLM이 career(단수) 형태로 반환해도 처리"""
        mock_call.return_value = {
            "career": {"company": "A사", "start_date": "2020-01", "end_date": "2022-06", "is_current": False},
            "flags": [],
        }
        entries = [{"company": "A사", "start_date": "2020.01", "source_section": "경력란"}]
        result = normalize_career_group(entries, "전체 경력")
        assert "careers" in result
        assert len(result["careers"]) == 1

    @patch("candidates.services.integrity.step2_normalize._call_gemini")
    def test_gemini_failure_returns_none(self, mock_call):
        mock_call.return_value = None
        result = normalize_career_group([], "전체 경력")
        assert result is None


class TestNormalizeEducationGroup:
    @patch("candidates.services.integrity.step2_normalize._call_gemini")
    def test_short_degree_detected(self, mock_call):
        mock_call.return_value = {
            "educations": [{"institution": "X대", "degree": "학사", "start_year": 2020, "end_year": 2022}],
            "flags": [{"type": "SHORT_DEGREE", "severity": "YELLOW", "field": "educations",
                        "detail": "4년제 2년 재학", "chosen": None, "alternative": None,
                        "reasoning": "편입 가능성 확인 필요"}],
        }
        entries = [{"institution": "X대", "degree": "학사", "start_year": 2020, "end_year": 2022, "source_section": "학력란"}]
        result = normalize_education_group(entries)
        assert len(result["flags"]) == 1
        assert result["flags"][0]["type"] == "SHORT_DEGREE"

    @patch("candidates.services.integrity.step2_normalize._call_gemini")
    def test_dropout_no_flag(self, mock_call):
        mock_call.return_value = {
            "educations": [{"institution": "Y대", "degree": "중퇴", "start_year": 2018, "end_year": 2020, "is_abroad": False}],
            "flags": [],
        }
        entries = [{"institution": "Y대", "degree": "중퇴", "start_year": 2018, "end_year": 2020, "source_section": "학력란"}]
        result = normalize_education_group(entries)
        assert result["flags"] == []

    def test_empty_entries_returns_empty(self):
        result = normalize_education_group([])
        assert result == {"educations": [], "flags": []}

    @patch("candidates.services.integrity.step2_normalize._call_gemini")
    def test_gemini_failure_returns_none(self, mock_call):
        mock_call.return_value = None
        entries = [{"institution": "Z대", "degree": "학사", "source_section": "학력란"}]
        result = normalize_education_group(entries)
        assert result is None


class TestNormalizeSkills:
    def test_passthrough(self):
        raw = {
            "certifications": [{"name": "정보처리기사", "date": "2020-05"}],
            "language_skills": [{"language": "영어", "level": "상"}],
        }
        result = normalize_skills(raw)
        assert result["certifications"] == raw["certifications"]
        assert result["language_skills"] == raw["language_skills"]

    def test_empty_data(self):
        result = normalize_skills({})
        assert result["certifications"] == []
        assert result["language_skills"] == []
