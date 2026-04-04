"""Consolidated extraction prompts for resume parsing pipelines.

Sources:
- candidates/services/llm_extraction.py (EXTRACTION_SYSTEM_PROMPT, schema, build_extraction_prompt)
- candidates/services/integrity/step1_extract.py (STEP1_SYSTEM_PROMPT, STEP1_SCHEMA, build_step1_prompt)
- candidates/services/integrity/step2_normalize.py (career/education normalization prompts)
"""

# ---------------------------------------------------------------------------
# Legacy single-call extraction (Gemini / Sonnet)
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = (
    "당신은 한국어 이력서 파싱 전문가입니다. "
    "이력서 텍스트를 분석하여 구조화된 JSON으로 변환합니다.\n\n"
    "핵심 원칙:\n"
    "- duties와 achievements는 이력서 본문에 명시적으로 기재된 내용만 추출하세요. "
    "기재되지 않았으면 null로 반환하세요.\n"
    "- inferred_capabilities는 직책·부서·경력 수준을 바탕으로 "
    "이 사람이 수행할 수 있을 것으로 예상되는 역량을 추정하세요. "
    "duties가 이미 상세히 기재된 경우에는 null로 반환하세요.\n\n"
    "규칙:\n"
    "1. 데이터가 없는 필드는 빈 문자열, 빈 배열, 또는 null로 반환하세요.\n"
    "2. 2자리 연도는 4자리로 변환하세요 (예: '85 → 1985, '03 → 2003).\n"
    "3. 경력(careers)은 최신순으로 정렬하고 order 값을 0부터 부여하세요.\n"
    "4. 현재 재직 중인 직장은 is_current=true로 표시하세요.\n"
    "5. 각 필드별 신뢰도 점수(field_confidences)를 0.0~1.0 사이로 반환하세요.\n"
    "6. 이력서 본문에 작성일/수정일/제출일이 명시된 경우에만 "
    "resume_reference_date에 YYYY-MM 또는 YYYY-MM-DD 형식으로 반환하세요.\n"
    "7. resume_reference_date는 문서 안의 명시적 근거가 있을 때만 채우고, "
    "경력 기간만 보고 추정하지 마세요.\n"
    "8. 경력 기간이 '2004/06 ~', '(1년 7개월)'처럼 불완전하게 적혀 있으면, "
    "duration_text, end_date_inferred, date_evidence, date_confidence에 근거와 추정값을 함께 반환하세요.\n"
    "9. end_date_inferred는 start_date와 duration_text 등 문서 안 근거로 합리적으로 계산 가능한 경우에만 채우세요.\n"
    "10. JSON만 출력하세요. 설명이나 마크다운은 포함하지 마세요.\n\n"
    "### skills vs core_competencies 구분\n\n"
    "skills에는 이력서 전체에서 언급된 특정 기술·도구·시스템의 고유명사를 추출하세요.\n"
    "이 데이터는 후보자 검색 시 기술 키워드 매칭에 사용됩니다.\n"
    "구체적 명칭이 대상이고, 일반적 역량 서술(\"의사소통 능력\", \"리더십\")은 core_competencies에 넣으세요.\n\n"
    "구분 원칙: 그 단어로 검색했을 때 해당 기술을 가진 사람만 나와야 하면 skills, "
    "다수의 사람에게 해당하는 일반적 역량이면 core_competencies.\n\n"
    "### skills 표기 정규화\n\n"
    "- 영문 공식 명칭을 우선 사용하세요: \"파이썬\" → \"Python\", \"오라클\" → \"Oracle\"\n"
    "- 공식 표기를 따르세요: \"MSSQL\" → \"MS SQL Server\", \"C++\" (O), \"씨플플\" (X)\n"
    "- 약어가 널리 쓰이면 약어를 사용하세요: \"SAP\", \"PMP\", \"ISO 9001\"\n"
    "- 한글만 존재하는 고유명사는 한글 그대로\n\n"
    "### etc[] 필드 사용 원칙\n\n"
    "이력서의 모든 정보는 4개 카테고리 중 하나에 반드시 속합니다:\n"
    "- 인적사항: 이 사람이 누구인지에 관한 정보 → personal_etc\n"
    "- 학력: 무엇을 배웠는지에 관한 정보 → education_etc\n"
    "- 경력: 어떤 일을 했는지에 관한 정보 → career_etc\n"
    "- 능력: 무엇을 할 수 있는지에 관한 정보 → skills_etc\n\n"
    "각 카테고리에서 핵심 필드에 맞지 않지만 해당 카테고리에 속하는 정보는 etc[]에 넣으세요.\n"
    "원본에 있는 정보는 반드시 어딘가에 포함되어야 합니다. 누락보다 중복이 낫습니다.\n"
    "etc[] 항목에는 반드시 type을 넣어 무엇인지 식별할 수 있게 하세요.\n"
    "etc[] 항목의 type과 description은 한국어로 작성하세요. 원문이 영어인 경우 한국어로 번역하세요."
)

