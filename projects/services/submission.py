"""Submission 상태 전환 + 프로젝트 status 연동."""

from django.utils import timezone

from projects.models import Project, ProjectStatus, Submission


class InvalidTransition(Exception):
    """허용되지 않는 상태 전환."""

    pass


# 허용되는 상태 전환
VALID_TRANSITIONS = {
    Submission.Status.DRAFTING: {Submission.Status.SUBMITTED},
    Submission.Status.SUBMITTED: {Submission.Status.PASSED, Submission.Status.REJECTED},
    # 통과/탈락은 종료 상태 — 추가 전환 불가
}


def submit_to_client(submission: Submission) -> Submission:
    """작성중 → 제출. submitted_at 기록."""
    if submission.status != Submission.Status.DRAFTING:
        raise InvalidTransition(
            f"'{submission.get_status_display()}' 상태에서는 제출할 수 없습니다."
        )
    submission.status = Submission.Status.SUBMITTED
    submission.submitted_at = timezone.now()
    submission.save(update_fields=["status", "submitted_at"])
    return submission


def apply_client_feedback(
    submission: Submission, result: str, feedback: str
) -> Submission:
    """제출 → 통과/탈락. 고객사 피드백 저장."""
    if submission.status != Submission.Status.SUBMITTED:
        raise InvalidTransition(
            f"'{submission.get_status_display()}' 상태에서는 피드백을 입력할 수 없습니다."
        )
    if result not in (Submission.Status.PASSED, Submission.Status.REJECTED):
        raise InvalidTransition(f"유효하지 않은 결과입니다: {result}")

    submission.status = result
    submission.client_feedback = feedback
    submission.client_feedback_at = timezone.now()
    submission.save(update_fields=["status", "client_feedback", "client_feedback_at"])
    return submission


def maybe_advance_project_status(project: Project) -> bool:
    """
    첫 Submission 생성 시 프로젝트 status 자동 전환.
    NEW 또는 SEARCHING → RECOMMENDING.
    Returns True if status was changed.
    """
    if project.status not in (ProjectStatus.NEW, ProjectStatus.SEARCHING):
        return False

    project.status = ProjectStatus.RECOMMENDING
    project.save(update_fields=["status"])
    return True
