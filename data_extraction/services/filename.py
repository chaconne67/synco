"""Parse Korean resume filenames to extract name + birth year, and group files by person."""

from __future__ import annotations

import re

# Known resume file extensions to strip
_EXTENSIONS = {".doc", ".docx", ".pdf", ".hwp"}

# Korean name: 2-4 hangul characters
_KOREAN_NAME_RE = re.compile(r"^[\uac00-\ud7a3]{2,4}$")

# Birth year patterns
_TWO_DIGIT_YEAR_RE = re.compile(r"^\d{2}$")
_FOUR_DIGIT_YEAR_RE = re.compile(r"^\d{4}$")


def _normalize_year(raw: str) -> int | None:
    """Convert a 2- or 4-digit string to a full birth year, or None if invalid."""
    if _FOUR_DIGIT_YEAR_RE.match(raw):
        year = int(raw)
        if 1950 <= year <= 2010:
            return year
        return None
    if _TWO_DIGIT_YEAR_RE.match(raw):
        y = int(raw)
        if 50 <= y <= 99:
            return 1900 + y
        elif 0 <= y <= 25:
            return 2000 + y
        return None
    return None


def _strip_extension(file_name: str) -> str:
    """Remove known file extension from the filename."""
    for ext in _EXTENSIONS:
        if file_name.lower().endswith(ext):
            return file_name[: -len(ext)]
    return file_name


def _split_tokens(stem: str) -> list[str]:
    """Split a filename stem into tokens, handling dot/hyphen/underscore separators
    and parenthesized groups like '강솔찬(85)'."""
    # First, expand parenthesized groups: "강솔찬(85)" → "강솔찬.85"
    stem = re.sub(r"\(([^)]+)\)", r".\1", stem)
    # Split on dots, hyphens, underscores
    tokens = re.split(r"[.\-_]", stem)
    return [t for t in tokens if t]


def parse_filename(file_name: str) -> dict:
    """Parse a Korean resume filename to extract name, birth year, and extra metadata.

    Returns {"name": str|None, "birth_year": int|None, "extra": list[str]}.
    """
    stem = _strip_extension(file_name)
    tokens = _split_tokens(stem)

    if not tokens:
        return {"name": None, "birth_year": None, "extra": []}

    name: str | None = None
    birth_year: int | None = None
    extra: list[str] = []

    for token in tokens:
        if name is None and _KOREAN_NAME_RE.match(token):
            name = token
        elif birth_year is None and (year := _normalize_year(token)) is not None:
            birth_year = year
        else:
            extra.append(token)

    # If we couldn't find a Korean name, treat the whole thing as unparseable
    if name is None:
        return {"name": None, "birth_year": None, "extra": []}

    return {"name": name, "birth_year": birth_year, "extra": extra}


def group_by_person(files: list[dict]) -> list[dict]:
    """Group resume files by (name, birth_year).

    Input: list of dicts with at least "file_name" and "modified_time" keys.
    Returns: list of group dicts with "key", "parsed", "primary", "others".
    """
    groups: dict[tuple, list[tuple[dict, dict]]] = {}
    unparseable: list[tuple[dict, dict]] = []

    for f in files:
        parsed = parse_filename(f["file_name"])
        if parsed["name"] is None:
            unparseable.append((f, parsed))
        else:
            key = (parsed["name"], parsed["birth_year"])
            groups.setdefault(key, []).append((f, parsed))

    result: list[dict] = []

    # Parsed groups
    for key, items in groups.items():
        # Sort by modified_time descending (newest first)
        items.sort(key=lambda x: x[0]["modified_time"], reverse=True)
        primary_file, primary_parsed = items[0]
        others = [item[0] for item in items[1:]]
        result.append(
            {
                "key": key,
                "parsed": primary_parsed,
                "primary": primary_file,
                "others": others,
            }
        )

    # Unparseable files as individual groups
    for f, parsed in unparseable:
        result.append(
            {
                "key": (f["file_name"],),
                "parsed": parsed,
                "primary": f,
                "others": [],
            }
        )

    return result
