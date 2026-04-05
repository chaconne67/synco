from unittest.mock import patch

from data_extraction.services.pipeline import (
    apply_cross_version_comparison,
    run_extraction_with_retry,
)


@patch("data_extraction.services.pipeline.validate_extraction")
@patch("data_extraction.services.pipeline.extract_candidate_data")
def test_pass_on_first_attempt(mock_extract, mock_validate):
    mock_extract.return_value = {"name": "홍길동", "careers": []}
    mock_validate.return_value = {
        "confidence_score": 0.95,
        "validation_status": "auto_confirmed",
        "field_confidences": {"name": 1.0},
        "issues": [],
    }
    result = run_extraction_with_retry(
        raw_text="홍길동 이력서\n서울시 강남구\n삼성전자 2020-2024 개발팀 팀장\n학력사항: 서울대 컴퓨터공학과 졸업\n이메일: test@test.com\n연락처: 010-1234-5678\n자기소개: 10년 경력의 개발자입니다.",
        file_path="/tmp/test.docx",
        category="HR",
        filename_meta={"name": "홍길동"},
    )
    assert result["extracted"]["name"] == "홍길동"
    assert result["diagnosis"]["verdict"] == "pass"
    assert result["attempts"] == 1
    assert result["retry_action"] == "none"


@patch("data_extraction.services.pipeline.validate_extraction")
@patch("data_extraction.services.pipeline.extract_candidate_data")
def test_fail_triggers_human_review(mock_extract, mock_validate):
    mock_extract.return_value = {"name": "홍길동", "careers": []}
    mock_validate.return_value = {
        "confidence_score": 0.5,
        "validation_status": "failed",
        "field_confidences": {"name": 1.0, "careers": 0.3},
        "issues": [
            {"field": "careers", "severity": "error", "message": "No careers found"}
        ],
    }
    result = run_extraction_with_retry(
        raw_text="홍길동 이력서\n서울시 강남구\n삼성전자 2020-2024 개발팀 팀장\n학력사항: 서울대 컴퓨터공학과 졸업\n이메일: test@test.com\n연락처: 010-1234-5678\n자기소개: 10년 경력의 개발자입니다.",
        file_path="/tmp/test.docx",
        category="HR",
        filename_meta={},
    )
    assert result["diagnosis"]["verdict"] == "fail"
    assert result["retry_action"] == "human_review"
    assert result["attempts"] == 1


@patch("data_extraction.services.pipeline.extract_candidate_data")
def test_extraction_returns_none(mock_extract):
    mock_extract.return_value = None
    result = run_extraction_with_retry(
        raw_text="garbage text for extraction test with enough length to pass quality gate",
        file_path="/tmp/test.docx",
        category="HR",
        filename_meta={},
    )
    assert result["extracted"] is None
    assert result["diagnosis"]["verdict"] == "fail"
    assert result["retry_action"] == "human_review"


@patch("data_extraction.services.pipeline.validate_extraction")
@patch("data_extraction.services.pipeline.extract_candidate_data")
def test_returns_raw_text_used(mock_extract, mock_validate):
    mock_extract.return_value = {"name": "테스트"}
    mock_validate.return_value = {
        "confidence_score": 0.95,
        "validation_status": "auto_confirmed",
        "field_confidences": {},
        "issues": [],
    }
    long_text = "원본텍스트 이력서 내용 " * 10
    result = run_extraction_with_retry(long_text, "/tmp/t.docx", "HR", {})
    assert result["raw_text_used"] == long_text


@patch("data_extraction.services.pipeline.validate_extraction")
@patch("data_extraction.services.pipeline.extract_candidate_data")
def test_applies_regex_filters_before_validation(mock_extract, mock_validate):
    mock_extract.return_value = {
        "name": "테스트",
        "phone": "+966-5078-50224 / +82-10-9034-5062",
        "resume_reference_date": "2025년 12월 기준",
        "careers": [],
        "certifications": [],
        "language_skills": [],
    }
    mock_validate.return_value = {
        "confidence_score": 0.95,
        "validation_status": "auto_confirmed",
        "field_confidences": {},
        "issues": [],
    }

    result = run_extraction_with_retry("원본텍스트 이력서 내용 " * 10, "/tmp/t.docx", "HR", {})

    assert result["extracted"]["phone"] == "+82-10-9034-5062"
    assert result["extracted"]["resume_reference_date"] == "2025-12"


def test_apply_cross_version_comparison_updates_flags_and_score():
    pipeline_result = {
        "extracted": {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2022-06"},
            ],
            "educations": [],
            "field_confidences": {},
        },
        "diagnosis": {
            "verdict": "pass",
            "issues": [],
            "field_scores": {},
            "overall_score": 1.0,
        },
        "attempts": 1,
        "retry_action": "none",
        "raw_text_used": "원본텍스트",
        "integrity_flags": [],
    }

    updated = apply_cross_version_comparison(
        pipeline_result,
        previous_data={
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2022-06"},
                {"company": "B사", "start_date": "2018-01", "end_date": "2019-12"},
            ],
            "educations": [],
        },
    )

    assert len(updated["integrity_flags"]) == 1
    assert updated["integrity_flags"][0]["type"] == "CAREER_DELETED"
    assert updated["diagnosis"]["overall_score"] < 1.0
