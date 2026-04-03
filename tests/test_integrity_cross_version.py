import pytest

from candidates.services.integrity.step3_cross_version import (
    compare_versions,
    _normalize_company,
)


class TestNormalizeCompany:
    """Verify fuzzy company name normalization."""

    def test_strip_korean_suffixes(self):
        assert _normalize_company("주식회사 삼성전자") == "삼성전자"
        assert _normalize_company("삼성전자 주식회사") == "삼성전자"
        assert _normalize_company("㈜삼성전자") == "삼성전자"
        assert _normalize_company("(주)삼성전자") == "삼성전자"

    def test_strip_english_suffixes(self):
        assert _normalize_company("Samsung Co., Ltd.") == "samsung"
        assert _normalize_company("Google Inc.") == "google"
        assert _normalize_company("Apple Corp.") == "apple"

    def test_case_insensitive(self):
        assert _normalize_company("Samsung Electronics") == _normalize_company("samsung electronics")

    def test_whitespace_normalization(self):
        assert _normalize_company("  삼성  전자  ") == "삼성 전자"

    def test_korean_suffix_variants_match(self):
        """㈜ and (주) should produce the same normalized name."""
        assert _normalize_company("㈜현대자동차") == _normalize_company("(주)현대자동차")


class TestNoChanges:
    def test_identical_data_no_flags(self):
        data = {
            "careers": [
                {"company": "삼성전자", "start_date": "2020-01", "end_date": "2023-06", "position": "과장"},
            ],
            "educations": [
                {"institution": "서울대학교", "degree": "경영학 학사", "start_year": 2014, "end_year": 2018},
            ],
        }
        assert compare_versions(data, data) == []

    def test_empty_data_no_flags(self):
        data = {"careers": [], "educations": []}
        assert compare_versions(data, data) == []


