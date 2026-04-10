from data_extraction.services.validation import (
    compute_overall_confidence,
    validate_cross_check,
    validate_extraction,
    validate_rules,
)


class TestRuleValidation:
    def test_valid_birth_year(self):
        data = {"name": "강솔찬", "birth_year": 1985}
        issues = validate_rules(data)
        assert not any(i["field"] == "birth_year" for i in issues)

    def test_invalid_birth_year_too_old(self):
        data = {"name": "강솔찬", "birth_year": 1930}
        issues = validate_rules(data)
        assert any(i["field"] == "birth_year" for i in issues)

    def test_invalid_birth_year_future(self):
        data = {"name": "강솔찬", "birth_year": 2030}
        issues = validate_rules(data)
        assert any(i["field"] == "birth_year" for i in issues)

    def test_missing_name(self):
        data = {"name": ""}
        issues = validate_rules(data)
        assert any(i["field"] == "name" for i in issues)

    def test_career_date_order(self):
        data = {
            "name": "강솔찬",
            "careers": [{"start_date": "2020.01", "end_date": "2015.01"}],
        }
        issues = validate_rules(data)
        assert any(i["field"] == "careers[0].date_order" for i in issues)
        assert any(i["severity"] == "warning" for i in issues)

    def test_valid_careers(self):
        data = {
            "name": "강솔찬",
            "careers": [{"start_date": "2015.01", "end_date": "2020.01"}],
        }
        issues = validate_rules(data)
        assert not any("date_order" in i["field"] for i in issues)

    def test_career_date_order_uses_inferred_end_date(self):
        data = {
            "name": "강솔찬",
            "careers": [{"start_date": "2020.01", "end_date_inferred": "2019.12"}],
        }
        issues = validate_rules(data)
        assert any(i["field"] == "careers[0].date_order" for i in issues)

    def test_invalid_date_confidence(self):
        data = {
            "name": "강솔찬",
            "careers": [{"start_date": "2020.01", "date_confidence": 1.5}],
        }
        issues = validate_rules(data)
        assert any(i["field"] == "careers[0].date_confidence" for i in issues)


class TestCrossCheck:
    def test_name_matches(self):
        parsed = {"name": "강솔찬", "birth_year": 1985}
        extracted = {"name": "강솔찬", "birth_year": 1985}
        issues = validate_cross_check(parsed, extracted)
        assert len(issues) == 0

    def test_name_mismatch(self):
        parsed = {"name": "강솔찬", "birth_year": 1985}
        extracted = {"name": "김영희", "birth_year": 1985}
        issues = validate_cross_check(parsed, extracted)
        assert any(i["field"] == "name" for i in issues)

    def test_birth_year_mismatch(self):
        parsed = {"name": "강솔찬", "birth_year": 1985}
        extracted = {"name": "강솔찬", "birth_year": 1990}
        issues = validate_cross_check(parsed, extracted)
        assert any(i["field"] == "birth_year" for i in issues)

    def test_skip_when_filename_unparsed(self):
        parsed = {"name": None, "birth_year": None}
        extracted = {"name": "강솔찬", "birth_year": 1985}
        issues = validate_cross_check(parsed, extracted)
        assert len(issues) == 0


class TestOverallConfidence:
    def test_high_confidence(self):
        score, status = compute_overall_confidence({"overall": 0.92}, [])
        assert status == "auto_confirmed"
        assert score >= 0.85

    def test_medium_confidence(self):
        score, status = compute_overall_confidence({"overall": 0.7}, [])
        assert status == "needs_review"
        assert 0.6 <= score < 0.85

    def test_low_confidence(self):
        score, status = compute_overall_confidence({"overall": 0.4}, [])
        assert status == "failed"
        assert score < 0.6

    def test_issues_lower_confidence(self):
        issues = [
            {"field": "name", "severity": "error", "message": "missing"},
            {"field": "birth_year", "severity": "error", "message": "invalid"},
        ]
        score, status = compute_overall_confidence({"name": 0.92}, issues)
        # 0.92 - 0.05 - 0.05 = 0.82 → needs_review
        assert score < 0.85
        assert status == "needs_review"


class TestValidateExtraction:
    def test_full_validation(self):
        extracted = {
            "name": "강솔찬",
            "birth_year": 1985,
            "careers": [{"start_date": "2015.01", "end_date": "2020.01"}],
            "field_confidences": {"overall": 0.9, "name": 0.95, "birth_year": 0.9},
        }
        filename_parsed = {"name": "강솔찬", "birth_year": 1985}
        result = validate_extraction(extracted, filename_parsed)
        assert "confidence_score" in result
        assert "validation_status" in result
        assert "issues" in result
        assert "field_confidences" in result
        assert isinstance(result["confidence_score"], float)
        assert result["validation_status"] in (
            "auto_confirmed",
            "needs_review",
            "failed",
        )


class TestCriticalFieldGate:
    def test_name_missing_forces_failed(self):
        field_scores = {
            "name": 0.0,
            "email": 1.0,
            "phone": 1.0,
            "careers": 1.0,
            "educations": 1.0,
        }
        category_scores = {"인적사항": 0.67, "학력": 1.0, "경력": 1.0, "능력": 0.5}
        score, status = compute_overall_confidence(category_scores, [], field_scores)
        assert status == "failed"

    def test_no_email_no_phone_blocks_auto_confirmed(self):
        field_scores = {
            "name": 1.0,
            "email": 0.0,
            "phone": 0.0,
            "careers": 1.0,
            "educations": 1.0,
        }
        category_scores = {"인적사항": 0.33, "학력": 1.0, "경력": 1.0, "능력": 1.0}
        score, status = compute_overall_confidence(category_scores, [], field_scores)
        assert status != "auto_confirmed"

    def test_email_present_allows_auto_confirmed(self):
        field_scores = {
            "name": 1.0,
            "email": 1.0,
            "phone": 0.0,
            "careers": 1.0,
            "educations": 1.0,
        }
        category_scores = {"인적사항": 0.67, "학력": 1.0, "경력": 1.0, "능력": 1.0}
        score, status = compute_overall_confidence(category_scores, [], field_scores)
        assert status == "auto_confirmed"

    def test_phone_present_allows_auto_confirmed(self):
        field_scores = {
            "name": 1.0,
            "email": 0.0,
            "phone": 1.0,
            "careers": 1.0,
            "educations": 1.0,
        }
        category_scores = {"인적사항": 0.67, "학력": 1.0, "경력": 1.0, "능력": 1.0}
        score, status = compute_overall_confidence(category_scores, [], field_scores)
        assert status == "auto_confirmed"

    def test_no_field_scores_no_gate(self):
        """Without field_scores, gates do not apply (backward compat)."""
        category_scores = {"인적사항": 0.67, "학력": 1.0, "경력": 1.0, "능력": 1.0}
        score, status = compute_overall_confidence(category_scores, [])
        assert status == "auto_confirmed"

    def test_validate_extraction_applies_gates(self):
        """validate_extraction passes field_scores through to compute_overall_confidence."""
        extracted = {
            "name": "",
            "birth_year": 1985,
            "email": "test@example.com",
            "phone": "010-1234-5678",
            "address": "서울",
            "current_company": "삼성",
            "current_position": "과장",
            "summary": "요약",
            "careers": [{"start_date": "2020.01"}],
            "educations": [{"institution": "서울대"}],
            "skills": ["Python"],
            "certifications": [],
            "language_skills": [],
        }
        result = validate_extraction(extracted, {})
        assert result["validation_status"] == "failed"
