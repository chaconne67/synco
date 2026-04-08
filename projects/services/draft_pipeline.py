"""SubmissionDraft 상태 전이 서비스."""

from projects.models import DraftStatus, SubmissionDraft


class InvalidDraftTransition(Exception):
    """허용되지 않는 draft 상태 전환."""

    pass


# 허용되는 상태 전이 맵
VALID_TRANSITIONS = {
    DraftStatus.PENDING: {DraftStatus.DRAFT_GENERATED},
    DraftStatus.DRAFT_GENERATED: {
        DraftStatus.CONSULTATION_ADDED,
        DraftStatus.FINALIZED,  # 상담 건너뛰기 허용
    },
    DraftStatus.CONSULTATION_ADDED: {DraftStatus.FINALIZED},
    DraftStatus.FINALIZED: {DraftStatus.REVIEWED},
    DraftStatus.REVIEWED: {
        DraftStatus.CONVERTED,
        DraftStatus.FINALIZED,  # 회귀: 재정리
    },
    DraftStatus.CONVERTED: {
        DraftStatus.REVIEWED,  # 회귀: 재검토
    },
}


def transition_draft(draft: SubmissionDraft, new_status: str) -> SubmissionDraft:
    """Draft 상태를 전환한다. 허용되지 않은 전이는 예외 발생."""
    allowed = VALID_TRANSITIONS.get(draft.status, set())
    if new_status not in allowed:
        raise InvalidDraftTransition(
            f"'{draft.get_status_display()}'에서 "
            f"'{DraftStatus(new_status).label}'(으)로 전환할 수 없습니다."
        )
    draft.status = new_status
    draft.save(update_fields=["status", "updated_at"])
    return draft
