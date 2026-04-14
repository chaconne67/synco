"""프로젝트 라이프사이클 상태 자동 전환 + Interview 전이 규칙.

Phase 1: Old ProjectStatus 10-state enum deleted. Offer model deleted.
Phase 2: Will be rewritten with new 2-phase + status/result model.
"""

from django.utils import timezone

from projects.models import Interview, Project


class InvalidTransition(Exception):
    """허용되지 않는 상태 전환."""

    pass


# --- Project lifecycle stubs (Phase 2 will implement) ---


def maybe_advance_to_interviewing(project: Project) -> bool:
    """Legacy stub — old 10-state lifecycle deleted. Phase 2 will implement."""
    return False


def maybe_advance_to_negotiating(project: Project) -> bool:
    """Legacy stub — Offer model and old lifecycle deleted. Phase 2 will implement."""
    return False


def maybe_advance_to_closed_success(project: Project) -> bool:
    """Legacy stub — old lifecycle deleted. Phase 2 will implement."""
    return False


# --- Interview Result Transition ---

INTERVIEW_RESULT_TRANSITIONS = {
    Interview.Result.PENDING: {
        Interview.Result.PASSED,
        Interview.Result.ON_HOLD,
        Interview.Result.FAILED,
    },
    # 합격/보류/탈락은 종료 상태 — 추가 전환 불가
}


def apply_interview_result(
    interview: Interview, result: str, feedback: str
) -> Interview:
    """대기 -> 합격/보류/탈락. 면접 결과 저장."""
    allowed = INTERVIEW_RESULT_TRANSITIONS.get(interview.result, set())
    if result not in allowed:
        raise InvalidTransition(
            f"'{interview.get_result_display()}' 상태에서는 결과를 변경할 수 없습니다."
        )
    if result not in Interview.Result.values:
        raise InvalidTransition(f"유효하지 않은 결과입니다: {result}")

    interview.result = result
    interview.feedback = feedback
    interview.save(update_fields=["result", "feedback"])
    return interview


# --- Offer stubs (Offer model deleted) ---


def is_submission_offer_eligible(submission) -> bool:
    """Legacy stub — Offer model deleted. Phase 2 will implement."""
    return False
