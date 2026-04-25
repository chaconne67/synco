"""Quality routing for large-scale extraction batches."""

from __future__ import annotations

MAX_RETRY_COUNT = 2

PERMANENT_ERROR_MARKERS = (
    "Text quality: empty",
    "Text quality: too_short",
    "Text quality: garbled",
    "Empty text extraction",
    "unsupported",
    "permission",
    "not found",
    "file not found",
)

TRANSIENT_ERROR_MARKERS = (
    "timeout",
    "temporarily",
    "rate limit",
    "quota",
    "internal server error",
    "service unavailable",
    "Missing text response",
    "Failed to parse JSON",
)

HIGH_RISK_FLAG_TYPES = {
    "BIRTH_YEAR_MISMATCH",
    "CAREER_DELETED",
    "CAMPUS_DEPARTMENT_MATCH",
    "SHORT_DEGREE",
    "STEP2_VALIDATION",
}


def route_error(
    error_message: str,
    *,
    retry_count: int = 0,
    has_raw_text: bool = False,
) -> dict:
    """Route hard failures by whether a retry can plausibly improve them."""
    text = error_message or ""
    lowered = text.lower()

    if any(marker.lower() in lowered for marker in PERMANENT_ERROR_MARKERS):
        return _route("permanent", "skip", "재시도해도 입력 품질이 바뀌지 않는 실패")

    retryable = has_raw_text or any(
        marker.lower() in lowered for marker in TRANSIENT_ERROR_MARKERS
    )
    if retryable and retry_count < MAX_RETRY_COUNT:
        return _route("transient", "retry_batch", "일시 오류 또는 LLM 응답 품질 이슈")
    if retryable:
        return _route("transient_exhausted", "blocked", "재시도 예산을 모두 사용함")

    return _route("unknown_failure", "blocked", "자동 재시도 근거가 부족한 실패")


def route_step1_validation(
    issues: list[dict],
    *,
    retry_count: int = 0,
) -> dict:
    """Route Step 1 warnings before creating a retry batch."""
    warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
    if warning_count and retry_count < 1:
        return _route(
            "quality_retryable",
            "retry_batch",
            "원문 누락 가능성이 있어 피드백 재추출 가치가 있음",
            priority=min(80, 40 + warning_count * 10),
        )
    if warning_count:
        return _route(
            "usable_flagged",
            "save_flagged",
            "이미 재시도했으므로 경고를 보존하고 다음 단계로 진행",
            priority=30,
        )
    return _route("clean", "next_stage", "Step 1 검증 경고 없음", priority=0)


def route_step2_validation(
    issues: list[dict],
    *,
    retry_count: int = 0,
) -> dict:
    """Route Step 2 errors before creating a retry batch.

    Step 2 검증의 error는 필수 필드 누락이나 날짜 형식 깨짐 같은 정규화 결함입니다.
    피드백을 첨부해 한 번 더 시도하면 깨끗해질 가능성이 있어 retry_batch로 분류합니다.
    """
    error_count = sum(1 for issue in issues if issue.get("severity") == "error")
    if error_count and retry_count < 1:
        return _route(
            "quality_retryable",
            "retry_batch",
            "정규화 결함이 있어 피드백 재시도 가치가 있음",
            priority=min(85, 50 + error_count * 10),
        )
    if error_count:
        return _route(
            "usable_flagged",
            "save_flagged",
            "이미 재시도했으므로 결함을 RED 플래그로 surface하고 다음 단계로 진행",
            priority=35,
        )
    return _route("clean", "next_stage", "Step 2 검증 오류 없음", priority=0)


def route_pipeline_result(pipeline_result: dict) -> dict:
    """Route structured extraction output after final diagnosis."""
    diagnosis = pipeline_result.get("diagnosis") or {}
    extracted = pipeline_result.get("extracted") or {}
    flags = (
        pipeline_result.get("integrity_flags") or extracted.get("integrity_flags") or []
    )
    score = diagnosis.get("overall_score") or 0.0
    red_flags = [flag for flag in flags if flag.get("severity") == "RED"]
    high_risk_reds = [
        flag for flag in red_flags if flag.get("type") in HIGH_RISK_FLAG_TYPES
    ]

    has_name = bool(extracted.get("name"))
    has_profile = bool(extracted.get("careers") or extracted.get("educations"))
    if not has_name or not has_profile:
        return _route(
            "human_review",
            "human_review",
            "핵심 식별/프로필 필드가 부족해 자동 활용이 어려움",
            priority=90,
        )

    if high_risk_reds:
        return _route(
            "human_review",
            "human_review",
            "고위험 불일치가 있어 소량 검토 큐로 보내야 함",
            priority=95,
        )

    if red_flags and score < 0.6:
        return _route(
            "low_confidence",
            "blocked",
            "낮은 신뢰도와 RED flag가 함께 있어 자동 활용 보류",
            priority=75,
        )

    if diagnosis.get("verdict") == "pass" and score >= 0.85:
        return _route("clean", "next_stage", "자동 확인 가능한 품질", priority=0)

    return _route(
        "usable_flagged",
        "save_flagged",
        "구조화 데이터는 사용 가능하나 경고/낮은 신뢰도 표시 필요",
        priority=45 if score >= 0.6 else 65,
    )


def _route(
    reason_class: str,
    next_action: str,
    reason: str,
    *,
    priority: int = 50,
) -> dict:
    return {
        "reason_class": reason_class,
        "next_action": next_action,
        "review_priority": priority,
        "reason": reason,
    }
