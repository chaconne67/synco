"""Step 2: Normalization + fraud detection — career, education, skills."""

from __future__ import annotations

import json
import logging

from candidates.services.integrity.step1_extract import _call_gemini

logger = logging.getLogger(__name__)

CAREER_SYSTEM_PROMPT = """\
당신은 이력서 경력 데이터를 정규화하는 전문가입니다.

Step 1에서 이력서의 모든 섹션, 모든 언어의 경력 데이터가 독립 추출되었습니다.
같은 회사가 여러 항목으로 나오고, 섹션마다 날짜나 표기가 다를 수 있습니다.

## 입력 구조

각 항목에는 다음 필드가 포함되어 있습니다:
- source_section: 이 데이터가 추출된 이력서 내 섹션 (예: 국문 경력란, 영문 경력란, 경력기술서)
- duration_text: 괄호 안에 기재된 기간 표기 (예: "2년 6개월", "11개월"). 날짜와의 정합성 검증에 사용됩니다.
같은 회사가 다른 source_section에서 다른 날짜로 추출되었을 수 있습니다.
다른 언어로 표기된 같은 회사도 있을 수 있습니다.

## 출력 용도

당신의 출력은 두 곳에서 사용됩니다:
- 정규화된 데이터 → 후보자 DB에 저장되어 검색·열람에 사용
- integrity_flags → 채용 담당자에게 검수 알림으로 표시

## 정규화

같은 회사의 여러 항목을 하나의 레코드로 통합하세요.
한 회사의 전체 기간과 세부 직무 기간이 함께 있으면, 전체 기간을 최종 값으로 사용하세요.

이력서의 서로 다른 섹션은 서로 다른 시점에 작성되었을 수 있습니다.
따라서 날짜가 충돌하면 가장 확정적인 정보를 선택하세요.
확정된 날짜가 "현재"보다 신뢰도가 높습니다.

경력은 최신순으로 정렬하고 order를 0부터 부여하세요.
start_date, end_date는 YYYY-MM 형식으로 통일하세요.
현재 재직 중이면 end_date는 null, is_current는 true.

## 위조 탐지

위조 탐지는 정규화의 부산물입니다.
통합이 매끄러우면 integrity_flags는 빈 배열입니다.
통합 과정에서 해소할 수 없는 모순이 발견되면 기록하세요.

거짓 경보는 채용 담당자의 시스템 신뢰를 떨어뜨립니다.
담당자가 RED를 보면 해당 후보자를 즉시 재검토하고,
YELLOW를 보면 면접 시 확인 사항으로 기록합니다.
보고할지 판단할 때 "이것을 보고 담당자가 재검토해야 하는 수준인가?"를 자문하세요.

타이핑 실수나 월 계산 방식 차이로 설명 가능한 작은 차이는
정규화만 하고 보고하지 마세요.

duration_text와 날짜 계산의 모순은 같은 항목 내 자기모순이므로
정규화로 해소할 수 없습니다 — 보고 대상입니다.

## 출력
JSON만 출력하세요.
"""

CAREER_OUTPUT_SCHEMA = """{
  "careers": [
    {
      "company": "string",
      "company_en": "string | null",
      "position": "string | null",
      "department": "string | null",
      "start_date": "string (YYYY-MM)",
      "end_date": "string | null (YYYY-MM)",
      "is_current": "boolean",
      "duties": "string | null",
      "achievements": "string | null",
      "order": "integer (최신순 0부터)"
    }
  ],
  "flags": [
    {
      "type": "string (DATE_CONFLICT)",
      "severity": "string (RED | YELLOW)",
      "field": "string",
      "detail": "string",
      "chosen": "string | null",
      "alternative": "string | null",
      "reasoning": "string"
    }
  ]
}"""

