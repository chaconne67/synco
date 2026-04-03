import pytest
from unittest.mock import patch

from candidates.services.integrity.step1_5_grouping import (
    GROUPING_SYSTEM_PROMPT,
    group_raw_data,
    _build_summary,
)


@pytest.fixture
def raw_data_same_company():
    """Raw data with same company appearing in different sections."""
    return {
        "careers": [
            {
                "company": "삼성전자",
                "start_date": "2010-01",
                "end_date": "2015-06",
                "source_section": "경력사항",
            },
            {
                "company": "Samsung Electronics",
                "start_date": "2010-01",
                "end_date": "2015-06",
                "source_section": "Career Summary",
            },
            {
                "company": "LG화학",
                "start_date": "2016-01",
                "end_date": "2020-12",
                "source_section": "경력사항",
            },
        ],
        "educations": [
            {
                "institution": "서울대학교",
                "start_year": 2006,
                "end_year": 2010,
                "source_section": "학력",
            },
            {
                "institution": "Seoul National University",
                "start_year": 2006,
                "end_year": 2010,
                "source_section": "Education",
            },
        ],
    }


@pytest.fixture
def gemini_grouped_response():
    """Gemini response that groups same company from different sections."""
    return {
        "career_groups": [
            {
                "group_id": "cg_1",
                "canonical_name": "삼성전자",
                "relationship": "same_company",
                "entry_indices": [0, 1],
            },
        ],
        "education_groups": [
            {
                "group_id": "eg_1",
                "canonical_name": "서울대학교",
                "entry_indices": [0, 1],
            },
        ],
        "ungrouped_career_indices": [2],
        "ungrouped_education_indices": [],
    }


class TestGroupRawData:
    @patch("candidates.services.integrity.step1_5_grouping._call_gemini")
    def test_groups_same_company_from_different_sections(
        self, mock_gemini, raw_data_same_company, gemini_grouped_response
    ):
        mock_gemini.return_value = gemini_grouped_response

        result = group_raw_data(raw_data_same_company)

        assert result is not None
        assert len(result["career_groups"]) == 1
        assert result["career_groups"][0]["entry_indices"] == [0, 1]
        assert result["career_groups"][0]["relationship"] == "same_company"
        assert len(result["education_groups"]) == 1
        assert result["education_groups"][0]["entry_indices"] == [0, 1]

    @patch("candidates.services.integrity.step1_5_grouping._call_gemini")
    def test_ungrouped_items_preserved(self, mock_gemini, gemini_grouped_response):
        raw_data = {
            "careers": [
                {"company": "A사", "start_date": "2010-01", "end_date": "2015-06"},
                {"company": "B사", "start_date": "2016-01", "end_date": "2020-12"},
                {"company": "C사", "start_date": "2021-01", "end_date": "2023-06"},
            ],
            "educations": [
                {"institution": "서울대", "start_year": 2006, "end_year": 2010},
            ],
        }
        mock_gemini.return_value = {
            "career_groups": [],
            "education_groups": [],
            "ungrouped_career_indices": [0, 1, 2],
            "ungrouped_education_indices": [0],
        }

        result = group_raw_data(raw_data)

        assert result is not None
        assert result["ungrouped_career_indices"] == [0, 1, 2]
        assert result["ungrouped_education_indices"] == [0]
        assert result["career_groups"] == []
        assert result["education_groups"] == []

    @patch("candidates.services.integrity.step1_5_grouping._call_gemini")
    def test_empty_data_returns_empty_grouping(self, mock_gemini):
        result = group_raw_data({"careers": [], "educations": []})

        assert result is not None
        assert result["career_groups"] == []
        assert result["education_groups"] == []
        assert result["ungrouped_career_indices"] == []
        assert result["ungrouped_education_indices"] == []
        mock_gemini.assert_not_called()

    @patch("candidates.services.integrity.step1_5_grouping._call_gemini")
    def test_gemini_failure_returns_none(self, mock_gemini):
        mock_gemini.side_effect = Exception("API error")

        result = group_raw_data({"careers": [{"company": "A사"}], "educations": []})

        assert result is None

    @patch("candidates.services.integrity.step1_5_grouping._call_gemini")
    def test_gemini_returns_none(self, mock_gemini):
        mock_gemini.return_value = None

        result = group_raw_data({"careers": [{"company": "A사"}], "educations": []})

        assert result is None

    @patch("candidates.services.integrity.step1_5_grouping._call_gemini")
    def test_missing_keys_returns_none(self, mock_gemini):
        mock_gemini.return_value = {"career_groups": []}  # missing other keys

        result = group_raw_data({"careers": [{"company": "A사"}], "educations": []})

        assert result is None

    @patch("candidates.services.integrity.step1_5_grouping._call_gemini")
    def test_feedback_included_in_message(self, mock_gemini):
        mock_gemini.return_value = {
            "career_groups": [],
            "education_groups": [],
            "ungrouped_career_indices": [0],
            "ungrouped_education_indices": [],
        }

        group_raw_data(
            {"careers": [{"company": "A사"}], "educations": []},
            feedback="인덱스 0과 1은 같은 회사입니다",
        )

        call_args = mock_gemini.call_args
        # positional args: (system, prompt, max_tokens)
        prompt_arg = call_args[0][1]
        assert "인덱스 0과 1은 같은 회사입니다" in prompt_arg

    @patch("candidates.services.integrity.step1_5_grouping._call_gemini")
    def test_parent_with_sub_periods(self, mock_gemini):
        raw_data = {
            "careers": [
                {"company": "삼성전자", "start_date": "2000-01", "end_date": "2010-12"},
                {"company": "삼성전자 메모리사업부", "start_date": "2005-01", "end_date": "2008-06"},
            ],
            "educations": [],
        }
        mock_gemini.return_value = {
            "career_groups": [
                {
                    "group_id": "cg_1",
                    "canonical_name": "삼성전자",
                    "relationship": "parent_with_sub_periods",
                    "entry_indices": [0, 1],
                }
            ],
            "education_groups": [],
            "ungrouped_career_indices": [],
            "ungrouped_education_indices": [],
        }

        result = group_raw_data(raw_data)

        assert result is not None
        assert result["career_groups"][0]["relationship"] == "parent_with_sub_periods"


