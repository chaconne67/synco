from django import template

register = template.Library()

SIZE_BADGE_MAP = {
    "대기업": "badge enterprise",
    "중견": "badge midcap",
    "중소": "badge sme",
    "외국계": "badge foreign",
    "스타트업": "badge startup",
}


@register.filter
def size_badge_class(size):
    if not size:
        return ""
    return SIZE_BADGE_MAP.get(size, "")


@register.filter
def client_initials(name):
    if not name:
        return ""
    s = name.strip()
    first_two = "".join(s.split())[:2]
    return first_two.upper() if first_two.isascii() else first_two


@register.simple_tag
def logo_class(client):
    raw = str(client.pk).replace("-", "")
    bucket = (int(raw[:2], 16) % 8) + 1
    return f"client-logo-{bucket}"


@register.filter
def get_item(d, key):
    try:
        return d.get(key, 0)
    except AttributeError:
        return 0


_TIER_PILL_MAP = {
    "SKY": "sky",
    "SSG": "ssg",
    "JKOS": "jkos",
    "KDH": "kdh",
    "INSEOUL": "inseoul",
    "SCIENCE_ELITE": "ktech",
    "REGIONAL": "regional",
    "OVERSEAS_TOP": "overseas",
    "OVERSEAS_HIGH": "overseas",
    "OVERSEAS_GOOD": "overseas",
}


@register.filter
def tier_pill_class(tier):
    return _TIER_PILL_MAP.get(tier, "inseoul")


_LISTED_PILL_MAP = {
    "KOSPI": "kospi",
    "KOSDAQ": "kosdaq",
    "해외상장": "global",
    "비상장": "private",
}


@register.filter
def listed_pill_class(listed):
    return _LISTED_PILL_MAP.get(listed, "private")


_SIZE_PILL_MAP = {
    "대기업": "enterprise",
    "중견": "midcap",
    "중소": "sme",
    "외국계": "foreign",
    "스타트업": "startup",
}


@register.filter
def size_pill_class(size):
    return _SIZE_PILL_MAP.get(size, "enterprise")


_LEVEL_PILL_MAP = {
    "상": "lvl-high",
    "중": "lvl-mid",
    "하": "lvl-low",
}


@register.filter
def level_pill_class(level):
    return _LEVEL_PILL_MAP.get(level, "lvl-low")


@register.simple_tag
def rlogo_class(name):
    """Deterministic 1–8 bucket from company name (for gradient tile)."""
    if not name:
        return "rlogo-1"
    code = sum(ord(c) for c in name)
    return f"rlogo-{(code % 8) + 1}"
