"""AI 초안 생성 + 자동 보정 (Gemini API)."""

import json
import logging

from django.conf import settings
from google import genai

from data_extraction.services.extraction.sanitizers import parse_llm_json

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"


def _get_gemini_client() -> genai.Client:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in settings")
    return genai.Client(api_key=api_key)


def _collect_candidate_data(candidate) -> dict:
    """Candidate 인스턴스에서 초안 생성에 필요한 모든 데이터를 수집."""
    data = {
        # 기본 정보
        "name": candidate.name,
        "name_en": candidate.name_en,
        "birth_year": candidate.birth_year,
        "gender": candidate.gender,
        "email": candidate.email,
        "phone": candidate.phone,
        "address": candidate.address,
        "current_company": candidate.current_company,
        "current_position": candidate.current_position,
        "total_experience_years": candidate.total_experience_years,
        "summary": candidate.summary,
        "self_introduction": candidate.self_introduction,
        # 연봉
        "current_salary": candidate.current_salary,
        "desired_salary": candidate.desired_salary,
        "salary_detail": candidate.salary_detail,
        # JSON 필드
        "core_competencies": candidate.core_competencies,
        "military_service": candidate.military_service,
        "family_info": candidate.family_info,
        "overseas_experience": candidate.overseas_experience,
        "awards": candidate.awards,
        "patents": candidate.patents,
        "projects": candidate.projects,
        "trainings": candidate.trainings,
        "skills": candidate.skills,
        "personal_etc": candidate.personal_etc,
        "education_etc": candidate.education_etc,
        "career_etc": candidate.career_etc,
        "skills_etc": candidate.skills_etc,
        # 관련 모델
        "careers": list(
            candidate.careers.values(
                "company",
                "company_en",
                "position",
                "department",
                "start_date",
                "end_date",
                "duration_text",
            )
        ),
        "educations": list(
            candidate.educations.values(
                "institution",
                "degree",
                "major",
                "gpa",
                "start_year",
                "end_year",
                "is_abroad",
            )
        ),
        "certifications": list(
            candidate.certifications.values(
                "name",
                "issuer",
                "acquired_date",
            )
        ),
        "language_skills": list(
            candidate.language_skills.values(
                "language",
                "test_name",
                "score",
                "level",
            )
        ),
    }
    return data


DRAFT_SYSTEM_PROMPT = """\
당신은 헤드헌팅 회사의 추천 서류 작성 전문가입니다.
후보자 데이터를 받아 고객사 제출용 추천 서류 초안을 작성합니다.

## 규칙
1. 모든 텍스트는 한국어로 작성합니다.
2. 경력 기간은 "YYYY.MM ~ YYYY.MM (N년 M개월)" 형식으로 통일합니다.
3. 회사 소개가 없는 경우 회사명으로 간략한 소개를 작성합니다.
4. 자격증 명칭은 공식 명칭으로 매칭합니다.
5. 오탈자를 교정합니다.
6. 영문명이 없으면 한국어 이름의 영문 표기를 생성합니다.

## 출력 형식
JSON으로 응답합니다. 구조:
{
  "personal_info": {
    "name": "", "name_en": "", "birth_year": null,
    "gender": "", "email": "", "phone": "", "address": ""
  },
  "summary": "전문 요약 (3-5문장)",
  "core_competencies": ["역량1", "역량2"],
  "careers": [
    {
      "company": "", "company_en": "", "company_intro": "",
      "position": "", "department": "",
      "period": "", "duration": "",
      "responsibilities": ["업무1"]
    }
  ],
  "educations": [
    {"institution": "", "degree": "", "major": "", "period": ""}
  ],
  "certifications": [
    {"name": "", "issuer": "", "date": ""}
  ],
  "language_skills": [
    {"language": "", "test": "", "score": "", "level": ""}
  ],
  "skills": ["기술1", "기술2"],
  "military": {"status": "", "branch": "", "period": ""},
  "additional": {
    "awards": [],
    "patents": [],
    "overseas": [],
    "training": [],
    "self_introduction": ""
  },
  "corrections": [
    {"field": "", "original": "", "corrected": "", "reason": ""}
  ]
}
"""


def _build_draft_prompt(candidate_data: dict) -> str:
    """Gemini에 전달할 프롬프트 구성."""
    return (
        "아래 후보자 데이터를 엑스다임 추천 서류 양식에 맞게 구조화하세요.\n"
        "자동 보정(오탈자, 서식 통일, 영문명 생성, 회사 소개 작성, "
        "자격증 명칭 매칭)을 수행하고, "
        "보정 내역을 corrections 배열에 기록하세요.\n\n"
        "후보자 데이터:\n"
        f"{json.dumps(candidate_data, ensure_ascii=False, indent=2)}"
    )


def generate_draft(draft) -> None:
    """AI 초안 생성. draft 객체에 결과를 저장한다."""
    candidate = draft.submission.candidate

    candidate_data = _collect_candidate_data(candidate)
    client = _get_gemini_client()
    prompt = _build_draft_prompt(candidate_data)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=DRAFT_SYSTEM_PROMPT,
            max_output_tokens=8000,
            temperature=0.3,
            response_mime_type="application/json",
        ),
    )

    result = parse_llm_json(response.text)
    if not isinstance(result, dict):
        raise RuntimeError("AI 초안 생성에 실패했습니다. 잘못된 응답 형식.")

    # corrections 분리 저장
    corrections = result.pop("corrections", [])

    draft.auto_draft_json = result
    draft.auto_corrections = corrections if isinstance(corrections, list) else []
    draft.status = "draft_generated"
    draft.save(
        update_fields=[
            "auto_draft_json",
            "auto_corrections",
            "status",
            "updated_at",
        ]
    )
