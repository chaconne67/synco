import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe


register = template.Library()


_NOTICE_HIGHLIGHT_PATTERN = re.compile(
    r"(\d{4}년(?: \d{1,2}월)?(?:\(추정\))?|\d{1,2}년(?: \d{1,2}개월)?|\d{1,2}개월)"
)


@register.filter
def highlight_notice_metrics(value: str) -> str:
    if not value:
        return ""

    escaped = escape(value)
    highlighted = _NOTICE_HIGHLIGHT_PATTERN.sub(
        r'<strong class="font-semibold text-inherit">\1</strong>',
        escaped,
    )
    return mark_safe(highlighted)
