import pytest

from candidates.services.integrity.step3_overlap import (
    check_period_overlaps,
    check_career_education_overlap,
)


class TestPeriodOverlaps:
    def test_no_overlap_sequential(self):
        careers = [
            {"company": "A사", "start_date": "2020-01", "end_date": "2022-06", "is_current": False},
            {"company": "B사", "start_date": "2022-07", "end_date": "2024-01", "is_current": False},
        ]
        assert check_period_overlaps(careers) == []

    def test_short_overlap_normal(self):
        careers = [
            {"company": "A사", "start_date": "2020-01", "end_date": "2022-06", "is_current": False},
            {"company": "B사", "start_date": "2022-05", "end_date": "2024-01", "is_current": False},
        ]
        assert check_period_overlaps(careers) == []

    def test_long_overlap_flagged(self):
        careers = [
            {"company": "A사", "start_date": "2020-01", "end_date": "2022-06", "is_current": False},
            {"company": "B사", "start_date": "2021-01", "end_date": "2024-01", "is_current": False},
        ]
        result = check_period_overlaps(careers)
        assert len(result) == 1
        assert result[0]["type"] == "PERIOD_OVERLAP"
        assert "17개월" in result[0]["detail"]

    def test_current_career_uses_today(self):
        careers = [
            {"company": "A사", "start_date": "2020-01", "end_date": None, "is_current": True},
            {"company": "B사", "start_date": "2023-01", "end_date": "2024-01", "is_current": False},
        ]
        result = check_period_overlaps(careers)
        assert len(result) >= 1

    def test_affiliated_group_excluded(self):
        careers = [
            {"company": "삼성카드", "start_date": "2002-08", "end_date": "2006-05", "is_current": False},
            {"company": "삼성그룹 T/F", "start_date": "2004-03", "end_date": "2005-03", "is_current": False},
        ]
        affiliated = [{"canonical_name": "삼성", "entry_indices": [0, 1], "relationship": "affiliated_group"}]
        assert check_period_overlaps(careers, affiliated_groups=affiliated) == []

    def test_repeated_overlaps_red(self):
        careers = [
            {"company": "A사", "start_date": "1994-02", "end_date": "1995-11", "is_current": False},
            {"company": "B사", "start_date": "1995-01", "end_date": "1997-10", "is_current": False},
            {"company": "C사", "start_date": "1996-10", "end_date": "2000-03", "is_current": False},
        ]
        result = check_period_overlaps(careers)
        assert any(f["severity"] == "RED" for f in result)

    def test_no_end_date_not_current_skipped(self):
        careers = [
            {"company": "A사", "start_date": "2020-01", "end_date": None, "is_current": False},
            {"company": "B사", "start_date": "2020-06", "end_date": "2022-01", "is_current": False},
        ]
        assert check_period_overlaps(careers) == []


class TestCareerEducationOverlap:
    def test_no_overlap(self):
        careers = [{"company": "A사", "start_date": "2020-01", "end_date": "2024-01", "is_current": False}]
        educations = [{"institution": "서울대", "start_year": 2014, "end_year": 2018}]
        assert check_career_education_overlap(careers, educations) == []

    def test_long_overlap_flagged(self):
        careers = [{"company": "A사", "start_date": "2016-01", "end_date": "2020-01", "is_current": False}]
        educations = [{"institution": "서울대", "start_year": 2014, "end_year": 2018}]
        result = check_career_education_overlap(careers, educations)
        assert len(result) == 1
        assert result[0]["type"] == "CAREER_EDUCATION_OVERLAP"

    def test_short_overlap_normal(self):
        careers = [{"company": "A사", "start_date": "2017-09", "end_date": "2020-01", "is_current": False}]
        educations = [{"institution": "서울대", "start_year": 2014, "end_year": 2018}]
        assert check_career_education_overlap(careers, educations) == []
