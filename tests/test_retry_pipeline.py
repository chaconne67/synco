from unittest.mock import patch

from candidates.services.retry_pipeline import run_extraction_with_retry


@patch("candidates.services.retry_pipeline.get_fewshot_examples", return_value=[])
@patch("candidates.services.retry_pipeline.validate_with_codex")
@patch("candidates.services.retry_pipeline.extract_candidate_data")
def test_pass_on_first_attempt(mock_extract, mock_codex, mock_fewshot):
    mock_extract.return_value = {"name": "홍길동", "careers": []}
    mock_codex.return_value = {
        "verdict": "pass",
        "issues": [],
        "field_scores": {"name": 1.0},
        "overall_score": 0.95,
    }
    result = run_extraction_with_retry(
        raw_text="홍길동 이력서",
        file_path="/tmp/test.docx",
        category="HR",
        filename_meta={"name": "홍길동"},
    )
    assert result["extracted"]["name"] == "홍길동"
    assert result["diagnosis"]["verdict"] == "pass"
    assert result["attempts"] == 1
    assert mock_extract.call_count == 1


@patch("shutil.which", return_value="/usr/bin/libreoffice")
@patch("candidates.services.retry_pipeline.get_fewshot_examples", return_value=[])
@patch("candidates.services.retry_pipeline.validate_with_codex")
@patch("candidates.services.retry_pipeline.extract_candidate_data")
@patch("candidates.services.retry_pipeline.extract_text_libreoffice")
def test_retry_on_text_extraction_failure(
    mock_libre, mock_extract, mock_codex, mock_fewshot, mock_which
):
    mock_extract.side_effect = [
        {"name": "홍길동", "careers": [{"company": "A", "start_date": ""}]},
        {"name": "홍길동", "careers": [{"company": "A", "start_date": "2020-01"}]},
    ]
    mock_codex.side_effect = [
        {
            "verdict": "fail",
            "issues": [
                {
                    "field": "careers[0].start_date",
                    "root_cause": "text_extraction",
                    "severity": "critical",
                    "type": "missing",
                    "evidence": "...",
                    "suggested_value": "2020-01",
                }
            ],
            "field_scores": {},
            "overall_score": 0.5,
        },
        {"verdict": "pass", "issues": [], "field_scores": {}, "overall_score": 0.92},
    ]
    mock_libre.return_value = "홍길동 재추출 텍스트 2020-01"
    result = run_extraction_with_retry(
        raw_text="홍길동 원본",
        file_path="/tmp/test.docx",
        category="HR",
        filename_meta={},
    )
    assert result["diagnosis"]["verdict"] == "pass"
    assert result["attempts"] == 2
    assert mock_libre.call_count == 1


@patch("candidates.services.retry_pipeline.get_fewshot_examples", return_value=[])
@patch("candidates.services.retry_pipeline.validate_with_codex")
@patch("candidates.services.retry_pipeline.extract_candidate_data")
def test_retry_on_llm_parsing_failure(mock_extract, mock_codex, mock_fewshot):
    mock_extract.side_effect = [
        {"name": "홍길동", "careers": [{"company": "", "start_date": ""}]},
        {
            "name": "홍길동",
            "careers": [{"company": "삼성전자", "start_date": "2020-01"}],
        },
    ]
    mock_codex.side_effect = [
        {
            "verdict": "fail",
            "issues": [
                {
                    "field": "careers[0].company",
                    "root_cause": "llm_parsing",
                    "severity": "critical",
                    "type": "missing",
                    "evidence": "원본에 삼성전자 있음",
                    "suggested_value": "삼성전자",
                }
            ],
            "field_scores": {},
            "overall_score": 0.4,
        },
        {"verdict": "pass", "issues": [], "field_scores": {}, "overall_score": 0.90},
    ]
    result = run_extraction_with_retry(
        raw_text="삼성전자 홍길동",
        file_path="/tmp/test.docx",
        category="HR",
        filename_meta={},
    )
    assert result["diagnosis"]["verdict"] == "pass"
    assert result["attempts"] == 2


@patch("candidates.services.retry_pipeline.get_fewshot_examples", return_value=[])
@patch("candidates.services.retry_pipeline.validate_with_codex")
@patch("candidates.services.retry_pipeline.extract_candidate_data")
def test_max_retries_exhausted(mock_extract, mock_codex, mock_fewshot):
    mock_extract.return_value = {"name": "홍길동", "careers": []}
    mock_codex.return_value = {
        "verdict": "fail",
        "issues": [
            {
                "field": "careers",
                "root_cause": "ambiguous_source",
                "severity": "critical",
                "type": "missing",
                "evidence": "...",
                "suggested_value": "",
            }
        ],
        "field_scores": {},
        "overall_score": 0.3,
    }
    result = run_extraction_with_retry(
        raw_text="홍길동", file_path="/tmp/test.docx", category="HR", filename_meta={}
    )
    assert result["diagnosis"]["verdict"] == "fail"
    assert result["retry_action"] == "human_review"
    assert result["attempts"] <= 4


@patch("candidates.services.retry_pipeline.get_fewshot_examples", return_value=[])
@patch("candidates.services.retry_pipeline.validate_with_codex")
@patch("candidates.services.retry_pipeline.extract_candidate_data")
def test_run_extraction_with_retry_returns_raw_text_used(
    mock_extract, mock_codex, mock_fewshot
):
    mock_extract.return_value = {"name": "테스트"}
    mock_codex.return_value = {
        "verdict": "pass",
        "issues": [],
        "field_scores": {},
        "overall_score": 0.95,
    }
    result = run_extraction_with_retry("원본텍스트", "/tmp/t.docx", "HR", {})
    assert result["raw_text_used"] == "원본텍스트"
