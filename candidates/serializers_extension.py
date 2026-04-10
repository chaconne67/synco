import re
from html import unescape

MAX_PAYLOAD_SIZE = 100 * 1024  # 100KB

FIELD_LIMITS = {
    "name": 100,
    "current_company": 255,
    "current_position": 255,
    "address": 500,
    "email": 254,
    "phone": 255,
    "external_profile_url": 500,
}

ARRAY_LIMITS = {
    "careers": 50,
    "educations": 20,
    "skills": 100,
}


def safe_str(val) -> str:
    """None-safe string conversion. None -> "", else str(val)."""
    if val is None:
        return ""
    return str(val)


def strip_html(value: str) -> str:
    """HTML 태그 제거, 엔티티 디코딩."""
    cleaned = re.sub(r"<[^>]+>", "", value)
    return unescape(cleaned).strip()


def normalize_url(url: str) -> str:
    """외부 프로필 URL 정규화. 서버에서만 수행."""
    from urllib.parse import urlsplit, urlunsplit

    url = url.strip()
    if not url:
        return ""
    parts = urlsplit(url)
    # Remove query, fragment, trailing slash
    normalized = urlunsplit(
        (parts.scheme, parts.netloc, parts.path.rstrip("/"), "", "")
    )
    return normalized.lower()


def normalize_company(name: str) -> str:
    """회사명 정규화 (비교용)."""
    name = name.strip().lower()
    # Remove common Korean legal suffixes
    for suffix in ["(주)", "주식회사", "(유)", "유한회사", "㈜"]:
        name = name.replace(suffix, "")
    return name.strip()


def parse_int_or_none(val) -> int | None:
    """안전한 정수 파싱. 실패 시 None."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    try:
        # Handle strings like "2020", "2020년"
        digits = re.sub(r"\D", "", str(val))
        if digits and len(digits) <= 4:
            return int(digits)
    except (ValueError, TypeError):
        pass
    return None


def _validate_dict_item(item, field_keys: list[str]) -> dict | None:
    """배열 요소가 dict인지 확인. 아니면 None."""
    if not isinstance(item, dict):
        return None
    return {k: strip_html(safe_str(item.get(k, ""))) for k in field_keys}


def validate_profile_data(raw_data: dict) -> tuple[dict | None, list[str]]:
    """프로필 데이터 검증. (cleaned_data, errors) 반환."""
    errors = []

    # Required: name
    name = strip_html(safe_str(raw_data.get("name", "")).strip())
    if not name:
        errors.append("name is required")

    # Build cleaned fields
    company = strip_html(safe_str(raw_data.get("current_company", "")))
    position = strip_html(safe_str(raw_data.get("current_position", "")))
    email = safe_str(raw_data.get("email", "")).strip().lower()
    phone = safe_str(raw_data.get("phone", ""))
    ext_url = normalize_url(safe_str(raw_data.get("external_profile_url", "")))

    # Phone normalization for secondary check
    from candidates.services.candidate_identity import normalize_phone_for_matching

    normalized_phone = normalize_phone_for_matching(phone)
    phone_valid = len(normalized_phone) >= 10

    # Secondary identifier check (at least one required)
    if not any([company, position, email, ext_url, phone_valid]):
        errors.append(
            "At least one of company, position, email, external_profile_url, "
            "or phone (10+ digits) required"
        )

    # Identity field length validation (reject, not truncate)
    if email and len(email) > FIELD_LIMITS["email"]:
        errors.append(f"email exceeds {FIELD_LIMITS['email']} chars")
    if ext_url and len(ext_url) > FIELD_LIMITS["external_profile_url"]:
        errors.append(
            f"external_profile_url exceeds {FIELD_LIMITS['external_profile_url']} chars"
        )

    if errors:
        return None, errors

    cleaned = {
        "name": name[: FIELD_LIMITS["name"]],
        "current_company": company[: FIELD_LIMITS["current_company"]],
        "current_position": position[: FIELD_LIMITS["current_position"]],
        "address": strip_html(safe_str(raw_data.get("address", "")))[
            : FIELD_LIMITS["address"]
        ],
        "email": email,
        "phone": phone[: FIELD_LIMITS["phone"]],
        "phone_normalized": normalized_phone,
        "external_profile_url": ext_url,
        "source_site": safe_str(raw_data.get("source_site", ""))[:20],
        "source_url": safe_str(raw_data.get("source_url", ""))[:500],
        "parse_quality": safe_str(raw_data.get("parse_quality", "complete"))[:20],
    }

    # Validate email format
    if cleaned["email"] and "@" not in cleaned["email"]:
        errors.append("Invalid email format")

    # Validate URL
    if cleaned["external_profile_url"] and not cleaned[
        "external_profile_url"
    ].startswith("http"):
        errors.append("external_profile_url must start with http")

    # Array fields — validate each item is dict
    career_keys = [
        "company",
        "position",
        "department",
        "start_date",
        "end_date",
        "is_current",
        "duties",
    ]
    careers_raw = raw_data.get("careers", [])
    if not isinstance(careers_raw, list):
        careers_raw = []
    cleaned["careers"] = [
        item
        for item in (
            _validate_dict_item(c, career_keys)
            for c in careers_raw[: ARRAY_LIMITS["careers"]]
        )
        if item is not None
    ]

    edu_keys = ["institution", "degree", "major", "start_year", "end_year"]
    edus_raw = raw_data.get("educations", [])
    if not isinstance(edus_raw, list):
        edus_raw = []
    cleaned["educations"] = [
        item
        for item in (
            _validate_dict_item(e, edu_keys)
            for e in edus_raw[: ARRAY_LIMITS["educations"]]
        )
        if item is not None
    ]

    skills_raw = raw_data.get("skills", [])
    if not isinstance(skills_raw, list):
        skills_raw = []
    cleaned["skills"] = [
        strip_html(safe_str(s))[:100] for s in skills_raw[: ARRAY_LIMITS["skills"]]
    ]

    # Update mode fields
    cleaned["update_mode"] = bool(raw_data.get("update_mode", False))
    cleaned["candidate_id"] = safe_str(raw_data.get("candidate_id", ""))
    cleaned["fields"] = raw_data.get("fields", [])

    # Confirmed new records for update mode
    new_careers_raw = raw_data.get("new_careers_confirmed", [])
    if not isinstance(new_careers_raw, list):
        new_careers_raw = []
    cleaned["new_careers_confirmed"] = [
        item
        for item in (
            _validate_dict_item(c, career_keys)
            for c in new_careers_raw[: ARRAY_LIMITS["careers"]]
        )
        if item is not None
    ]

    new_edus_raw = raw_data.get("new_educations_confirmed", [])
    if not isinstance(new_edus_raw, list):
        new_edus_raw = []
    cleaned["new_educations_confirmed"] = [
        item
        for item in (
            _validate_dict_item(e, edu_keys)
            for e in new_edus_raw[: ARRAY_LIMITS["educations"]]
        )
        if item is not None
    ]

    if errors:
        return None, errors

    return cleaned, []
