import pytest

from candidates.services.integrity.validators import (
    validate_step1,
    validate_step1_5,
    validate_step2,
)


# ===========================================================================
# Step 1 — extraction completeness
# ===========================================================================


class TestValidateStep1:
    """Tests for validate_step1."""

    def test_pass_complete_data(self):
        """No issues when data is diverse and complete."""
        raw_data = {
            "careers": [
                {"source_section": "경력사항", "duration_text": "2년 3개월"},
                {"source_section": "해외경력", "duration_text": None},
            ],
        }
        resume_text = "삼성전자 경력사항에서 근무 후 해외경력 섹션에 기재."
        issues = validate_step1(raw_data, resume_text)
        assert issues == []

    def test_single_source_section_warning(self):
        """Warn when all careers share the same source_section."""
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
                {"source_section": "경력사항"},
                {"source_section": "경력사항"},
            ],
        }
        resume_text = "일반적인 이력서 텍스트입니다."
        issues = validate_step1(raw_data, resume_text)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "same source_section" in issues[0]["message"]

    def test_single_career_no_diversity_warning(self):
        """No diversity warning when there is only one career."""
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
            ],
        }
        resume_text = "단일 경력 이력서."
        issues = validate_step1(raw_data, resume_text)
        assert issues == []

    def test_japanese_present_no_section(self):
        """Warn when resume has Japanese but no source_section references it."""
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
                {"source_section": "자격증"},
            ],
        }
        resume_text = "東京本社にて勤務。カタカナテスト。경력사항 기재."
        issues = validate_step1(raw_data, resume_text)
        jp_issues = [i for i in issues if "Japanese" in i["message"]]
        assert len(jp_issues) == 1
        assert jp_issues[0]["severity"] == "warning"

    def test_japanese_present_with_section(self):
        """No warning when Japanese text has a matching source_section."""
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
                {"source_section": "にほんご経歴"},
            ],
        }
        resume_text = "東京本社にて勤務。경력사항도 있음."
        issues = validate_step1(raw_data, resume_text)
        jp_issues = [i for i in issues if "Japanese" in i["message"]]
        assert jp_issues == []

    def test_japanese_katakana_only(self):
        """Katakana-only text should also trigger Japanese detection."""
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
            ],
        }
        resume_text = "ソフトウェアエンジニア として勤務"
        issues = validate_step1(raw_data, resume_text)
        jp_issues = [i for i in issues if "Japanese" in i["message"]]
        assert len(jp_issues) == 1

    def test_english_present_no_section(self):
        """Warn when resume has significant English but no section references it."""
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
            ],
        }
        resume_text = "SoftwareEngineeringDepartment 에서 근무했습니다."
        issues = validate_step1(raw_data, resume_text)
        en_issues = [i for i in issues if "English" in i["message"]]
        assert len(en_issues) == 1
        assert en_issues[0]["severity"] == "warning"

    def test_english_short_no_warning(self):
        """Short English words (< 15 chars) should not trigger warning."""
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
            ],
        }
        resume_text = "Samsung에서 Manager로 근무."
        issues = validate_step1(raw_data, resume_text)
        en_issues = [i for i in issues if "English" in i["message"]]
        assert en_issues == []

    def test_english_present_with_section(self):
        """No warning when English text has a matching source_section."""
        raw_data = {
            "careers": [
                {"source_section": "EnglishResumeSection with details"},
            ],
        }
        resume_text = "WorkedAtSoftwareEngineeringDepartment for 5 years."
        issues = validate_step1(raw_data, resume_text)
        en_issues = [i for i in issues if "English" in i["message"]]
        assert en_issues == []

    def test_duration_text_missing_with_parenthetical(self):
        """Warn when resume has parenthetical durations but no career has duration_text."""
        raw_data = {
            "careers": [
                {"source_section": "경력사항", "duration_text": None},
                {"source_section": "기타경력", "duration_text": ""},
            ],
        }
        resume_text = "삼성전자 (11개월) 근무 후 LG전자 (2Y 6M) 근무."
        issues = validate_step1(raw_data, resume_text)
        dur_issues = [i for i in issues if "duration_text" in i["message"]]
        assert len(dur_issues) == 1
        assert dur_issues[0]["severity"] == "warning"

    def test_duration_text_present(self):
        """No warning when at least one career has duration_text filled."""
        raw_data = {
            "careers": [
                {"source_section": "경력사항", "duration_text": "11개월"},
                {"source_section": "기타경력", "duration_text": None},
            ],
        }
        resume_text = "삼성전자 (11개월) 근무."
        issues = validate_step1(raw_data, resume_text)
        dur_issues = [i for i in issues if "duration_text" in i["message"]]
        assert dur_issues == []

    def test_duration_pattern_2y_6m(self):
        """Detect (2Y 6M) style parenthetical duration."""
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
            ],
        }
        resume_text = "해외법인 근무 (2Y 6M) 발령."
        issues = validate_step1(raw_data, resume_text)
        dur_issues = [i for i in issues if "duration_text" in i["message"]]
        assert len(dur_issues) == 1

    def test_empty_careers(self):
        """No crash with empty careers list."""
        raw_data = {"careers": []}
        resume_text = "빈 이력서."
        issues = validate_step1(raw_data, resume_text)
        assert issues == []

    def test_no_source_section_field(self):
        """Careers without source_section field should not crash."""
        raw_data = {
            "careers": [
                {"company": "A사"},
                {"company": "B사"},
            ],
        }
        resume_text = "일반 이력서."
        issues = validate_step1(raw_data, resume_text)
        # With 2 careers but 0 source_sections, set size is 0 (not 1),
        # so the diversity check does not trigger.
        assert issues == []