class TestCareerDeleted:
    def test_short_career_deleted_yellow(self):
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2022-01", "end_date": "2023-06", "position": None},
                {"company": "B사", "start_date": "2020-01", "end_date": "2021-06", "position": None},
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {"company": "A사", "start_date": "2022-01", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAREER_DELETED"
        assert flags[0]["severity"] == "YELLOW"
        assert "B사" in flags[0]["detail"]

    def test_long_career_deleted_red(self):
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2022-01", "end_date": "2023-06", "position": None},
                {"company": "B사", "start_date": "2018-01", "end_date": "2021-06", "position": None},
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {"company": "A사", "start_date": "2022-01", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAREER_DELETED"
        assert flags[0]["severity"] == "RED"

    def test_deleted_career_fuzzy_match(self):
        """Company with ㈜ prefix in previous and (주) in current should match (not deleted)."""
        previous = {
            "careers": [
                {"company": "㈜삼성전자", "start_date": "2020-01", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {"company": "(주)삼성전자", "start_date": "2020-01", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0


class TestCareerPeriodChanged:
    def test_minor_date_change_no_flag(self):
        """Differences within 3 months should not be flagged."""
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {"company": "A사", "start_date": "2020-03", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0

    def test_significant_start_change_yellow(self):
        """Start date differs by >3 months => YELLOW."""
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {"company": "A사", "start_date": "2019-06", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAREER_PERIOD_CHANGED"
        assert flags[0]["severity"] == "YELLOW"
        assert "시작일" in flags[0]["detail"]

    def test_significant_end_change_yellow(self):
        """End date differs by >3 months => YELLOW."""
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-01", "position": None},
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-12", "position": None},
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAREER_PERIOD_CHANGED"
        assert flags[0]["severity"] == "YELLOW"

    def test_multiple_careers_changed_red(self):
        """Multiple careers with period changes => RED."""
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2022-06", "position": None},
                {"company": "B사", "start_date": "2018-01", "end_date": "2019-12", "position": None},
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {"company": "A사", "start_date": "2019-01", "end_date": "2023-06", "position": None},
                {"company": "B사", "start_date": "2017-01", "end_date": "2020-06", "position": None},
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        period_flags = [f for f in flags if f["type"] == "CAREER_PERIOD_CHANGED"]
        assert len(period_flags) == 2
        assert all(f["severity"] == "RED" for f in period_flags)

    def test_period_changed_with_suffix_variation(self):
        """Company name with different suffixes should still match for period comparison."""
        previous = {
            "careers": [
                {"company": "주식회사 카카오", "start_date": "2020-01", "end_date": "2022-06", "position": None},
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {"company": "카카오", "start_date": "2019-01", "end_date": "2022-06", "position": None},
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAREER_PERIOD_CHANGED"


class TestCareerAddedRetroactively:
    def test_new_past_career_yellow(self):
        """A career added with dates before previous latest end => YELLOW."""
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-06", "position": None},
                {"company": "Z사", "start_date": "2017-01", "end_date": "2019-06", "position": None},
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAREER_ADDED_RETROACTIVELY"
        assert flags[0]["severity"] == "YELLOW"
        assert "Z사" in flags[0]["detail"]

    def test_new_recent_career_no_flag(self):
        """A career added after previous latest end => not flagged as retroactive."""
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-06", "position": None},
                {"company": "B사", "start_date": "2023-07", "end_date": "2024-06", "position": None},
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0

    def test_new_career_no_end_date_no_flag(self):
        """A new career with no end_date (current job) is not retroactive."""
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-06", "position": None},
                {"company": "B사", "start_date": "2023-07", "end_date": None, "position": None},
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0


class TestEducationChanged:
    def test_degree_changed_red(self):
        previous = {
            "careers": [],
            "educations": [
                {"institution": "서울대학교", "degree": "경영학 학사", "start_year": 2014, "end_year": 2018},
            ],
        }
        current = {
            "careers": [],
            "educations": [
                {"institution": "서울대학교", "degree": "경영학 석사", "start_year": 2014, "end_year": 2018},
            ],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "EDUCATION_CHANGED"
        assert flags[0]["severity"] == "RED"
        assert "학사" in flags[0]["detail"]
        assert "석사" in flags[0]["detail"]

    def test_institution_changed_red(self):
        previous = {
            "careers": [],
            "educations": [
                {"institution": "고려대학교", "degree": "경영학 학사", "start_year": 2014, "end_year": 2018},
            ],
        }
        current = {
            "careers": [],
            "educations": [
                {"institution": "서울대학교", "degree": "경영학 학사", "start_year": 2014, "end_year": 2018},
            ],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "EDUCATION_CHANGED"
        assert flags[0]["severity"] == "RED"
        assert "고려대학교" in flags[0]["detail"]
        assert "서울대학교" in flags[0]["detail"]

    def test_same_education_no_flag(self):
        data = {
            "careers": [],
            "educations": [
                {"institution": "서울대학교", "degree": "경영학 학사", "start_year": 2014, "end_year": 2018},
            ],
        }
        assert compare_versions(data, data) == []

    def test_education_added_no_flag(self):
        """Adding a new education is not suspicious by itself."""
        previous = {
            "careers": [],
            "educations": [
                {"institution": "서울대학교", "degree": "경영학 학사", "start_year": 2014, "end_year": 2018},
            ],
        }
        current = {
            "careers": [],
            "educations": [
                {"institution": "서울대학교", "degree": "경영학 학사", "start_year": 2014, "end_year": 2018},
                {"institution": "MIT", "degree": "MBA", "start_year": 2019, "end_year": 2021},
            ],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0

    def test_degree_none_to_value_no_flag(self):
        """Going from no degree to having one is not a change (just added info)."""
        previous = {
            "careers": [],
            "educations": [
                {"institution": "서울대학교", "degree": None, "start_year": 2014, "end_year": 2018},
            ],
        }
        current = {
            "careers": [],
            "educations": [
                {"institution": "서울대학교", "degree": "경영학 학사", "start_year": 2014, "end_year": 2018},
            ],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0


class TestComprehensiveScenarios:
    def test_multiple_flag_types_combined(self):
        """A realistic scenario producing multiple types of flags."""
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-06", "position": "과장"},
                {"company": "B사", "start_date": "2017-01", "end_date": "2019-12", "position": "대리"},
            ],
            "educations": [
                {"institution": "서울대학교", "degree": "경영학 학사", "start_year": 2012, "end_year": 2016},
            ],
        }
        current = {
            "careers": [
                # A사 period extended (start moved back 6 months)
                {"company": "A사", "start_date": "2019-07", "end_date": "2023-06", "position": "과장"},
                # B사 deleted
                # C사 retroactively added (dates before 2023-06)
                {"company": "C사", "start_date": "2015-01", "end_date": "2016-12", "position": "사원"},
            ],
            "educations": [
                # Degree changed
                {"institution": "서울대학교", "degree": "경영학 석사", "start_year": 2012, "end_year": 2016},
            ],
        }
        flags = compare_versions(current, previous)
        types = {f["type"] for f in flags}
        assert "CAREER_DELETED" in types
        assert "CAREER_PERIOD_CHANGED" in types
        assert "CAREER_ADDED_RETROACTIVELY" in types
        assert "EDUCATION_CHANGED" in types

    def test_flag_format_complete(self):
        """Verify all flags have the required keys."""
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-06", "position": None},
                {"company": "B사", "start_date": "2017-01", "end_date": "2019-12", "position": None},
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        required_keys = {"type", "severity", "field", "detail", "chosen", "alternative", "reasoning"}
        for flag in flags:
            assert set(flag.keys()) == required_keys

    def test_exactly_3_month_diff_not_flagged(self):
        """Boundary: exactly 3 months difference should NOT trigger flag (> not >=)."""
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {"company": "A사", "start_date": "2020-04", "end_date": "2023-06", "position": None},
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0

    def test_exactly_24_month_career_deleted_yellow(self):
        """Boundary: exactly 24 months (2 years) should be YELLOW (> not >=)."""
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2022-01", "position": None},
            ],
            "educations": [],
        }
        current = {"careers": [], "educations": []}
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["severity"] == "YELLOW"

    def test_25_month_career_deleted_red(self):
        """25 months > 24 months threshold => RED."""
        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2022-02", "position": None},
            ],
            "educations": [],
        }
        current = {"careers": [], "educations": []}
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["severity"] == "RED"
