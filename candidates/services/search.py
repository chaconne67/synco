"""Search engine: natural language → LLM-generated SQL."""

from __future__ import annotations

import logging
import re

from django.db import connection

from common.llm import call_llm

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────
# DB schema for LLM context
# ────────────────────────────────────────────

DB_SCHEMA = """
-- 후보자 기본 정보
CREATE TABLE candidates (
    id UUID PRIMARY KEY,
    name VARCHAR,              -- 이름
    name_en VARCHAR,           -- 영문 이름
    birth_year SMALLINT,       -- 출생연도 (예: 1985)
    gender VARCHAR,            -- 성별 (남/여)
    email VARCHAR,
    phone VARCHAR,
    address VARCHAR,           -- 주소
    total_experience_years SMALLINT,  -- 총 경력 연수
    current_company VARCHAR,   -- 현재 회사
    current_position VARCHAR,  -- 현재 직급/직책
    current_salary INTEGER,    -- 현재 연봉 (만원)
    desired_salary INTEGER,    -- 희망 연봉 (만원)
    summary TEXT,              -- 후보자 요약
    status VARCHAR,            -- 상태
    primary_category_id UUID REFERENCES categories(id)
);

-- 경력 사항 (1:N)
CREATE TABLE careers (
    id UUID PRIMARY KEY,
    candidate_id UUID REFERENCES candidates(id),
    company VARCHAR,           -- 회사명
    company_en VARCHAR,        -- 영문 회사명
    position VARCHAR,          -- 직급/직책
    department VARCHAR,        -- 부서
    start_date VARCHAR,        -- 시작일
    end_date VARCHAR,          -- 종료일
    is_current BOOLEAN,        -- 현재 재직 여부
    duties TEXT,               -- 담당 업무
    achievements TEXT          -- 성과
);

-- 학력 (1:N)
CREATE TABLE educations (
    id UUID PRIMARY KEY,
    candidate_id UUID REFERENCES candidates(id),
    institution VARCHAR,       -- 학교명
    degree VARCHAR,            -- 학위 (학사/석사/박사)
    major VARCHAR,             -- 전공
    start_year INTEGER,
    end_year INTEGER,
    is_abroad BOOLEAN          -- 해외 학교 여부
);

-- 자격증 (1:N)
CREATE TABLE certifications (
    id UUID PRIMARY KEY,
    candidate_id UUID REFERENCES candidates(id),
    name VARCHAR,              -- 자격증명
    issuer VARCHAR             -- 발급 기관
);

-- 어학 (1:N)
CREATE TABLE language_skills (
    id UUID PRIMARY KEY,
    candidate_id UUID REFERENCES candidates(id),
    language VARCHAR,          -- 언어
    test_name VARCHAR,         -- 시험명 (TOEIC, JLPT 등)
    score VARCHAR,             -- 점수
    level VARCHAR              -- 수준
);

-- 카테고리 (직무 분류)
CREATE TABLE categories (
    id UUID PRIMARY KEY,
    name VARCHAR               -- Accounting, HR, Sales, Engineer 등
);

-- 후보자-카테고리 매핑 (M:N)
CREATE TABLE candidates_categories (
    candidate_id UUID REFERENCES candidates(id),
    category_id UUID REFERENCES categories(id)
);
"""

# ────────────────────────────────────────────
# System prompt
# ────────────────────────────────────────────

SEARCH_SYSTEM_PROMPT = f"""당신은 헤드헌팅 후보자 검색 SQL 생성기입니다.

## 역할
1. 사용자의 자연어 요청이 헤드헌팅 업무(후보자 검색, 인재 추천, 채용 관련)인지 판단합니다.
2. 헤드헌팅 업무이면 PostgreSQL SELECT 쿼리를 생성합니다.
3. 헤드헌팅 업무가 아니면 거절합니다.

## 헤드헌팅 관련 업무 예시
- 후보자 검색/추천 (경력, 학력, 회사, 직무, 나이, 성별, 지역 등)
- 인재풀 조회, 필터링, 정렬
- 후보자 비교, 통계 (몇 명인지, 평균 경력 등)

## 헤드헌팅 업무가 아닌 예시
- 일반 대화, 인사, 잡담
- 날씨, 뉴스, 일정
- 프로그래밍, 번역 등 다른 업무

## DB 스키마
{DB_SCHEMA}

## 출력 형식 (JSON만 출력)

헤드헌팅 관련 요청인 경우:
```json
{{
  "is_valid": true,
  "sql": "SELECT ... FROM candidates ...",
  "ai_message": "검색 결과를 안내하는 한국어 존대말 메시지"
}}
```

헤드헌팅 관련이 아닌 경우:
```json
{{
  "is_valid": false,
  "sql": null,
  "ai_message": "죄송합니다. 저는 후보자 검색 전용 AI입니다. 후보자 경력, 학력, 직무 등에 대해 질문해주세요."
}}
```

## SQL 규칙
1. SELECT만 허용. INSERT/UPDATE/DELETE/DROP/ALTER 절대 금지.
2. 결과에 반드시 candidates.id, candidates.name을 포함하세요.
3. JOIN으로 careers, educations 등 연결 가능합니다.
4. 회사명 매칭 시 ILIKE '%키워드%'는 오탐이 발생할 수 있습니다 (예: '%SK%'가 'Nu Skin'도 매칭). 시작 매칭(LIKE 'SK%')을 우선 사용하고, 필요 시 오탐 제외 조건을 추가하세요.
5. LIMIT은 사용자가 명시한 경우에만 넣으세요. 기본 LIMIT은 넣지 마세요.
6. 음성 입력이므로 필러 단어(음, 어, 그, 있잖아요)는 무시하세요.
7. 올해는 2026년입니다. "나이 50" → birth_year <= 1976.
8. DISTINCT를 적절히 사용하세요 (JOIN 시 중복 방지).
9. ai_message에 검색 조건을 간결하게 요약하세요. DB에 없는 정보(대학교 소재지, 업종 분류 등)를 추정해서 검색한 경우 "DB에 소재지 정보가 없어 학교명으로 추정했습니다" 같이 한계를 명시하세요.
10. 이전 SQL이 주어지면, 대화 맥락에서 이전 결과를 좁히는 건지 새 검색인지 자연스럽게 판단하세요."""


