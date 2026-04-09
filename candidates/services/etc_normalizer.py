"""_etc.type canonicalization, splitting, and shape normalization.

Splits _etc JSONFields by canonical type and transforms items through
detail_normalizers to match the UI-expected shape.
"""

from __future__ import annotations

from candidates.services.detail_normalizers import (
    normalize_awards,
    normalize_overseas,
    normalize_patents,
    normalize_projects,
    normalize_trainings,
)

# ---------------------------------------------------------------------------
# Alias maps: exact string → canonical type
# ---------------------------------------------------------------------------

_CAREER_ETC_ALIASES: dict[str, str] = {
    "퇴사 사유": "퇴사사유",
    "입사/퇴사 사유": "퇴사사유",
    "입사계기 및 퇴사이유": "퇴사사유",
    "입사 계기 및 퇴사 사유": "퇴사사유",
    "이직 사유": "퇴사사유",
    "전배 사유": "퇴사사유",
    "수상 및 기타 경력": "수상",
    "포상": "수상",
    "수상": "수상",
    "특허": "특허",
    "교육": "교육",
}

_EDUCATION_ETC_ALIASES: dict[str, str] = {
    "교육": "교육",
    "교육 및 연수": "교육",
    "교육 수료": "교육",
    "교육 프로그램": "교육",
    "교육이수": "교육",
    "해외연수": "교육",
    "어학연수": "교육",
    "수상경력": "수상",
    "수상내역": "수상",
}

_SKILLS_ETC_ALIASES: dict[str, str] = {
    "교육": "교육",
    "교육 이수": "교육",
    "전문 교육 과정": "교육",
    "교육 및 훈련": "교육",
    "성과": "수상",
    "성과 지표": "수상",
}

# ---------------------------------------------------------------------------
# Keyword maps: substring match for free-text type variations
# Order matters — first match wins.
# ---------------------------------------------------------------------------

_CAREER_ETC_KEYWORDS: dict[str, str] = {
    "퇴사": "퇴사사유",
    "이직": "퇴사사유",
    "퇴직": "퇴사사유",
    "수상": "수상",
    "포상": "수상",
    "상훈": "수상",
    "특허": "특허",
    "교육": "교육",
    "훈련": "교육",
    "연수": "교육",
    "프로젝트": "프로젝트",
    "해외": "해외경험",
}

_EDUCATION_ETC_KEYWORDS: dict[str, str] = {
    "교육": "교육",
    "훈련": "교육",
    "연수": "교육",
    "수상": "수상",
    "상훈": "수상",
}

_SKILLS_ETC_KEYWORDS: dict[str, str] = {
    "교육": "교육",
    "훈련": "교육",
    "과정": "교육",
    "수상": "수상",
    "성과": "수상",
}


# ---------------------------------------------------------------------------
# Core canonicalization
# ---------------------------------------------------------------------------


def _canonicalize(
    item: dict,
    aliases: dict[str, str],
    keywords: dict[str, str],
) -> str:
    """Return canonical type for an _etc item.

    1st pass: exact match (aliases)
    2nd pass: keyword contains match (keywords) — handles free-text variations
    """
    raw_type = (item.get("type") or "").strip()
    if raw_type in aliases:
        return aliases[raw_type]
    for keyword, canonical in keywords.items():
        if keyword in raw_type:
            return canonical
    return "기타"


# ---------------------------------------------------------------------------
# Split functions — bucket + shape-transform via detail_normalizers
# ---------------------------------------------------------------------------


def split_career_etc(items: list[dict]) -> dict:
    """Split career_etc into {awards, patents, trainings, projects, overseas, remaining}.

    Each bucket is shape-transformed through the appropriate detail_normalizer.
    """
    raw_awards: list[dict] = []
    raw_patents: list[dict] = []
    raw_trainings: list[dict] = []
    raw_projects: list[dict] = []
    raw_overseas: list[dict] = []
    remaining: list[dict] = []

    for item in items:
        canonical = _canonicalize(item, _CAREER_ETC_ALIASES, _CAREER_ETC_KEYWORDS)
        if canonical == "수상":
            raw_awards.append(item)
        elif canonical == "특허":
            raw_patents.append(item)
        elif canonical == "교육":
            raw_trainings.append(item)
        elif canonical == "프로젝트":
            raw_projects.append(item)
        elif canonical == "해외경험":
            raw_overseas.append(item)
        elif canonical == "퇴사사유":
            pass  # Handled by backfill → Career.reason_left
        else:
            remaining.append(item)

    return {
        "awards": normalize_awards(raw_awards),
        "patents": normalize_patents(raw_patents),
        "trainings": normalize_trainings(raw_trainings),
        "projects": normalize_projects(raw_projects),
        "overseas": normalize_overseas(raw_overseas),
        "remaining": remaining,
    }


def split_education_etc(items: list[dict]) -> dict:
    """Split education_etc into {trainings, awards, remaining}."""
    raw_trainings: list[dict] = []
    raw_awards: list[dict] = []
    remaining: list[dict] = []

    for item in items:
        canonical = _canonicalize(item, _EDUCATION_ETC_ALIASES, _EDUCATION_ETC_KEYWORDS)
        if canonical == "교육":
            raw_trainings.append(item)
        elif canonical == "수상":
            raw_awards.append(item)
        else:
            remaining.append(item)

    return {
        "trainings": normalize_trainings(raw_trainings),
        "awards": normalize_awards(raw_awards),
        "remaining": remaining,
    }


def split_skills_etc(items: list[dict]) -> dict:
    """Split skills_etc into {trainings, awards, remaining}."""
    raw_trainings: list[dict] = []
    raw_awards: list[dict] = []
    remaining: list[dict] = []

    for item in items:
        canonical = _canonicalize(item, _SKILLS_ETC_ALIASES, _SKILLS_ETC_KEYWORDS)
        if canonical == "교육":
            raw_trainings.append(item)
        elif canonical == "수상":
            raw_awards.append(item)
        else:
            remaining.append(item)

    return {
        "trainings": normalize_trainings(raw_trainings),
        "awards": normalize_awards(raw_awards),
        "remaining": remaining,
    }


def build_etc_context(candidate) -> dict:
    """Build template context by splitting _etc fields and merging results.

    Used by both candidate_detail and review_detail views.
    """
    career_split = split_career_etc(candidate.career_etc or [])
    edu_split = split_education_etc(candidate.education_etc or [])
    skills_split = split_skills_etc(candidate.skills_etc or [])

    return {
        "trainings_data": (
            edu_split["trainings"]
            + skills_split["trainings"]
            + career_split["trainings"]
        ),
        "awards_data": (
            career_split["awards"] + edu_split["awards"] + skills_split["awards"]
        ),
        "patents_data": career_split["patents"],
        "projects_data": career_split["projects"],
        "overseas_experience": career_split["overseas"],
        "career_etc_remaining": career_split["remaining"],
        "education_etc_remaining": edu_split["remaining"],
        "skills_etc_remaining": skills_split["remaining"],
    }
