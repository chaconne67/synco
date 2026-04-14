"""컨택 중복 체크 + 잠금 관리 서비스.

Phase 1: Contact model deleted. This entire module is legacy.
Phase 2-6: Will be replaced with Application/ActionItem-based flow.
All functions are stubs that raise NotImplementedError.
"""


def check_duplicate(project, candidate):
    """Legacy stub — Contact model deleted."""
    return {"blocked": False, "warnings": [], "other_projects": []}


def create_contact(**kwargs):
    """Legacy stub — Contact model deleted."""
    raise NotImplementedError("Contact model deleted in Phase 1")


def reserve_candidates(project, candidate_ids, consultant):
    """Legacy stub — Contact model deleted."""
    raise NotImplementedError("Contact model deleted in Phase 1")


def release_expired_reservations():
    """Legacy stub — Contact model deleted."""
    return 0
