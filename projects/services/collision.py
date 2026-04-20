"""Collision detection for project registration."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from projects.models import Project, ProjectStatus

# Closed statuses -- projects with these statuses are excluded from collision checks
CLOSED_STATUSES = {
    ProjectStatus.CLOSED,
}


def compute_title_similarity(title_a: str, title_b: str) -> float:
    """
    Compute similarity score between two project titles.

    Strategy:
    1. Extract keywords by splitting Korean compound words at common suffixes
    2. Use SequenceMatcher for overall similarity
    3. Boost score when core keywords match

    Returns float 0.0 ~ 1.0.
    """
    if not title_a or not title_b:
        return 0.0

    a_norm = _normalize(title_a)
    b_norm = _normalize(title_b)

    # Base similarity via SequenceMatcher
    base_score = SequenceMatcher(None, a_norm, b_norm).ratio()

    # Keyword extraction and matching for boost
    kw_a = _extract_keywords(a_norm)
    kw_b = _extract_keywords(b_norm)

    if kw_a and kw_b:
        common = kw_a & kw_b
        total = kw_a | kw_b
        keyword_score = len(common) / len(total) if total else 0.0
        # Weighted combination: 60% base, 40% keyword
        return min(1.0, 0.6 * base_score + 0.4 * keyword_score)

    return base_score


def _normalize(title: str) -> str:
    """Normalize title: lowercase, strip whitespace, remove common noise."""
    title = title.strip().lower()
    # Remove common parenthetical suffixes like (정규직), (계약직)
    title = re.sub(r"\s*\(.*?\)\s*", "", title)
    return title


# Common Korean role/position suffixes for splitting compound words
_ROLE_SUFFIXES = [
    "팀장",
    "파트장",
    "실장",
    "센터장",
    "본부장",
    "부장",
    "차장",
    "과장",
    "대리",
    "사원",
    "매니저",
    "리더",
    "담당",
    "책임",
    "수석",
    "선임",
    "이사",
    "상무",
    "전무",
    "부사장",
    "사장",
]

# Common department keywords
_DEPT_KEYWORDS = [
    "기획",
    "영업",
    "마케팅",
    "인사",
    "재무",
    "회계",
    "총무",
    "법무",
    "개발",
    "연구",
    "생산",
    "품질",
    "물류",
    "구매",
    "경영",
    "전략",
    "디자인",
    "IT",
    "보안",
    "감사",
]


def _extract_keywords(title: str) -> set[str]:
    """Extract meaningful keywords from a normalized title."""
    keywords = set()

    # Check for role suffixes
    for suffix in _ROLE_SUFFIXES:
        if suffix in title:
            keywords.add(suffix)
            # Also extract the prefix before the suffix as a keyword
            idx = title.find(suffix)
            prefix = title[:idx].strip()
            if prefix:
                keywords.add(prefix)

    # Check for department keywords
    for dept in _DEPT_KEYWORDS:
        if dept in title:
            keywords.add(dept)

    # If no keywords found, use the whole title as one keyword
    if not keywords:
        keywords.add(title)

    return keywords


def detect_collisions(
    client_id,
    title: str,
    exclude_project_id=None,
) -> list[dict]:
    """
    Detect similar projects for a given client and title.

    Returns list of dicts sorted by score descending, max 5 items:
    [
        {
            "project": Project,
            "score": float,
            "conflict_type": "높은중복" | "참고정보",
            "consultant_name": str,
            "status_display": str,
        },
        ...
    ]
    """
    # Fetch active projects for this client
    candidates = (
        Project.objects.filter(
            client_id=client_id,
        )
        .exclude(
            status__in=CLOSED_STATUSES,
        )
        .select_related("created_by")
    )

    if exclude_project_id:
        candidates = candidates.exclude(pk=exclude_project_id)

    results = []
    for proj in candidates:
        score = compute_title_similarity(title, proj.title)
        if score > 0.0:
            conflict_type = "높은중복" if score >= 0.7 else "참고정보"
            consultant_name = ""
            if proj.created_by:
                consultant_name = (
                    proj.created_by.get_full_name() or proj.created_by.username
                )
            results.append(
                {
                    "project": proj,
                    "score": round(score, 2),
                    "conflict_type": conflict_type,
                    "consultant_name": consultant_name,
                    "status_display": proj.get_status_display(),
                }
            )

    # Sort by score descending, take top 5
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:5]
