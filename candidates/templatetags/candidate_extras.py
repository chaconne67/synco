import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe


register = template.Library()


_NOTICE_HIGHLIGHT_PATTERN = re.compile(
    r"(\d{4}년(?: \d{1,2}월)?(?:\(추정\))?|\d{1,2}년(?: \d{1,2}개월)?|\d{1,2}개월)"
)


_FIELD_LABELS = {
    "name": "이름",
    "birth_year": "출생년도",
    "email": "이메일",
    "phone": "연락처",
    "address": "주소",
    "current_company": "현재 회사",
    "current_position": "현재 직책",
    "total_experience_years": "총 경력",
    "summary": "요약",
    "careers": "경력사항",
    "educations": "학력사항",
}


@register.filter
def field_label_ko(value: str) -> str:
    return _FIELD_LABELS.get(value, value)


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