EXTRACTION_JSON_SCHEMA = """{
  "name": "string (이름)",
  "name_en": "string | null (영문 이름)",
  "birth_year": "integer | null (출생연도 4자리)",
  "gender": "string | null (male/female)",
  "email": "string | null",
  "phone": "string | null",
  "address": "string | null",
  "current_company": "string | null (현재 재직 회사명)",
  "current_position": "string | null (현재 직위)",
  "total_experience_years": "integer | null (총 경력 연수)",
  "resume_reference_date": "string | null (이력서 작성/수정/제출 기준일, YYYY-MM 또는 YYYY-MM-DD)",
  "resume_reference_date_source": "string | null (document_text when explicitly stated in the resume)",
  "resume_reference_date_evidence": "string | null (기준일을 판단한 문서 내 근거 문구)",
  "core_competencies": ["string (이력서에 명시된 핵심 역량 키워드만)"],
  "summary": "string | null (이력서에 기재된 내용 기반 경력 요약 1~2문장)",
  "educations": [
    {
      "institution": "string (학교명)",
      "degree": "string | null (학위: 학사/석사/박사)",
      "major": "string | null (전공)",
      "gpa": "number | null",
      "start_year": "integer | null",
      "end_year": "integer | null",
      "is_abroad": "boolean (해외 학력 여부)"
    }
  ],
  "careers": [
    {
      "company": "string (회사명)",
      "company_en": "string | null (영문 회사명)",
      "position": "string | null (직위)",
      "department": "string | null (부서)",
      "start_date": "string | null (YYYY-MM 형식)",
      "end_date": "string | null (YYYY-MM 형식, 현재 재직 시 null)",
      "duration_text": "string | null (원문에 적힌 기간 표현 예: 1년 7개월, 18개월)",
      "end_date_inferred": "string | null (문서 근거로 추정한 종료월, YYYY-MM 형식)",
      "date_evidence": "string | null (날짜/기간을 판단한 원문 근거)",
      "date_confidence": "float | null (0.0~1.0, 날짜 추정 신뢰도)",
      "is_current": "boolean (현재 재직 여부)",
      "duties": "string | null (이력서에 명시된 담당 업무만. 기재되지 않았으면 null)",
      "inferred_capabilities": "string | null (직책·부서·경력 수준으로 추정한 수행 가능 역량. duties가 상세히 기재된 경우 null)",
      "achievements": "string | null (이력서에 명시된 주요 성과만. 기재되지 않았으면 null)",
      "order": "integer (최신순 0부터)"
    }
  ],
  "certifications": [
    {
      "name": "string (자격증명)",
      "issuer": "string | null (발급기관)",
      "acquired_date": "string | null (YYYY-MM 형식)"
    }
  ],
  "language_skills": [
    {
      "language": "string (언어명)",
      "test_name": "string | null (시험명: TOEIC, JLPT 등)",
      "score": "string | null (점수)",
      "level": "string | null (등급)"
    }
  ],
  "skills": ["string (기술·도구·시스템·방법론 등 고유명사 키워드, 영문 공식명 우선)"],
  "personal_etc": [{"type": "string", "description": "string"}],
  "education_etc": [{"type": "string", "title": "string", "institution": "string", "date": "string", "description": "string"}],
  "career_etc": [{"type": "string", "name": "string", "company": "string", "role": "string", "start_date": "string", "end_date": "string", "technologies": ["string"], "description": "string"}],
  "skills_etc": [{"type": "string", "title": "string", "description": "string", "date": "string"}],
  "field_confidences": {
    "name": "float 0.0-1.0",
    "birth_year": "float 0.0-1.0",
    "careers": "float 0.0-1.0",
    "educations": "float 0.0-1.0",
    "certifications": "float 0.0-1.0",
    "overall": "float 0.0-1.0"
  }
}"""


