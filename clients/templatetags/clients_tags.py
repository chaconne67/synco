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
