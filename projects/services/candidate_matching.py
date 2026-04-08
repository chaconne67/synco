"""후보자 적합도 매칭: requirements 기반 스코어링."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 5차원 가중치
WEIGHTS = {
    "experience": 0.25,
    "keywords": 0.25,
    "certifications": 0.20,
    "education": 0.15,
    "demographics": 0.15,
}


def match_candidates(
    requirements: dict,
    organization=None,
    limit: int = 100,
) -> list[dict]:
    """requirements 기반으로 후보자를 검색하고 적합도 점수를 산출.

    Args:
        requirements: AI가 추출한 JD 요구조건
        organization: Organization 필터 (전달 시 owned_by 격리 적용)
        limit: 최대 결과 수

    Returns:
        [{"candidate": Candidate, "score": float, "level": str, "details": dict}, ...]
        level: "높음" (70%+), "보통" (40-70%), "낮음" (40%-)
    """
    from candidates.services.search import build_search_queryset, normalize_filter_spec

    from projects.services.jd_analysis import requirements_to_search_filters

    # 1. requirements → 검색 필터 변환
    filters = requirements_to_search_filters(requirements)
    if not filters:
        return []

    # 2. 기본 검색으로 후보자 풀 확보 (느슨한 필터)
    # 경력/성별/연령만으로 1차 필터링
    loose_filters = normalize_filter_spec(
        {
            "min_experience_years": filters.get("min_experience_years"),
            "max_experience_years": filters.get("max_experience_years"),
            "gender": filters.get("gender"),
            "birth_year_from": filters.get("birth_year_from"),
            "birth_year_to": filters.get("birth_year_to"),
        }
    )
    qs = build_search_queryset(loose_filters)

    # 조직 격리: 슬라이스 전에 적용
    if organization:
        qs = qs.filter(owned_by=organization)

    qs = qs[: limit * 3]

    # 3. 개별 스코어링
    results = []
    for candidate in qs:
        score, details = _score_candidate(candidate, requirements)
        level = _score_to_level(score)
        results.append(
            {
                "candidate": candidate,
                "score": round(score, 2),
                "level": level,
                "details": details,
            }
        )

    # 4. 점수순 정렬 + 상위 limit개
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def _score_candidate(candidate, requirements: dict) -> tuple[float, dict]:
    """후보자의 적합도 점수를 산출.

    Returns:
        (total_score: 0.0~1.0, details: {dimension: {score, reason}})
    """
    details = {}

    # 1. 경력 범위 (25%)
    exp_score, exp_reason = _score_experience(candidate, requirements)
    details["experience"] = {"score": exp_score, "reason": exp_reason}

    # 2. 키워드 매칭 (25%)
    kw_score, kw_reason = _score_keywords(candidate, requirements)
    details["keywords"] = {"score": kw_score, "reason": kw_reason}

    # 3. 자격증 (20%)
    cert_score, cert_reason = _score_certifications(candidate, requirements)
    details["certifications"] = {"score": cert_score, "reason": cert_reason}

    # 4. 학력 (15%)
    edu_score, edu_reason = _score_education(candidate, requirements)
    details["education"] = {"score": edu_score, "reason": edu_reason}

    # 5. 연령·성별 (15%)
    demo_score, demo_reason = _score_demographics(candidate, requirements)
    details["demographics"] = {"score": demo_score, "reason": demo_reason}

    total = (
        exp_score * WEIGHTS["experience"]
        + kw_score * WEIGHTS["keywords"]
        + cert_score * WEIGHTS["certifications"]
        + edu_score * WEIGHTS["education"]
        + demo_score * WEIGHTS["demographics"]
    )

    return total, details


def _score_experience(candidate, requirements: dict) -> tuple[float, str]:
    """경력 범위 일치 점수."""
    exp = candidate.total_experience_years
    if exp is None:
        return 0.5, "경력 정보 없음 (판정 불가)"

    min_exp = requirements.get("min_experience_years")
    max_exp = requirements.get("max_experience_years")

    if min_exp is None and max_exp is None:
        return 1.0, "경력 조건 없음"

    # 범위 내 = 만점
    in_range = True
    if min_exp is not None and exp < min_exp:
        in_range = False
    if max_exp is not None and exp > max_exp:
        in_range = False

    if in_range:
        return 1.0, f"경력 {exp}년 (범위 내)"

    # 범위에서 ±2년 = 감점
    gap = 0
    if min_exp is not None and exp < min_exp:
        gap = min_exp - exp
    elif max_exp is not None and exp > max_exp:
        gap = exp - max_exp

    if gap <= 2:
        return 0.5, f"경력 {exp}년 (범위에서 {gap}년 차이)"

    return 0.0, f"경력 {exp}년 (범위 초과)"


def _score_keywords(candidate, requirements: dict) -> tuple[float, str]:
    """키워드 매칭 점수: JD 키워드와 후보자 경력/스킬 텍스트 겹침 비율."""
    jd_keywords = requirements.get("keywords") or []
    if not jd_keywords:
        return 1.0, "키워드 조건 없음"

    # 후보자 텍스트 풀 구성
    candidate_text = _build_candidate_text(candidate).lower()

    matched = []
    for kw in jd_keywords:
        if kw.lower() in candidate_text:
            matched.append(kw)

    ratio = len(matched) / len(jd_keywords) if jd_keywords else 0
    matched_str = ", ".join(matched[:5]) if matched else "없음"
    return ratio, f"키워드 {len(matched)}/{len(jd_keywords)} 매칭 ({matched_str})"


def _build_candidate_text(candidate) -> str:
    """후보자의 검색 가능한 텍스트를 결합."""
    parts = [
        candidate.current_company or "",
        candidate.current_position or "",
        candidate.summary or "",
    ]

    # 경력
    for career in candidate.careers.all():
        parts.extend(
            [
                career.company or "",
                career.position or "",
                career.duties or "",
                career.achievements or "",
            ]
        )

    # 스킬
    skills = candidate.skills or []
    if isinstance(skills, list):
        for s in skills:
            if isinstance(s, str):
                parts.append(s)
            elif isinstance(s, dict):
                parts.append(s.get("name", ""))

    return " ".join(parts)


def _score_certifications(candidate, requirements: dict) -> tuple[float, str]:
    """자격증 보유 점수."""
    required = requirements.get("required_certifications") or []
    preferred = requirements.get("preferred_certifications") or []

    if not required and not preferred:
        return 1.0, "자격증 조건 없음"

    candidate_certs = [c.name.lower() for c in candidate.certifications.all()]

    # required 충족 체크
    required_met = 0
    for cert in required:
        if any(cert.lower() in cc for cc in candidate_certs):
            required_met += 1

    # preferred 보너스
    preferred_met = 0
    for cert in preferred:
        if any(cert.lower() in cc for cc in candidate_certs):
            preferred_met += 1

    if required:
        base_score = required_met / len(required)
    else:
        base_score = 1.0

    if preferred:
        bonus = (preferred_met / len(preferred)) * 0.3  # 최대 30% 보너스
    else:
        bonus = 0

    score = min(base_score + bonus, 1.0)
    return (
        score,
        f"필수 {required_met}/{len(required)}, 우대 {preferred_met}/{len(preferred)}",
    )


def _score_education(candidate, requirements: dict) -> tuple[float, str]:
    """학력 조건 점수: 전공 일치 + 대학 그룹 매칭."""
    from candidates.services.search import UNIVERSITY_GROUPS

    edu_fields = requirements.get("education_fields") or []
    edu_pref = requirements.get("education_preference") or ""

    if not edu_fields and not edu_pref:
        return 1.0, "학력 조건 없음"

    candidate_edus = list(candidate.educations.all())
    if not candidate_edus:
        return 0.5, "학력 정보 없음 (판정 불가)"

    score = 0.0
    reasons = []

    # 전공 일치
    if edu_fields:
        candidate_majors = [e.major.lower() for e in candidate_edus if e.major]
        field_matched = 0
        for field in edu_fields:
            if any(field.lower() in m for m in candidate_majors):
                field_matched += 1
        if field_matched > 0:
            score += 0.7
            reasons.append(f"전공 {field_matched}/{len(edu_fields)} 일치")
        else:
            reasons.append("전공 불일치")

    # 대학 그룹 매칭 (UNIVERSITY_GROUPS 재활용)
    candidate_schools = [e.institution for e in candidate_edus if e.institution]
    for group_name, schools in UNIVERSITY_GROUPS.items():
        matched = False
        for school in schools:
            if any(school in cs for cs in candidate_schools):
                score += 0.3
                reasons.append(f"{group_name} 소속")
                matched = True
                break
        if matched:
            break

    return min(score, 1.0), " / ".join(reasons) if reasons else "판정 불가"


def _score_demographics(candidate, requirements: dict) -> tuple[float, str]:
    """연령·성별 점수."""
    score = 1.0
    reasons = []

    # 성별
    req_gender = requirements.get("gender")
    if req_gender:
        if candidate.gender and candidate.gender.lower() != req_gender.lower():
            score = 0.0
            reasons.append(f"성별 불일치 (요구: {req_gender})")
        elif not candidate.gender:
            reasons.append("성별 정보 없음")
        else:
            reasons.append("성별 일치")

    # 연령
    birth_from = requirements.get("birth_year_from")
    birth_to = requirements.get("birth_year_to")
    if birth_from or birth_to:
        if candidate.birth_year:
            in_range = True
            if birth_from and candidate.birth_year < birth_from:
                in_range = False
            if birth_to and candidate.birth_year > birth_to:
                in_range = False
            if not in_range:
                score = 0.0
                reasons.append(f"연령 범위 밖 (출생: {candidate.birth_year})")
            else:
                reasons.append("연령 범위 내")
        else:
            reasons.append("출생연도 정보 없음")

    return score, " / ".join(reasons) if reasons else "인구통계 조건 없음"


def _score_to_level(score: float) -> str:
    """점수를 등급으로 변환."""
    if score >= 0.7:
        return "높음"
    elif score >= 0.4:
        return "보통"
    return "낮음"


def generate_gap_report(candidate, requirements: dict) -> dict:
    """후보자별 JD 요구사항 충족/미충족 항목 분석 리포트.

    Returns:
        {
            "candidate_name": str,
            "overall_score": float,
            "overall_level": str,
            "met": [{"item": str, "evidence": str}],
            "unmet": [{"item": str, "detail": str}],
            "unknown": [{"item": str, "reason": str}],
        }
    """
    score, details = _score_candidate(candidate, requirements)

    met = []
    unmet = []
    unknown = []

    for dim_name, dim_data in details.items():
        dim_score = dim_data["score"]
        dim_reason = dim_data["reason"]

        if "판정 불가" in dim_reason or "정보 없음" in dim_reason:
            unknown.append({"item": dim_name, "reason": dim_reason})
        elif dim_score >= 0.7:
            met.append({"item": dim_name, "evidence": dim_reason})
        else:
            unmet.append({"item": dim_name, "detail": dim_reason})

    return {
        "candidate_name": candidate.name,
        "overall_score": round(score, 2),
        "overall_level": _score_to_level(score),
        "met": met,
        "unmet": unmet,
        "unknown": unknown,
    }