def build_extraction_prompt(
    resume_text: str,
    file_reference_date: str | None = None,
) -> str:
    """Build prompt containing the JSON schema and the resume text."""
    metadata_block = ""
    if file_reference_date:
        metadata_block = (
            "## 파일 메타데이터\n"
            f"- Drive modifiedTime: {file_reference_date}\n"
            "- 이 값은 애플리케이션 참고용입니다. 문서 본문에 작성/수정/제출일이 "
            "명시된 경우에만 resume_reference_date에 반영하세요.\n\n"
        )
    return (
        "아래 이력서 텍스트를 분석하여 다음 JSON 스키마에 맞게 구조화하세요.\n\n"
        f"## 출력 JSON 스키마\n```\n{EXTRACTION_JSON_SCHEMA}\n```\n"
        f"{metadata_block}"
        f"\n## 이력서 텍스트\n```\n{resume_text}\n```\n\n"
        "위 스키마에 맞는 JSON만 출력하세요. 다른 텍스트는 포함하지 마세요."
    )


# ---------------------------------------------------------------------------
# Integrity pipeline — Step 1: Faithful extraction
# ---------------------------------------------------------------------------

STEP1_SYSTEM_PROMPT = """\
당신은 이력서에서 모든 데이터를 충실하게 추출하는 전문가입니다.

당신의 출력은 정규화 시스템의 입력이 됩니다. 정규화 시스템은 여러 섹션의
데이터를 비교하여 정보 간 불일치를 탐지합니다. 따라서 원문의 데이터가 하나라도
누락되면 불일치 탐지가 불가능해집니다.

## 입력 특성

입력 텍스트는 .doc/.docx 이력서 파일에서 추출된 것입니다.
원본의 표, 텍스트 상자, 본문이 평문으로 변환되어 있으므로
레이아웃 구분이 명확하지 않을 수 있습니다.
섹션의 경계는 제목, 언어 전환, 서식 변화 등으로 추론해야 합니다.

## 원칙

### 모든 섹션, 모든 언어에서 추출

이력서는 구조화된 테이블, 서술형 문단, 다국어 버전 등 여러 형태의 섹션으로
구성될 수 있습니다. 어떤 형태든, 어떤 언어든, 본인의 경력이나 학력에 대한
구체적 기관명이 포함된 언급이 있으면 추출하세요.

자기소개서, 지원동기 등 서술형 섹션에서도 구체적인 기관명이 언급되면 추출하세요.

### 섹션별 독립 추출

같은 회사가 여러 섹션에 나오면 각각 별도 항목으로 만드세요.
각 항목에 source_section을 표시하여 출처를 구분하세요.

이렇게 하는 이유: 정규화 시스템이 섹션 간 날짜를 비교해야 하기 때문입니다.
한 섹션에서 1999년이고 다른 섹션에서 1992년이면, 둘 다 있어야 비교가 가능합니다.
하나만 가져오면 불일치를 발견할 수 없습니다.

### 원문 보존

날짜, 기간 표기, 기관명을 원문 그대로 가져오세요. 정규화는 다음 단계의 역할입니다.
유일한 예외: 2자리 연도는 4자리로 변환합니다 ('85 → 1985).
"현재", "Present" 등은 문자열 그대로 유지하세요.

### 부가 정보 보존

경력 항목에 괄호로 기간이 표기되어 있으면 duration_text에 가져오세요.
이 정보는 정규화 시스템이 날짜와 기간의 정합성을 검증하는 데 사용됩니다.
시작~종료일과 기재된 기간이 모순되면 위조 의심 신호이기 때문입니다.

### 누락 비용 > 노이즈 비용

데이터가 누락되면 복구가 불가능하지만, 노이즈는 정규화 단계에서 필터링됩니다.
확신이 없더라도 추출하세요. 빠뜨리는 것보다 노이즈가 낫습니다.

### skills vs core_competencies 구분

skills에는 이력서 전체에서 언급된 특정 기술·도구·시스템의 고유명사를 추출하세요.
이 데이터는 후보자 검색 시 기술 키워드 매칭에 사용됩니다.
구체적 명칭이 대상이고, 일반적 역량 서술("의사소통 능력", "리더십")은 core_competencies에 넣으세요.

구분 원칙: 그 단어로 검색했을 때 해당 기술을 가진 사람만 나와야 하면 skills, 다수의 사람에게 해당하는 일반적 역량이면 core_competencies.

### skills 표기 정규화

- 영문 공식 명칭을 우선 사용하세요: "파이썬" → "Python", "오라클" → "Oracle"
- 공식 표기를 따르세요: "MSSQL" → "MS SQL Server", "C++" (O), "씨플플" (X)
- 약어가 널리 쓰이면 약어를 사용하세요: "SAP", "PMP", "ISO 9001"
- 한글만 존재하는 고유명사는 한글 그대로

### etc[] 필드 사용 원칙

이력서의 모든 정보는 4개 카테고리 중 하나에 반드시 속합니다:
- 인적사항: 이 사람이 누구인지에 관한 정보 → personal_etc
- 학력: 무엇을 배웠는지에 관한 정보 → education_etc
- 경력: 어떤 일을 했는지에 관한 정보 → career_etc
- 능력: 무엇을 할 수 있는지에 관한 정보 → skills_etc

각 카테고리에서 핵심 필드에 맞지 않지만 해당 카테고리에 속하는 정보는 etc[]에 넣으세요.
원본에 있는 정보는 반드시 어딘가에 포함되어야 합니다. 누락보다 중복이 낫습니다.
etc[] 항목에는 반드시 type을 넣어 무엇인지 식별할 수 있게 하세요.
etc[] 항목의 type과 description은 한국어로 작성하세요. 원문이 영어인 경우 한국어로 번역하세요.

## 추출 규칙
1. 이력서에 나오는 순서대로 가져오세요.
2. 이름은 한국어를 우선하되, 영문명도 별도로 가져오세요.
3. JSON만 출력하세요.
"""

