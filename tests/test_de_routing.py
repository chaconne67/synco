from data_extraction.services.extraction.routing import (
    route_error,
    route_pipeline_result,
    route_step1_validation,
)


def test_route_error_skips_permanent_text_quality_failure():
    routing = route_error("Text quality: too_short", has_raw_text=False)

    assert routing["reason_class"] == "permanent"
    assert routing["next_action"] == "skip"


def test_route_error_retries_transient_llm_failure_with_raw_text():
    routing = route_error(
        "Failed to parse JSON extraction output",
        has_raw_text=True,
    )

    assert routing["reason_class"] == "transient"
    assert routing["next_action"] == "retry_batch"


def test_route_error_blocks_after_retry_budget():
    routing = route_error(
        "Failed to parse JSON extraction output",
        retry_count=2,
        has_raw_text=True,
    )

    assert routing["reason_class"] == "transient_exhausted"
    assert routing["next_action"] == "blocked"


def test_route_step1_validation_retries_once_then_saves_flagged():
    issues = [{"severity": "warning", "message": "section missed"}]

    first = route_step1_validation(issues, retry_count=0)
    second = route_step1_validation(issues, retry_count=1)

    assert first["next_action"] == "retry_batch"
    assert second["next_action"] == "save_flagged"


def test_route_pipeline_result_saves_usable_low_risk_flags():
    routing = route_pipeline_result(
        {
            "extracted": {
                "name": "홍길동",
                "careers": [{"company": "A"}],
                "educations": [],
            },
            "diagnosis": {"verdict": "pass", "overall_score": 0.75},
            "integrity_flags": [
                {
                    "type": "CAMPUS_MISSING",
                    "severity": "YELLOW",
                    "field": "educations",
                }
            ],
        }
    )

    assert routing["reason_class"] == "usable_flagged"
    assert routing["next_action"] == "save_flagged"


def test_route_pipeline_result_sends_high_risk_red_to_human_review():
    routing = route_pipeline_result(
        {
            "extracted": {
                "name": "홍길동",
                "careers": [{"company": "A"}],
                "educations": [],
            },
            "diagnosis": {"verdict": "fail", "overall_score": 0.7},
            "integrity_flags": [
                {
                    "type": "BIRTH_YEAR_MISMATCH",
                    "severity": "RED",
                    "field": "birth_year",
                }
            ],
        }
    )

    assert routing["reason_class"] == "human_review"
    assert routing["next_action"] == "human_review"