EDUCATION_SYSTEM_PROMPT = """\
당신은 이력서 학력 데이터를 정규화하는 전문가입니다.

Step 1에서 이력서의 모든 섹션, 모든 언어의 학력 데이터가 독립 추출되었습니다.
같은 학교가 여러 항목으로 나올 수 있습니다.

## 입력 구조

각 항목에는 source_section(추출된 섹션)이 포함되어 있습니다.
같은 학교가 다른 섹션이나 다른 언어에서 다른 정보로 추출되었을 수 있습니다.

## 출력 용도

당신의 출력은 두 곳에서 사용됩니다:
- 정규화된 데이터 → 후보자 DB에 저장
- integrity_flags → 채용 담당자에게 검수 알림으로 표시

## 정규화

같은 학교의 여러 항목을 하나의 레코드로 통합하세요.
날짜가 충돌하면 가장 확정적인 정보를 선택하세요.
이력서의 서로 다른 섹션은 서로 다른 시점에 작성되었을 수 있으므로,
확정된 정보가 "현재"보다 신뢰도가 높습니다.

## 위조 탐지

위조 탐지는 정규화의 부산물입니다.
통합이 매끄러우면 빈 배열입니다.

본인이 솔직하게 밝힌 학력 사항은 위조가 아닙니다.
같은 분야의 다른 학교가 있으면 편입 가능성이 있습니다.
위 어디에도 해당하지 않으면서 정규 학위를 수업연한보다
현저히 짧은 기간에 취득한 것은 보고 대상입니다.

거짓 경보는 담당자의 신뢰를 떨어뜨리므로 확실한 것만 보고하세요.
보고할지 판단할 때 "이것을 보고 담당자가 재검토해야 하는 수준인가?"를 자문하세요.

## 출력
JSON만 출력하세요.
"""

EDUCATION_OUTPUT_SCHEMA = """{
  "educations": [
    {
      "institution": "string",
      "degree": "string | null",
      "major": "string | null",
      "start_year": "integer | null",
      "end_year": "integer | null",
      "is_abroad": "boolean"
    }
  ],
  "flags": [
    {
      "type": "string (SHORT_DEGREE)",
      "severity": "string (RED | YELLOW)",
      "field": "string",
      "detail": "string",
      "chosen": "string | null",
      "alternative": "string | null",
      "reasoning": "string"
    }
  ]
}"""


def normalize_career_group(
    entries: list[dict],
    canonical_name: str,
    *,
    feedback: str | None = None,
) -> dict | None:
    """Normalize all career entries into deduplicated, ordered careers + flags."""
    entries_json = json.dumps(entries, ensure_ascii=False, indent=2)

    feedback_block = ""
    if feedback:
        feedback_block = f"\n## 피드백\n{feedback}\n"

    prompt = (
        f"아래 {len(entries)}개 경력 항목을 정규화하세요. "
        f"같은 회사의 중복 항목은 하나로 통합하세요.{feedback_block}\n\n"
        f"## 출력 스키마\n```\n{CAREER_OUTPUT_SCHEMA}\n```\n\n"
        f"## 입력 항목\n```json\n{entries_json}\n```\n\n"
        "JSON만 출력하세요."
    )

    result = _call_gemini(CAREER_SYSTEM_PROMPT, prompt, max_tokens=4000)
    if not result or "careers" not in result:
        # fallback: single career format
        if result and "career" in result:
            result["careers"] = [result.pop("career")]
            return result
        logger.warning("Step 2 career normalization failed")
        return None

    return result


def normalize_education_group(
    entries: list[dict],
    *,
    feedback: str | None = None,
) -> dict | None:
    """Normalize education entries + detect SHORT_DEGREE."""
    if not entries:
        return {"educations": [], "flags": []}

    entries_json = json.dumps(entries, ensure_ascii=False, indent=2)

    feedback_block = ""
    if feedback:
        feedback_block = f"\n## 피드백\n{feedback}\n"

    prompt = (
        f"아래 {len(entries)}개 학력 항목을 정규화하고 위조 의심을 탐지하세요."
        f"{feedback_block}\n\n"
        f"## 출력 스키마\n```\n{EDUCATION_OUTPUT_SCHEMA}\n```\n\n"
        f"## 입력 항목\n```json\n{entries_json}\n```\n\n"
        "JSON만 출력하세요."
    )

    result = _call_gemini(EDUCATION_SYSTEM_PROMPT, prompt, max_tokens=2000)
    if not result or "educations" not in result:
        logger.warning("Step 2 education normalization failed")
        return None

    return result


def normalize_skills(raw_data: dict) -> dict:
    """Code-based skills normalization. No LLM."""
    return {
        "certifications": raw_data.get("certifications", []),
        "language_skills": raw_data.get("language_skills", []),
    }
