"""Tests for resume fraud detection rules."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from data_extraction.services.extraction.integrity import (
    check_birth_year_consistency,
    check_campus_match,
    check_education_gaps,
    _check_career_deleted,
)


# ===========================================================================
# check_education_gaps
# ===========================================================================


class TestEducationGaps:
    def test_grad_only_no_undergrad(self):
        educations = [
            {"institution": "서울대학교", "degree": "석사", "major": "컴퓨터공학", "start_year": 2018, "end_year": 2020},
        ]
        flags = check_education_gaps(educations)
        types = [f["type"] for f in flags]
        assert "EDUCATION_GAP" in types
        assert any("학부" in f["detail"] for f in flags)

    def test_grad_and_undergrad_no_flag(self):
        educations = [
            {"institution": "서울대학교", "degree": "석사", "major": "컴퓨터공학", "start_year": 2018, "end_year": 2020},
            {"institution": "고려대학교", "degree": "학사", "major": "컴퓨터공학", "start_year": 2014, "end_year": 2018},
        ]
        flags = check_education_gaps(educations)
        assert not any("학부" in f.get("detail", "") for f in flags)

    def test_undergrad_only_no_flag(self):
        educations = [
            {"institution": "연세대학교", "degree": "학사", "major": "경영학", "start_year": 2010, "end_year": 2014},
        ]
        flags = check_education_gaps(educations)
        assert not any("학부" in f.get("detail", "") for f in flags)

    def test_missing_start_year(self):
        educations = [
            {"institution": "한양대학교", "degree": "학사", "major": "기계공학", "start_year": None, "end_year": 2014},
        ]
        flags = check_education_gaps(educations)
        assert any("입학년도" in f["detail"] for f in flags)

    def test_both_years_present_no_flag(self):
        educations = [
            {"institution": "한양대학교", "degree": "학사", "major": "기계공학", "start_year": 2010, "end_year": 2014},
        ]
        flags = check_education_gaps(educations)
        assert len(flags) == 0

    def test_english_degree_keywords(self):
        educations = [
            {"institution": "MIT", "degree": "Ph.D.", "major": "CS", "start_year": 2015, "end_year": 2020},
        ]
        flags = check_education_gaps(educations)
        assert any("학부" in f["detail"] for f in flags)

    def test_mba_without_undergrad(self):
        educations = [
            {"institution": "서울대학교", "degree": "MBA", "major": "경영학", "start_year": 2020, "end_year": 2022},
        ]
        flags = check_education_gaps(educations)
        assert any("학부" in f["detail"] for f in flags)

    def test_empty_educations(self):
        assert check_education_gaps([]) == []


# ===========================================================================
# check_campus_match
# ===========================================================================


SAMPLE_CAMPUS_DATA = {
    "고려대학교": {
        "main_campus": "안암(서울)",
        "tier": "SKY",
        "campuses": {
            "안암(서울)": {"in_seoul": True},
            "세종": {"in_seoul": False},
        },
        "campus_only_departments": {
            "세종": ["약학과", "간호학과"],
            "안암(서울)": ["의학과"],
        },
        "campus_keywords": {
            "안암(서울)": ["안암", "서울"],
            "세종": ["세종", "조치원"],
        },
        "aliases": ["고대", "고려대", "Korea Univ"],
    },
}


class TestCampusMatch:
    @pytest.fixture(autouse=True)
    def _patch_data(self):
        with patch(
            "data_extraction.services.extraction.integrity._load_multi_campus_data",
            return_value=SAMPLE_CAMPUS_DATA,
        ):
            yield

    def test_multi_campus_no_keyword_yellow(self):
        educations = [
            {"institution": "고려대학교", "degree": "학사", "major": "경영학"},
        ]
        flags = check_campus_match(educations)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAMPUS_MISSING"
        assert flags[0]["severity"] == "YELLOW"

    def test_campus_keyword_present_no_flag(self):
        educations = [
            {"institution": "고려대학교 안암캠퍼스", "degree": "학사", "major": "경영학"},
        ]
        flags = check_campus_match(educations)
        assert len(flags) == 0

    def test_sejong_campus_keyword_no_flag(self):
        educations = [
            {"institution": "고려대학교 세종캠퍼스", "degree": "학사", "major": "경영학"},
        ]
        flags = check_campus_match(educations)
        assert len(flags) == 0

    def test_department_only_at_regional_campus_red(self):
        educations = [
            {"institution": "고려대학교", "degree": "학사", "major": "약학과"},
        ]
        flags = check_campus_match(educations)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAMPUS_DEPARTMENT_MATCH"
        assert flags[0]["severity"] == "RED"

    def test_alias_matching(self):
        educations = [
            {"institution": "고대", "degree": "학사", "major": "경영학"},
        ]
        flags = check_campus_match(educations)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAMPUS_MISSING"

    def test_non_multi_campus_no_flag(self):
        educations = [
            {"institution": "서울대학교", "degree": "학사", "major": "물리학"},
        ]
        flags = check_campus_match(educations)
        assert len(flags) == 0

    def test_empty_data_no_flag(self):
        with patch(
            "data_extraction.services.extraction.integrity._load_multi_campus_data",
            return_value={},
        ):
            flags = check_campus_match([{"institution": "고려대학교", "degree": "학사"}])
            assert len(flags) == 0


# ===========================================================================
# check_birth_year_consistency
# ===========================================================================


class TestBirthYearConsistency:
    def test_same_year_no_flag(self):
        assert check_birth_year_consistency(1985, 1985) == []

    def test_different_year_red(self):
        flags = check_birth_year_consistency(1975, 1974)
        assert len(flags) == 1
        assert flags[0]["type"] == "BIRTH_YEAR_MISMATCH"
        assert flags[0]["severity"] == "RED"
        assert "1974" in flags[0]["detail"]
        assert "1975" in flags[0]["detail"]

    def test_current_none_no_flag(self):
        assert check_birth_year_consistency(None, 1985) == []

    def test_previous_none_no_flag(self):
        assert check_birth_year_consistency(1985, None) == []

    def test_both_none_no_flag(self):
        assert check_birth_year_consistency(None, None) == []


# ===========================================================================
# _check_career_deleted (enhanced: 2+ deletions → RED)
# ===========================================================================


class TestCareerDeletedEnhanced:
    def test_single_short_delete_yellow(self):
        """Single short career deletion stays YELLOW."""
        careers = [
            {"company": "ABC Corp", "start_date": "2020-01", "end_date": "2021-06", "position": "대리"},
        ]
        flags = _check_career_deleted(careers)
        assert len(flags) == 1
        assert flags[0]["severity"] == "YELLOW"

    def test_single_long_delete_red(self):
        """Single long career deletion (>24 months) is RED."""
        careers = [
            {"company": "ABC Corp", "start_date": "2018-01", "end_date": "2021-06", "position": "과장"},
        ]
        flags = _check_career_deleted(careers)
        assert len(flags) == 1
        assert flags[0]["severity"] == "RED"

    def test_two_deletes_all_red(self):
        """Two or more deletions upgrade ALL to RED."""
        careers = [
            {"company": "ABC Corp", "start_date": "2020-01", "end_date": "2021-01", "position": "사원"},
            {"company": "DEF Inc", "start_date": "2021-02", "end_date": "2022-01", "position": "대리"},
        ]
        flags = _check_career_deleted(careers)
        assert len(flags) == 2
        assert all(f["severity"] == "RED" for f in flags)
        assert all("2건 이상" in f["reasoning"] for f in flags)

    def test_empty_no_flag(self):
        assert _check_career_deleted([]) == []
