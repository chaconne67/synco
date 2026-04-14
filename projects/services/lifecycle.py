"""Legacy shim -- real implementations moved to action_lifecycle.py.

voice/action_executor.py imports this module at top level, so it must exist
for app boot. Phase 6 (voice/ rewrite) will remove this file entirely.
"""

# Re-export for backward compatibility
from projects.services.action_lifecycle import (  # noqa: F401
    InvalidTransition,
    apply_interview_result,
)


def maybe_advance_to_interviewing(project) -> bool:
    return False


def maybe_advance_to_negotiating(project) -> bool:
    return False


def maybe_advance_to_closed_success(project) -> bool:
    return False


def is_submission_offer_eligible(submission) -> bool:
    return False
