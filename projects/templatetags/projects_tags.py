"""Custom template tags for projects app."""

from django import template

from projects.models import CARD_STAGES_ORDER

register = template.Library()


@register.simple_tag
def card_stages():
    """후보자 카드 진행바용 7단계 (서칭 제외)."""
    return CARD_STAGES_ORDER
