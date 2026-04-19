"""Custom template tags for projects app."""

from django import template

from projects.models import CARD_STAGES_ORDER

register = template.Library()


@register.simple_tag
def card_stages():
    """후보자 카드 진행바용 7단계 (서칭 제외)."""
    return CARD_STAGES_ORDER


@register.simple_tag
def card_stages_for(application):
    """진행바 표시용 (stage_id, label, state). state는 current 위치 기준 선형 표시.

    state: 'passed' (current 이전) | 'current' | 'upcoming' (current 이후).
    실제 stages_passed에 뒷 단계가 들어있어도 UI는 선형으로 노출.
    hired면 전 단계 passed + hired current.
    """
    cur = application.current_stage
    # hired / None 처리
    if cur == "hired":
        return [(sid, label, "passed") for sid, label in CARD_STAGES_ORDER[:-1]] + [
            (CARD_STAGES_ORDER[-1][0], CARD_STAGES_ORDER[-1][1], "current")
        ]
    if cur is None:  # dropped
        return [(sid, label, "upcoming") for sid, label in CARD_STAGES_ORDER]

    ids = [sid for sid, _ in CARD_STAGES_ORDER]
    try:
        cur_idx = ids.index(cur)
    except ValueError:
        cur_idx = -1

    result = []
    for idx, (sid, label) in enumerate(CARD_STAGES_ORDER):
        if idx < cur_idx:
            state = "passed"
        elif idx == cur_idx:
            state = "current"
        else:
            state = "upcoming"
        result.append((sid, label, state))
    return result