# ────────────────────────────────────────────
# SQL safety check
# ────────────────────────────────────────────

_FORBIDDEN_PATTERNS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|EXEC)\b",
    re.IGNORECASE,
)


def _is_safe_sql(sql: str) -> bool:
    """Only allow SELECT queries."""
    if not sql or not sql.strip().upper().startswith("SELECT"):
        return False
    if _FORBIDDEN_PATTERNS.search(sql):
        return False
    if ";" in sql.replace(sql.strip(), ""):  # trailing semicolons only
        pass
    return True


# ────────────────────────────────────────────
# Main search function
# ────────────────────────────────────────────


def parse_and_search(user_text: str, previous_sql: str | None = None) -> dict:
    """Natural language → LLM SQL → execute → results.

    Returns:
        {
            "candidates": [{"id": ..., "name": ..., ...}, ...],
            "sql": "SELECT ...",
            "ai_message": "...",
            "is_valid": True/False,
            "result_count": int,
        }
    """
    prompt_parts = []
    if previous_sql:
        prompt_parts.append(f"이전 검색 SQL:\n{previous_sql}")
    prompt_parts.append(f"사용자 요청: {user_text}")
    prompt = "\n".join(prompt_parts)

    try:
        raw = call_llm(prompt, system=SEARCH_SYSTEM_PROMPT, timeout=30, max_tokens=800)
        parsed = _extract_json(raw)
    except Exception:
        logger.exception("LLM SQL generation failed")
        return {
            "candidates": [],
            "sql": None,
            "ai_message": "검색 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
            "is_valid": True,
            "result_count": 0,
        }

    if not parsed.get("is_valid"):
        return {
            "candidates": [],
            "sql": None,
            "ai_message": parsed.get(
                "ai_message",
                "죄송합니다. 저는 후보자 검색 전용 AI입니다.",
            ),
            "is_valid": False,
            "result_count": 0,
        }

    sql = (parsed.get("sql") or "").strip().rstrip(";")
    if not _is_safe_sql(sql):
        logger.warning("Unsafe SQL rejected: %s", sql)
        return {
            "candidates": [],
            "sql": None,
            "ai_message": "검색 조건을 이해하지 못했습니다. 다시 말씀해주세요.",
            "is_valid": True,
            "result_count": 0,
        }

    # Execute with one retry on SQL error
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            columns = [col.name for col in cursor.description]
            rows = cursor.fetchall()
    except Exception as exc:
        logger.warning("SQL failed, retrying with error context: %s", exc)
        # Give LLM the error and ask to fix
        retry_prompt = (
            f"이전 SQL 실행 시 오류 발생:\nSQL: {sql}\n오류: {exc}\n\n"
            f"오류를 수정하여 올바른 SQL을 다시 생성하세요.\n원래 요청: {user_text}"
        )
        try:
            raw2 = call_llm(retry_prompt, system=SEARCH_SYSTEM_PROMPT, timeout=30, max_tokens=800)
            parsed2 = _extract_json(raw2)
            sql2 = (parsed2.get("sql") or "").strip().rstrip(";")
            if _is_safe_sql(sql2):
                sql = sql2
                with connection.cursor() as cursor:
                    cursor.execute(sql)
                    columns = [col.name for col in cursor.description]
                    rows = cursor.fetchall()
                ai_message = parsed2.get("ai_message", parsed.get("ai_message", ""))
            else:
                raise RuntimeError("Retry SQL also unsafe")
        except Exception:
            logger.exception("SQL retry also failed: %s", sql)
            return {
                "candidates": [],
                "sql": sql,
                "ai_message": "검색 실행 중 오류가 발생했습니다. 조건을 바꿔서 다시 시도해주세요.",
                "is_valid": True,
                "result_count": 0,
            }

    results = [dict(zip(columns, row)) for row in rows]
    ai_message = parsed.get("ai_message", f"{len(results)}명을 찾았습니다.")

    return {
        "candidates": results,
        "sql": sql,
        "ai_message": ai_message,
        "is_valid": True,
        "result_count": len(results),
    }


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response."""
    import json

    text = text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)