# ===========================================================================
# Step 1.5 — grouping quality
# ===========================================================================


class TestValidateStep1_5:
    """Tests for validate_step1_5."""

    def test_pass_well_grouped(self):
        """No issues when most careers are grouped."""
        grouping = {
            "groups": [
                {"canonical_name": "삼성", "entry_indices": [0, 1, 2]},
                {"canonical_name": "LG", "entry_indices": [3, 4]},
            ],
        }
        issues = validate_step1_5(grouping, total_careers=5, total_educations=2)
        assert issues == []

    def test_high_ungrouped_ratio(self):
        """Warn when >50% of careers are ungrouped."""
        grouping = {
            "groups": [
                {"canonical_name": "삼성", "entry_indices": [0]},
            ],
        }
        issues = validate_step1_5(grouping, total_careers=5, total_educations=1)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "4/5" in issues[0]["message"]
        assert "80%" in issues[0]["message"]

    def test_exactly_50_percent_no_warning(self):
        """No warning at exactly 50% ungrouped."""
        grouping = {
            "groups": [
                {"canonical_name": "A", "entry_indices": [0, 1]},
            ],
        }
        issues = validate_step1_5(grouping, total_careers=4, total_educations=0)
        assert issues == []

    def test_all_ungrouped(self):
        """Warn when no careers are grouped."""
        grouping = {"groups": []}
        issues = validate_step1_5(grouping, total_careers=3, total_educations=0)
        assert len(issues) == 1
        assert "3/3" in issues[0]["message"]

    def test_zero_careers(self):
        """No crash and no warning with zero careers."""
        grouping = {"groups": []}
        issues = validate_step1_5(grouping, total_careers=0, total_educations=0)
        assert issues == []

    def test_all_grouped(self):
        """No warning when every career is grouped."""
        grouping = {
            "groups": [
                {"canonical_name": "A", "entry_indices": [0, 1, 2]},
            ],
        }
        issues = validate_step1_5(grouping, total_careers=3, total_educations=1)
        assert issues == []

    def test_overlapping_group_indices(self):
        """Handle overlapping indices across groups (deduplication)."""
        grouping = {
            "groups": [
                {"canonical_name": "A", "entry_indices": [0, 1]},
                {"canonical_name": "B", "entry_indices": [1, 2]},
            ],
        }
        # 3 unique indices grouped out of 6 total = 50% ungrouped, not > 50%
        issues = validate_step1_5(grouping, total_careers=6, total_educations=0)
        # indices {0,1,2} = 3 grouped, 6-3=3 ungrouped, 3/6=0.5 not > 0.5
        assert issues == []


# ===========================================================================
# Step 2 — normalization quality
# ===========================================================================


