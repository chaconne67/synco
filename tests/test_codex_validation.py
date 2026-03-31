import json
from unittest.mock import patch
from candidates.services.codex_validation import validate_with_codex

MOCK_CODEX_RESPONSE = json.dumps(
    {
        "verdict": "fail",
        "issues": [
            {
                "field": "careers[0].start_date",
                "type": "missing",
                "evidence": "원본에 'Dec. 2016 – May 2025' 존재하나 추출 결과에 없음",
                "root_cause": "text_extraction",
                "severity": "critical",
                "suggested_value": "2016-12",
            }
        ],
        "field_scores": {"name": 1.0, "careers": 0.3, "educations": 0.9},
        "overall_score": 0.55,
    }
)


@patch("candidates.services.codex_validation._call_codex_cli")
def test_validate_with_codex_fail(mock_call):
    mock_call.return_value = MOCK_CODEX_RESPONSE
    raw_text = "김홍안 이력서 원본 텍스트..."
    extracted = {
        "name": "김홍안",
        "careers": [{"company": "북미공장", "start_date": ""}],
    }
    filename_meta = {"name": "김홍안", "companies": ["대한솔루션", "LG엔솔"]}
    result = validate_with_codex(raw_text, extracted, filename_meta)
    assert result["verdict"] == "fail"
    assert len(result["issues"]) == 1
    assert result["issues"][0]["root_cause"] == "text_extraction"
    assert result["overall_score"] == 0.55


@patch("candidates.services.codex_validation._call_codex_cli")
def test_validate_with_codex_pass(mock_call):
    mock_call.return_value = json.dumps(
        {
            "verdict": "pass",
            "issues": [],
            "field_scores": {"name": 1.0, "careers": 0.95, "educations": 0.9},
            "overall_score": 0.95,
        }
    )
    result = validate_with_codex("text", {"name": "홍길동"}, {})
    assert result["verdict"] == "pass"
    assert result["overall_score"] == 0.95


@patch("candidates.services.codex_validation._call_codex_cli")
def test_validate_with_codex_cli_failure_returns_fallback(mock_call):
    mock_call.side_effect = RuntimeError("codex timeout")
    result = validate_with_codex("text", {"name": "홍길동"}, {})
    assert result["verdict"] == "error"
    assert result["overall_score"] == 0.0