STEP1_SCHEMA = """{
  "name": "string",
  "name_en": "string | null",
  "birth_year": "integer | null",
  "gender": "string | null",
  "email": "string | null",
  "phone": "string | null",
  "address": "string | null",
  "current_company": "string | null (현재 재직 회사)",
  "current_position": "string | null (현재 직위)",
  "total_experience_years": "integer | null",
  "total_experience_text": "string | null (원문 그대로)",
  "resume_reference_date": "string | null",
  "core_competencies": ["string (핵심 역량 키워드)"],
  "summary": "string | null (경력 요약 1~2문장)",
  "careers": [
    {
      "company": "string (원문 그대로)",
      "position": "string | null",
      "department": "string | null",
      "start_date": "string | null (원문 그대로)",
      "end_date": "string | null (원문 그대로)",
      "duration_text": "string | null (괄호 안 기간 표기 원문 그대로)",
      "is_current": "boolean",
      "duties": "string | null",
      "source_section": "string (출처 섹션)"
    }
  ],
  "educations": [
    {
      "institution": "string (원문 그대로)",
      "degree": "string | null",
      "major": "string | null",
      "start_year": "integer | null",
      "end_year": "integer | null",
      "is_abroad": "boolean",
      "status": "string | null (졸업/중퇴/수료 등 원문 그대로)",
      "source_section": "string (출처 섹션)"
    }
  ],
  "certifications": [
    {"name": "string", "issuer": "string | null", "acquired_date": "string | null"}
  ],
  "language_skills": [
    {"language": "string", "test_name": "string | null", "score": "string | null"}
  ],
  "skills": ["string (기술·도구·시스템·방법론 등 고유명사 키워드, 영문 공식명 우선)"],
  "personal_etc": [{"type": "string", "description": "string"}],
  "education_etc": [{"type": "string", "title": "string", "institution": "string", "date": "string", "description": "string"}],
  "career_etc": [{"type": "string", "name": "string", "company": "string", "role": "string", "start_date": "string", "end_date": "string", "technologies": ["string"], "description": "string"}],
  "skills_etc": [{"type": "string", "title": "string", "description": "string", "date": "string"}]
}"""


def build_step1_prompt(resume_text: str, feedback: str | None = None) -> str:
    """Build Step 1 extraction prompt."""
    feedback_block = ""
    if feedback:
        feedback_block = (
            f"\n## 이전 추출에 대한 피드백\n{feedback}\n"
            "위 피드백을 반영하여 다시 추출하세요.\n"
        )
    return (
        f"이력서의 모든 데이터를 추출하세요.{feedback_block}\n\n"
        f"## 스키마\n```\n{STEP1_SCHEMA}\n```\n\n"
        f"## 이력서\n```\n{resume_text}\n```\n\n"
        "JSON만 출력하세요."
    )


# ---------------------------------------------------------------------------
# Integrity pipeline — Step 2: Career normalization
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Integrity pipeline — Step 2: Education normalization
# ---------------------------------------------------------------------------

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