class TestValidateStep2:
    """Tests for validate_step2."""

    def test_pass_complete_data(self):
        """No issues when all fields are valid."""
        normalized = {
            "careers": [
                {
                    "company": "삼성전자",
                    "start_date": "2020-01",
                    "end_date": "2022-06",
                },
                {
                    "company": "LG전자",
                    "start_date": "2022-07",
                    "end_date": None,
                },
            ],
            "flags": [
                {
                    "severity": "YELLOW",
                    "reasoning": "Short overlap during transition",
                },
            ],
        }
        issues = validate_step2(normalized)
        assert issues == []

    def test_missing_company(self):
        """Error when company is missing."""
        normalized = {
            "careers": [
                {"company": "", "start_date": "2020-01"},
            ],
            "flags": [],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        assert len(errors) == 1
        assert "company" in errors[0]["message"]

    def test_missing_start_date(self):
        """Error when start_date is missing."""
        normalized = {
            "careers": [
                {"company": "삼성전자", "start_date": None},
            ],
            "flags": [],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        assert len(errors) == 1
        assert "start_date" in errors[0]["message"]

    def test_missing_both_required(self):
        """Error for each missing required field."""
        normalized = {
            "careers": [
                {"company": None, "start_date": ""},
            ],
            "flags": [],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        assert len(errors) == 2

    def test_invalid_start_date_format(self):
        """Error when start_date does not match YYYY-MM."""
        normalized = {
            "careers": [
                {"company": "A사", "start_date": "2020/01"},
            ],
            "flags": [],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        assert any("start_date" in e["message"] and "YYYY-MM" in e["message"] for e in errors)

    def test_invalid_end_date_format(self):
        """Error when end_date does not match YYYY-MM."""
        normalized = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "June 2022"},
            ],
            "flags": [],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        assert any("end_date" in e["message"] for e in errors)

    def test_invalid_date_month_13(self):
        """Error for month value > 12."""
        normalized = {
            "careers": [
                {"company": "A사", "start_date": "2020-13"},
            ],
            "flags": [],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        assert any("YYYY-MM" in e["message"] for e in errors)

    def test_flag_without_reasoning(self):
        """Warning when a flag has severity but no reasoning."""
        normalized = {
            "careers": [
                {"company": "A사", "start_date": "2020-01"},
            ],
            "flags": [
                {"severity": "RED", "type": "PERIOD_OVERLAP"},
            ],
        }
        issues = validate_step2(normalized)
        warnings = [i for i in issues if i["severity"] == "warning"]
        assert len(warnings) == 1
        assert "reasoning" in warnings[0]["message"]

    def test_flag_with_reasoning_ok(self):
        """No warning when flag has both severity and reasoning."""
        normalized = {
            "careers": [
                {"company": "A사", "start_date": "2020-01"},
            ],
            "flags": [
                {
                    "severity": "RED",
                    "reasoning": "Repeated overlap pattern",
                },
            ],
        }
        issues = validate_step2(normalized)
        warnings = [i for i in issues if i["severity"] == "warning"]
        assert warnings == []

    def test_flag_no_severity_no_warning(self):
        """No warning when flag has no severity (nothing to validate)."""
        normalized = {
            "careers": [
                {"company": "A사", "start_date": "2020-01"},
            ],
            "flags": [
                {"type": "INFO", "detail": "some info"},
            ],
        }
        issues = validate_step2(normalized)
        assert issues == []

    def test_empty_careers(self):
        """No crash with empty careers."""
        normalized = {"careers": [], "flags": []}
        issues = validate_step2(normalized)
        assert issues == []

    def test_multiple_careers_mixed_issues(self):
        """Multiple careers with various issues."""
        normalized = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2022-06"},
                {"company": "", "start_date": "bad-date"},
                {"company": "C사", "start_date": "2023-01", "end_date": "not-a-date"},
            ],
            "flags": [
                {"severity": "YELLOW"},
            ],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        warnings = [i for i in issues if i["severity"] == "warning"]
        # Career #1: missing company + bad start_date = 2 errors
        # Career #2: bad end_date = 1 error
        assert len(errors) == 3
        # Flag without reasoning = 1 warning
        assert len(warnings) == 1

    def test_no_integrity_flags_key(self):
        """No crash when integrity_flags key is missing."""
        normalized = {
            "careers": [
                {"company": "A사", "start_date": "2020-01"},
            ],
        }
        issues = validate_step2(normalized)
        assert issues == []
