from django import template

register = template.Library()


_LEVEL_MAP_4 = {"native", "원어민", "모국어", "상", "a"}
_LEVEL_MAP_3 = {"business", "fluent", "advanced", "고급", "중상", "b"}
_LEVEL_MAP_2 = {"conversational", "intermediate", "중급", "중", "c"}
_LEVEL_MAP_1 = {"basic", "beginner", "초급", "하", "d"}


def _match_keyword(text, keywords):
    """Check if any keyword matches in text (case-insensitive, substring match)."""
    text_lower = text.lower()
    for k in keywords:
        k_lower = k.lower()
        # For multi-char keywords, check substring; for single char, check word boundary
        if len(k_lower) > 1:
            if k_lower in text_lower:
                return True
        else:
            # Single character: must be whole word (word boundaries)
            if f" {k_lower} " in f" {text_lower} ":
                return True
    return False


@register.simple_tag
def language_level_bars(lang) -> int:
    """Return 1-4 for UI dot bar."""
    level = (getattr(lang, "level", "") or "").strip()
    test = (getattr(lang, "test_name", "") or "").strip()
    score = (getattr(lang, "score", "") or "").strip()
    blob = f"{level} {test} {score}"

    if _match_keyword(blob, _LEVEL_MAP_4):
        return 4
    if _match_keyword(blob, _LEVEL_MAP_3):
        return 3
    if _match_keyword(blob, _LEVEL_MAP_2):
        return 2
    if _match_keyword(blob, _LEVEL_MAP_1):
        return 1
    return 2  # default when info is missing


@register.simple_tag
def review_notice_pill(candidate):
    """Return pill dict {severity, count, label, classes} or None if no notices."""
    red = getattr(candidate, "review_notice_red_count", 0) or 0
    yellow = getattr(candidate, "review_notice_yellow_count", 0) or 0
    blue = getattr(candidate, "review_notice_blue_count", 0) or 0
    if red:
        return {
            "severity": "red",
            "count": red,
            "label": f"중요 {red}건",
            "classes": "text-rose-700 bg-rose-50 border-rose-100",
        }
    if yellow:
        return {
            "severity": "yellow",
            "count": yellow,
            "label": f"주의 {yellow}건",
            "classes": "text-amber-700 bg-amber-50 border-amber-100",
        }
    if blue:
        return {
            "severity": "blue",
            "count": blue,
            "label": f"참고 {blue}건",
            "classes": "text-slate-600 bg-slate-50 border-slate-100",
        }
    return None
