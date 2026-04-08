"""프로젝트 라이프사이클 상태 자동 전환 + Interview/Offer 전이 규칙."""

from django.utils import timezone

from projects.models import Interview, Offer, Project, ProjectStatus, Submission


class InvalidTransition(Exception):
    """허용되지 않는 상태 전환."""

    pass


# --- Project Status Auto-transition ---

# 라이프사이클 순서 (숫자가 클수록 후반)
STATUS_ORDER = {
    ProjectStatus.NEW: 0,
    ProjectStatus.SEARCHING: 1,
    ProjectStatus.RECOMMENDING: 2,
    ProjectStatus.INTERVIEWING: 3,
    ProjectStatus.NEGOTIATING: 4,
    ProjectStatus.CLOSED_SUCCESS: 5,
}


def maybe_advance_to_interviewing(project: Project) -> bool:
    """
    첫 Interview 생성 시 프로젝트 status 자동 전환.
    RECOMMENDING 이하 → INTERVIEWING.
    Returns True if status was changed.
    """
    current_order = STATUS_ORDER.get(project.status, -1)
    if current_order >= STATUS_ORDER[ProjectStatus.INTERVIEWING]:
        return False

    project.status = ProjectStatus.INTERVIEWING
    project.save(update_fields=["status"])
    return True


def maybe_advance_to_negotiating(project: Project) -> bool:
    """
    첫 Offer 생성 시 프로젝트 status 자동 전환.
    INTERVIEWING 이하 → NEGOTIATING.
    Returns True if status was changed.
    """
    current_order = STATUS_ORDER.get(project.status, -1)
    if current_order >= STATUS_ORDER[ProjectStatus.NEGOTIATING]:
        return False

    project.status = ProjectStatus.NEGOTIATING
    project.save(update_fields=["status"])
    return True


def maybe_advance_to_closed_success(project: Project) -> bool:
    """
    Offer accepted → CLOSED_SUCCESS.
    Returns True if status was changed.
    """
    current_order = STATUS_ORDER.get(project.status, -1)
    if current_order >= STATUS_ORDER[ProjectStatus.CLOSED_SUCCESS]:
        return False

    project.status = ProjectStatus.CLOSED_SUCCESS
    project.save(update_fields=["status"])
    return True


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
    """대기 → 합격/보류/탈락. 면접 결과 저장."""
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


# --- Offer Status Transition ---

OFFER_STATUS_TRANSITIONS = {
    Offer.Status.NEGOTIATING: {
        Offer.Status.ACCEPTED,
        Offer.Status.REJECTED,
    },
    # 수락/거절은 종료 상태 — 추가 전환 불가
}


def accept_offer(offer: Offer) -> Offer:
    """협상중 → 수락."""
    if offer.status != Offer.Status.NEGOTIATING:
        raise InvalidTransition(
            f"'{offer.get_status_display()}' 상태에서는 수락할 수 없습니다."
        )
    offer.status = Offer.Status.ACCEPTED
    offer.decided_at = timezone.now()
    offer.save(update_fields=["status", "decided_at"])
    return offer


def reject_offer(offer: Offer) -> Offer:
    """협상중 → 거절."""
    if offer.status != Offer.Status.NEGOTIATING:
        raise InvalidTransition(
            f"'{offer.get_status_display()}' 상태에서는 거절할 수 없습니다."
        )
    offer.status = Offer.Status.REJECTED
    offer.decided_at = timezone.now()
    offer.save(update_fields=["status", "decided_at"])
    return offer


# --- Offer Eligibility Check ---


def is_submission_offer_eligible(submission: Submission) -> bool:
    """해당 Submission의 최신 인터뷰 결과가 합격인지 확인."""
    latest_interview = submission.interviews.order_by("-round").first()
    if not latest_interview:
        return False
    return latest_interview.result == Interview.Result.PASSED