class TestSystemPrompt:
    def test_has_no_merge_principle(self):
        assert "병합 금지" in GROUPING_SYSTEM_PROMPT

    def test_has_ungrouped_principle(self):
        assert "미분류" in GROUPING_SYSTEM_PROMPT or "ungrouped" in GROUPING_SYSTEM_PROMPT

    def test_has_grouping_failure_cost(self):
        assert "잘못된 그루핑" in GROUPING_SYSTEM_PROMPT

    def test_has_same_institution_different_language(self):
        assert "다른 언어" in GROUPING_SYSTEM_PROMPT

    def test_has_parent_sub_periods(self):
        assert "parent_with_sub_periods" in GROUPING_SYSTEM_PROMPT

    def test_has_affiliated_group(self):
        assert "affiliated_group" in GROUPING_SYSTEM_PROMPT


class TestBuildSummary:
    def test_career_summary_format(self):
        raw_data = {
            "careers": [
                {
                    "company": "삼성전자",
                    "start_date": "2010-01",
                    "end_date": "2015-06",
                    "source_section": "경력사항",
                },
            ],
            "educations": [],
        }
        summary = _build_summary(raw_data)
        assert "[0] 삼성전자 | 2010-01~2015-06 | source: 경력사항" in summary

    def test_education_summary_format(self):
        raw_data = {
            "careers": [],
            "educations": [
                {
                    "institution": "서울대학교",
                    "start_year": 2006,
                    "end_year": 2010,
                    "source_section": "학력",
                },
            ],
        }
        summary = _build_summary(raw_data)
        assert "[0] 서울대학교 | 2006~2010 | source: 학력" in summary

    def test_current_career_shows_현재(self):
        raw_data = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "is_current": True,
                },
            ],
            "educations": [],
        }
        summary = _build_summary(raw_data)
        assert "현재" in summary

    def test_empty_data_returns_empty(self):
        summary = _build_summary({"careers": [], "educations": []})
        assert summary == ""
