# Voice-First 후보자 검색 (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Google Drive에서 파싱된 후보자 DB를 음성/텍스트 대화형 검색 UI로 검색하는 Voice-First 인터페이스 구축 (플로팅 챗봇 + 풀스크린 결과 리스트 + 하이브리드 검색)

**Architecture:** candidates 앱 확장. CandidateEmbedding 모델(pgvector)로 시맨틱 검색, SearchSession/SearchTurn 모델로 multi-turn 대화 관리. LLM이 자연어→구조화 필터 JSON 변환. 프론트엔드는 HTMX + Tailwind + vanilla JS (MediaRecorder + Whisper API). v1 네비게이션은 유지하되, 기본 랜딩을 후보자 검색으로 변경.

**Tech Stack:** Django 5.2, PostgreSQL 16 + pgvector, HTMX 2.0, Tailwind CSS (CDN), Whisper API (openai SDK), Gemini embedding (common/embedding.py), common/llm.py (call_llm_json)

**Design Docs:**
- `docs/v2/design-voice-search.md` — 전체 UI/UX 스펙, 와이어프레임, 기술 아키텍처

---

## File Structure

```
candidates/
├── models.py                          # + CandidateEmbedding, SearchSession, SearchTurn
├── urls.py                            # + search URLs (/candidates/, /candidates/<pk>/, /candidates/search/, /candidates/voice/)
├── views.py                           # + candidate_list, candidate_detail, search_chat, voice_transcribe
├── services/
│   ├── search.py                      # NEW: 자연어→필터 변환 + 하이브리드 검색 엔진
│   ├── embedding.py                   # NEW: 후보자 임베딩 생성/조회
│   └── whisper.py                     # NEW: Whisper API 음성→텍스트
├── management/
│   └── commands/
│       └── generate_embeddings.py     # NEW: 기존 후보자 임베딩 배치 생성
├── templates/
│   └── candidates/
│       ├── search.html                # NEW: 전체 페이지 (base.html 확장)
│       ├── detail.html                # NEW: 전체 페이지 (base.html 확장)
│       └── partials/
│           ├── candidate_list.html    # NEW: 후보자 카드 리스트 (HTMX partial)
│           ├── candidate_card.html    # NEW: 개별 카드 컴포넌트
│           ├── candidate_detail_content.html  # NEW: 상세 HTMX partial
│           ├── chatbot_modal.html     # NEW: 플로팅 챗봇 모달
│           ├── chat_messages.html     # NEW: 채팅 메시지 리스트 (HTMX partial)
│           └── search_status_bar.html # NEW: 검색 상태 바
└── static/
    └── candidates/
        └── chatbot.js                 # NEW: 챗봇 JS (모달, 마이크, HTMX 연동)

tests/
├── test_candidate_embedding.py        # 임베딩 모델/서비스 테스트
├── test_search_service.py             # 검색 엔진 테스트
├── test_search_views.py               # 뷰 + URL 테스트
└── test_whisper_service.py            # Whisper 서비스 테스트

main/settings.py                       # + OPENAI_API_KEY 설정
```

---

## Task 1: CandidateEmbedding 모델 + pgvector

**Files:**
- Modify: `candidates/models.py` — CandidateEmbedding 모델 추가
- Test: `tests/test_candidate_embedding.py`

### Step 1: Write the model test

- [ ] **1.1: Create test file**

```python
# tests/test_candidate_embedding.py
import pytest
from django.db import connection

from candidates.models import Candidate, CandidateEmbedding, Category


@pytest.fixture
def category(db):
    return Category.objects.create(name="HR", name_ko="인사")


@pytest.fixture
def candidate(db, category):
    return Candidate.objects.create(
        name="홍길동",
        birth_year=1985,
        current_company="삼성전자",
        current_position="과장",
        total_experience_years=10,
        primary_category=category,
    )


@pytest.mark.django_db
def test_create_embedding(candidate):
    """CandidateEmbedding can store a 3072-dim vector."""
    vec = [0.1] * 3072
    emb = CandidateEmbedding.objects.create(
        candidate=candidate,
        embedding=vec,
        text_hash="abc123",
    )
    assert emb.pk is not None
    assert emb.candidate == candidate


@pytest.mark.django_db
def test_embedding_unique_per_candidate(candidate):
    """One candidate → one embedding (unique constraint)."""
    vec = [0.1] * 3072
    CandidateEmbedding.objects.create(
        candidate=candidate,
        embedding=vec,
        text_hash="abc123",
    )
    with pytest.raises(Exception):
        CandidateEmbedding.objects.create(
            candidate=candidate,
            embedding=vec,
            text_hash="def456",
        )


@pytest.mark.django_db
def test_pgvector_cosine_search(candidate, category):
    """Cosine similarity search returns nearest candidates."""
    # Create 2 candidates with different embeddings
    vec_a = [1.0] + [0.0] * 3071
    vec_b = [0.0] + [1.0] + [0.0] * 3070

    CandidateEmbedding.objects.create(
        candidate=candidate, embedding=vec_a, text_hash="a"
    )

    candidate_b = Candidate.objects.create(
        name="김철수",
        primary_category=category,
    )
    CandidateEmbedding.objects.create(
        candidate=candidate_b, embedding=vec_b, text_hash="b"
    )

    # Search with query close to vec_a
    query_vec = [0.9] + [0.1] + [0.0] * 3070
    results = CandidateEmbedding.objects.order_by(
        CandidateEmbedding.cosine_distance_expression(query_vec)
    )[:10]
    assert results[0].candidate == candidate
```

- [ ] **1.2: Run test — expect FAIL**

```bash
uv run pytest tests/test_candidate_embedding.py -v
```

Expected: `ImportError: cannot import name 'CandidateEmbedding'`

### Step 2: Implement model

- [ ] **1.3: Add CandidateEmbedding to models.py**

Add at the end of `candidates/models.py`:

```python
from pgvector.django import VectorField, CosineDistance


class CandidateEmbedding(BaseModel):
    """후보자 임베딩 벡터 (Gemini 3072-dim)."""

    candidate = models.OneToOneField(
        Candidate,
        on_delete=models.CASCADE,
        related_name="embedding",
    )
    embedding = VectorField(dimensions=3072)
    text_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "candidate_embeddings"

    def __str__(self):
        return f"Embedding({self.candidate.name})"

    @staticmethod
    def cosine_distance_expression(query_vector):
        return CosineDistance("embedding", query_vector)
```

- [ ] **1.4: Makemigrations + migrate**

```bash
uv run python manage.py makemigrations candidates -n add_candidate_embedding
uv run python manage.py migrate
```

- [ ] **1.5: Run tests — expect PASS**

```bash
uv run pytest tests/test_candidate_embedding.py -v
```

- [ ] **1.6: Commit**

```bash
git add candidates/models.py candidates/migrations/ tests/test_candidate_embedding.py
git commit -m "feat: CandidateEmbedding model with pgvector cosine search"
```

---

## Task 2: 임베딩 생성 서비스 + 배치 커맨드

**Files:**
- Create: `candidates/services/embedding.py`
- Create: `candidates/management/commands/generate_embeddings.py`
- Test: `tests/test_candidate_embedding.py` (확장)

### Step 1: Embedding service

- [ ] **2.1: Add service tests to test file**

Append to `tests/test_candidate_embedding.py`:

```python
from unittest.mock import patch

from candidates.services.embedding import build_embedding_text, generate_candidate_embedding


@pytest.mark.django_db
def test_build_embedding_text(candidate):
    """Build searchable text from candidate data."""
    text = build_embedding_text(candidate)
    assert "홍길동" in text
    assert "삼성전자" in text
    assert "과장" in text


@pytest.mark.django_db
@patch("candidates.services.embedding.get_embedding")
def test_generate_candidate_embedding(mock_embed, candidate):
    """Generate and save embedding for a candidate."""
    mock_embed.return_value = [0.5] * 3072
    emb = generate_candidate_embedding(candidate)
    assert emb is not None
    assert CandidateEmbedding.objects.filter(candidate=candidate).exists()
    mock_embed.assert_called_once()


@pytest.mark.django_db
@patch("candidates.services.embedding.get_embedding")
def test_generate_embedding_skips_if_unchanged(mock_embed, candidate):
    """Skip re-embedding if text hash unchanged."""
    mock_embed.return_value = [0.5] * 3072
    generate_candidate_embedding(candidate)
    generate_candidate_embedding(candidate)  # second call
    assert mock_embed.call_count == 1  # skipped
```

- [ ] **2.2: Run tests — expect FAIL**

```bash
uv run pytest tests/test_candidate_embedding.py::test_build_embedding_text -v
```

- [ ] **2.3: Implement embedding service**

Create `candidates/services/embedding.py`:

```python
"""Generate and manage candidate embeddings for semantic search."""

import hashlib

from candidates.models import Candidate, CandidateEmbedding
from common.embedding import get_embedding


def build_embedding_text(candidate: Candidate) -> str:
    """Build a searchable text representation of a candidate for embedding."""
    parts = [candidate.name]

    if candidate.current_company:
        parts.append(f"현재 {candidate.current_company} {candidate.current_position or ''}")

    if candidate.total_experience_years:
        parts.append(f"경력 {candidate.total_experience_years}년")

    if candidate.summary:
        parts.append(candidate.summary)

    # Careers
    for career in candidate.careers.all()[:5]:
        line = career.company
        if career.position:
            line += f" {career.position}"
        if career.department:
            line += f" {career.department}"
        if career.duties:
            line += f" {career.duties[:100]}"
        parts.append(line)

    # Education
    for edu in candidate.educations.all():
        line = edu.institution
        if edu.degree:
            line += f" {edu.degree}"
        if edu.major:
            line += f" {edu.major}"
        parts.append(line)

    # Certifications
    for cert in candidate.certifications.all():
        parts.append(cert.name)

    # Core competencies
    if candidate.core_competencies:
        parts.extend(candidate.core_competencies[:10])

    # Categories
    for cat in candidate.categories.all():
        parts.append(cat.name)

    return " ".join(parts)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def generate_candidate_embedding(candidate: Candidate) -> CandidateEmbedding | None:
    """Generate embedding for a candidate. Skips if text unchanged.

    Returns the CandidateEmbedding instance, or None on failure.
    """
    text = build_embedding_text(candidate)
    h = _text_hash(text)

    existing = CandidateEmbedding.objects.filter(candidate=candidate).first()
    if existing and existing.text_hash == h:
        return existing  # unchanged

    vec = get_embedding(text)
    if vec is None:
        return None

    if existing:
        existing.embedding = vec
        existing.text_hash = h
        existing.save(update_fields=["embedding", "text_hash", "updated_at"])
        return existing

    return CandidateEmbedding.objects.create(
        candidate=candidate,
        embedding=vec,
        text_hash=h,
    )
```

- [ ] **2.4: Run tests — expect PASS**

```bash
uv run pytest tests/test_candidate_embedding.py -v
```

- [ ] **2.5: Create batch management command**

Create `candidates/management/commands/generate_embeddings.py`:

```python
"""Generate embeddings for all candidates missing them.

Usage:
    uv run python manage.py generate_embeddings
    uv run python manage.py generate_embeddings --force  # regenerate all
"""

from django.core.management.base import BaseCommand

from candidates.models import Candidate, CandidateEmbedding
from candidates.services.embedding import generate_candidate_embedding


class Command(BaseCommand):
    help = "Generate embeddings for candidates"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Regenerate all embeddings (ignore text_hash cache)",
        )

    def handle(self, *args, **options):
        force = options.get("force")

        if force:
            candidates = Candidate.objects.all()
        else:
            existing_ids = CandidateEmbedding.objects.values_list(
                "candidate_id", flat=True
            )
            candidates = Candidate.objects.exclude(id__in=existing_ids)

        total = candidates.count()
        self.stdout.write(f"Generating embeddings for {total} candidates...")

        ok, fail = 0, 0
        for c in candidates.iterator():
            result = generate_candidate_embedding(c)
            if result:
                ok += 1
            else:
                fail += 1
                self.stderr.write(f"  FAIL: {c.name}")

        self.stdout.write(self.style.SUCCESS(f"Done: {ok} OK, {fail} failed"))
```

- [ ] **2.6: Commit**

```bash
git add candidates/services/embedding.py candidates/management/commands/generate_embeddings.py tests/test_candidate_embedding.py
git commit -m "feat: candidate embedding service + batch generation command"
```

- [ ] **2.7: Run batch generation on existing data**

```bash
uv run python manage.py generate_embeddings
```

---

## Task 3: SearchSession + SearchTurn 모델

**Files:**
- Modify: `candidates/models.py` — SearchSession, SearchTurn 추가
- Test: `tests/test_search_service.py`

- [ ] **3.1: Write model tests**

Create `tests/test_search_service.py`:

```python
import pytest
from django.contrib.auth import get_user_model

from candidates.models import SearchSession, SearchTurn

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="tester", password="test1234")


@pytest.mark.django_db
def test_create_search_session(user):
    session = SearchSession.objects.create(user=user)
    assert session.is_active is True
    assert session.current_filters == {}


@pytest.mark.django_db
def test_create_search_turn(user):
    session = SearchSession.objects.create(user=user)
    turn = SearchTurn.objects.create(
        session=session,
        turn_number=1,
        input_type="text",
        user_text="회계 10년차 이상",
        ai_response="30명을 찾았습니다",
        filters_applied={"category": "Accounting", "min_experience_years": 10},
        result_count=30,
    )
    assert turn.session == session
    assert turn.filters_applied["category"] == "Accounting"
```

- [ ] **3.2: Run tests — expect FAIL**

```bash
uv run pytest tests/test_search_service.py -v
```

- [ ] **3.3: Add models to candidates/models.py**

Append before `CandidateEmbedding`:

```python
class SearchSession(BaseModel):
    """음성/텍스트 검색 세션 (multi-turn)."""

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="search_sessions",
    )
    is_active = models.BooleanField(default=True)
    current_filters = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "search_sessions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Session({self.user}, active={self.is_active})"


class SearchTurn(BaseModel):
    """검색 세션 내 개별 턴."""

    class InputType(models.TextChoices):
        VOICE = "voice", "음성"
        TEXT = "text", "텍스트"

    session = models.ForeignKey(
        SearchSession,
        on_delete=models.CASCADE,
        related_name="turns",
    )
    turn_number = models.PositiveIntegerField()
    input_type = models.CharField(
        max_length=10,
        choices=InputType.choices,
        default=InputType.TEXT,
    )
    user_text = models.TextField()
    ai_response = models.TextField(blank=True)
    filters_applied = models.JSONField(default=dict, blank=True)
    result_count = models.IntegerField(default=0)

    class Meta:
        db_table = "search_turns"
        ordering = ["turn_number"]

    def __str__(self):
        return f"Turn {self.turn_number}: {self.user_text[:30]}"
```

- [ ] **3.4: Makemigrations + migrate**

```bash
uv run python manage.py makemigrations candidates -n add_search_session_turn
uv run python manage.py migrate
```

- [ ] **3.5: Run tests — expect PASS**

```bash
uv run pytest tests/test_search_service.py -v
```

- [ ] **3.6: Commit**

```bash
git add candidates/models.py candidates/migrations/ tests/test_search_service.py
git commit -m "feat: SearchSession + SearchTurn models for multi-turn search"
```

---

## Task 4: 검색 엔진 서비스 (자연어→필터 + 하이브리드 검색)

**Files:**
- Create: `candidates/services/search.py`
- Test: `tests/test_search_service.py` (확장)

- [ ] **4.1: Add search service tests**

Append to `tests/test_search_service.py`:

```python
from unittest.mock import patch, MagicMock

from candidates.models import Candidate, Category, CandidateEmbedding
from candidates.services.search import (
    parse_search_query,
    execute_structured_search,
    hybrid_search,
)


@pytest.fixture
def category(db):
    return Category.objects.create(name="Accounting", name_ko="회계")


@pytest.fixture
def candidate_a(db, category):
    c = Candidate.objects.create(
        name="강솔찬",
        current_company="현대엠시트",
        current_position="회계팀장",
        total_experience_years=12,
        primary_category=category,
    )
    c.categories.add(category)
    return c


@pytest.fixture
def candidate_b(db, category):
    c = Candidate.objects.create(
        name="김영희",
        current_company="스타트업",
        current_position="인턴",
        total_experience_years=1,
        primary_category=category,
    )
    c.categories.add(category)
    return c


@pytest.mark.django_db
def test_execute_structured_search_by_category(candidate_a, candidate_b, category):
    filters = {"category": "Accounting"}
    results = execute_structured_search(filters)
    assert candidate_a in results
    assert candidate_b in results


@pytest.mark.django_db
def test_execute_structured_search_min_experience(candidate_a, candidate_b):
    filters = {"min_experience_years": 10}
    results = execute_structured_search(filters)
    assert candidate_a in results
    assert candidate_b not in results


@pytest.mark.django_db
def test_execute_structured_search_company(candidate_a, candidate_b):
    filters = {"companies_include": ["현대"]}
    results = execute_structured_search(filters)
    assert candidate_a in results
    assert candidate_b not in results


@pytest.mark.django_db
@patch("candidates.services.search.call_llm_json")
def test_parse_search_query(mock_llm):
    mock_llm.return_value = {
        "filters": {
            "category": "Accounting",
            "min_experience_years": 10,
        },
        "semantic_query": "회계 10년차 이상",
        "action": "new",
        "ai_message": "회계 분야 10년 이상 경력 후보자를 찾겠습니다.",
    }
    result = parse_search_query("회계 10년차 이상 찾아줘", current_filters={})
    assert result["filters"]["category"] == "Accounting"
    assert result["action"] == "new"
```

- [ ] **4.2: Run tests — expect FAIL**

```bash
uv run pytest tests/test_search_service.py::test_execute_structured_search_by_category -v
```

- [ ] **4.3: Implement search service**

Create `candidates/services/search.py`:

```python
"""Search engine: natural language → structured filters + hybrid search."""

from __future__ import annotations

import logging
from functools import reduce
from operator import or_

from django.db.models import Q, QuerySet

from candidates.models import Candidate, CandidateEmbedding, Category
from common.embedding import get_embedding
from common.llm import call_llm_json

logger = logging.getLogger(__name__)

CATEGORY_NAMES = [
    "Accounting", "EHS", "Engineer", "Finance", "HR", "Law",
    "Logistics", "Marketing", "MD", "MR", "Plant", "PR+AD",
    "Procurement", "Production", "Quality", "R&D", "Sales",
    "SCM", "SI+IT", "VMD",
]

SEARCH_SYSTEM_PROMPT = (
    "당신은 헤드헌팅 후보자 검색 시스템입니다.\n"
    "사용자의 자연어 검색 요청을 구조화된 필터 JSON으로 변환합니다.\n\n"
    "사용 가능한 카테고리: " + ", ".join(CATEGORY_NAMES) + "\n\n"
    "규칙:\n"
    "1. 확실하지 않은 필터는 null로 두세요.\n"
    "2. 회사명 필터는 부분 매치입니다 (예: '삼성' → 삼성전자, 삼성SDI 등 포함).\n"
    "3. action은 'new'(새 검색), 'narrow'(현재 결과에서 좁히기), 'broaden'(넓히기) 중 하나.\n"
    "4. ai_message는 사용자에게 보여줄 응답 메시지입니다. 한국어 존대말로 작성하세요.\n"
    "5. JSON만 출력하세요.\n\n"
    "출력 JSON 스키마:\n"
    "{\n"
    '  "filters": {\n'
    '    "category": "string | null",\n'
    '    "min_experience_years": "integer | null",\n'
    '    "max_experience_years": "integer | null",\n'
    '    "companies_include": ["string"] | null,\n'
    '    "education_keyword": "string | null",\n'
    '    "position_keyword": "string | null"\n'
    "  },\n"
    '  "semantic_query": "string (시맨틱 검색용 요약 텍스트)",\n'
    '  "action": "new | narrow | broaden",\n'
    '  "ai_message": "string (사용자에게 보여줄 메시지)"\n'
    "}"
)


def parse_search_query(
    user_text: str,
    current_filters: dict,
) -> dict:
    """Convert natural language query to structured search filters via LLM.

    Returns dict with keys: filters, semantic_query, action, ai_message.
    """
    prompt_parts = []
    if current_filters:
        prompt_parts.append(f"현재 적용된 필터: {current_filters}")
    prompt_parts.append(f"사용자 요청: {user_text}")

    prompt = "\n".join(prompt_parts)

    try:
        result = call_llm_json(
            prompt,
            system=SEARCH_SYSTEM_PROMPT,
            timeout=120,
            max_tokens=500,
        )
        # Validate required keys
        if not isinstance(result, dict) or "filters" not in result:
            return _fallback_result(user_text)
        result.setdefault("action", "new")
        result.setdefault("ai_message", "검색 결과를 확인해주세요.")
        result.setdefault("semantic_query", user_text)
        return result
    except Exception:
        logger.exception("LLM search query parsing failed")
        return _fallback_result(user_text)


def _fallback_result(user_text: str) -> dict:
    """Fallback when LLM fails — use full text as semantic query."""
    return {
        "filters": {},
        "semantic_query": user_text,
        "action": "new",
        "ai_message": "정확한 필터 대신 유사 검색으로 찾았습니다.",
    }


def execute_structured_search(filters: dict) -> QuerySet[Candidate]:
    """Apply structured filters to Candidate queryset."""
    qs = Candidate.objects.select_related("primary_category").prefetch_related(
        "categories"
    )

    category = filters.get("category")
    if category:
        qs = qs.filter(categories__name=category)

    min_exp = filters.get("min_experience_years")
    if min_exp is not None:
        qs = qs.filter(total_experience_years__gte=min_exp)

    max_exp = filters.get("max_experience_years")
    if max_exp is not None:
        qs = qs.filter(total_experience_years__lte=max_exp)

    companies = filters.get("companies_include")
    if companies:
        q_list = [Q(current_company__icontains=c) for c in companies]
        career_q = [Q(careers__company__icontains=c) for c in companies]
        qs = qs.filter(reduce(or_, q_list + career_q)).distinct()

    edu_kw = filters.get("education_keyword")
    if edu_kw:
        qs = qs.filter(
            Q(educations__institution__icontains=edu_kw)
            | Q(educations__major__icontains=edu_kw)
        ).distinct()

    position_kw = filters.get("position_keyword")
    if position_kw:
        qs = qs.filter(
            Q(current_position__icontains=position_kw)
            | Q(careers__position__icontains=position_kw)
        ).distinct()

    return qs


def hybrid_search(
    filters: dict,
    semantic_query: str | None = None,
    limit: int = 50,
) -> list[Candidate]:
    """Hybrid search: structured filters + semantic ranking.

    1. Apply structured filters
    2. If semantic_query provided, rank by cosine similarity
    3. Otherwise, order by updated_at desc
    """
    qs = execute_structured_search(filters)

    if semantic_query:
        query_vec = get_embedding(semantic_query)
        if query_vec:
            # Get candidate IDs from structured search
            candidate_ids = set(qs.values_list("id", flat=True))

            if candidate_ids:
                # Rank by cosine similarity within filtered set
                embeddings = (
                    CandidateEmbedding.objects.filter(
                        candidate_id__in=candidate_ids
                    )
                    .select_related("candidate", "candidate__primary_category")
                    .order_by(
                        CandidateEmbedding.cosine_distance_expression(query_vec)
                    )[:limit]
                )
                ranked = [e.candidate for e in embeddings]

                # Add candidates without embeddings at the end
                ranked_ids = {c.id for c in ranked}
                unranked = qs.exclude(id__in=ranked_ids)[:limit]
                return ranked + list(unranked)
            return []

    # No semantic query — order by recency
    return list(qs.order_by("-updated_at")[:limit])
```

- [ ] **4.4: Run tests — expect PASS**

```bash
uv run pytest tests/test_search_service.py -v
```

- [ ] **4.5: Commit**

```bash
git add candidates/services/search.py tests/test_search_service.py
git commit -m "feat: search engine with structured filters + hybrid search"
```

---

## Task 5: Whisper 음성→텍스트 서비스

**Files:**
- Create: `candidates/services/whisper.py`
- Modify: `main/settings.py` — OPENAI_API_KEY 추가
- Test: `tests/test_whisper_service.py`

- [ ] **5.1: Write Whisper service test**

Create `tests/test_whisper_service.py`:

```python
import io
from unittest.mock import patch, MagicMock

import pytest

from candidates.services.whisper import transcribe_audio


@patch("candidates.services.whisper._get_openai_client")
def test_transcribe_audio(mock_client_fn):
    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = MagicMock(text="회계 경력 10년 이상")
    mock_client_fn.return_value = mock_client

    audio_file = io.BytesIO(b"fake audio data")
    audio_file.name = "test.webm"
    result = transcribe_audio(audio_file)

    assert result == "회계 경력 10년 이상"
    mock_client.audio.transcriptions.create.assert_called_once()
```

- [ ] **5.2: Run test — expect FAIL**

```bash
uv run pytest tests/test_whisper_service.py -v
```

- [ ] **5.3: Add OPENAI_API_KEY to settings**

Add to `main/settings.py` after `GEMINI_API_KEY`:

```python
# OpenAI (Whisper API)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
```

- [ ] **5.4: Implement Whisper service**

Create `candidates/services/whisper.py`:

```python
"""Whisper API speech-to-text service."""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_client = None


def _get_openai_client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def transcribe_audio(audio_file) -> str:
    """Transcribe audio file to text using Whisper API.

    Args:
        audio_file: File-like object with .name attribute (webm/mp4/ogg).

    Returns:
        Transcribed text string.

    Raises:
        RuntimeError on API failure.
    """
    try:
        client = _get_openai_client()
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="ko",
        )
        return transcript.text
    except Exception as e:
        logger.exception("Whisper transcription failed")
        raise RuntimeError(f"음성 인식에 실패했습니다: {e}") from e
```

- [ ] **5.5: Run tests — expect PASS**

```bash
uv run pytest tests/test_whisper_service.py -v
```

- [ ] **5.6: Commit**

```bash
git add candidates/services/whisper.py main/settings.py tests/test_whisper_service.py
git commit -m "feat: Whisper API speech-to-text service"
```

---

## Task 6: 검색 뷰 + URL 라우팅

**Files:**
- Modify: `candidates/views.py` — candidate_list, candidate_detail, search_chat, voice_transcribe 뷰 추가
- Modify: `candidates/urls.py` — URL 패턴 추가
- Test: `tests/test_search_views.py`

- [ ] **6.1: Write view tests**

Create `tests/test_search_views.py`:

```python
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from candidates.models import Candidate, Category, SearchSession

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="tester", password="test1234")


@pytest.fixture
def auth_client(user):
    client = Client()
    client.login(username="tester", password="test1234")
    return client


@pytest.fixture
def category(db):
    return Category.objects.create(name="Accounting", name_ko="회계")


@pytest.fixture
def candidate(db, category):
    c = Candidate.objects.create(
        name="강솔찬",
        current_company="현대엠시트",
        total_experience_years=12,
        primary_category=category,
    )
    c.categories.add(category)
    return c


@pytest.mark.django_db
def test_candidate_list_page(auth_client, candidate):
    resp = auth_client.get("/candidates/")
    assert resp.status_code == 200
    assert "강솔찬" in resp.content.decode()


@pytest.mark.django_db
def test_candidate_list_htmx_partial(auth_client, candidate):
    resp = auth_client.get(
        "/candidates/",
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="main-content",
    )
    assert resp.status_code == 200


@pytest.mark.django_db
def test_candidate_list_filter_category(auth_client, candidate, category):
    resp = auth_client.get(f"/candidates/?category={category.name}")
    assert resp.status_code == 200
    assert "강솔찬" in resp.content.decode()


@pytest.mark.django_db
def test_candidate_detail_page(auth_client, candidate):
    resp = auth_client.get(f"/candidates/{candidate.pk}/")
    assert resp.status_code == 200
    assert "강솔찬" in resp.content.decode()


@pytest.mark.django_db
@patch("candidates.views.parse_search_query")
@patch("candidates.views.hybrid_search")
def test_search_chat(mock_search, mock_parse, auth_client, candidate):
    mock_parse.return_value = {
        "filters": {"category": "Accounting"},
        "semantic_query": "회계",
        "action": "new",
        "ai_message": "회계 후보자 1명을 찾았습니다.",
    }
    mock_search.return_value = [candidate]

    resp = auth_client.post(
        "/candidates/search/",
        data=json.dumps({"message": "회계 찾아줘"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = json.loads(resp.content)
    assert data["ai_message"] == "회계 후보자 1명을 찾았습니다."
    assert data["result_count"] == 1


@pytest.mark.django_db
def test_login_required(client):
    resp = client.get("/candidates/")
    assert resp.status_code == 302  # redirect to login
```

- [ ] **6.2: Run tests — expect FAIL**

```bash
uv run pytest tests/test_search_views.py -v
```

- [ ] **6.3: Implement views**

Replace `candidates/views.py`:

```python
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, render

from .models import (
    Candidate,
    Category,
    ExtractionLog,
    SearchSession,
    SearchTurn,
)
from .services.search import hybrid_search, parse_search_query
from .services.whisper import transcribe_audio

# -- Review views (existing) ---------------------------------------------------

REVIEW_PAGE_SIZE = 20

STATUS_CHOICES = [
    ("needs_review", "검토 필요"),
    ("auto_confirmed", "자동 확인"),
    ("confirmed", "확인 완료"),
    ("failed", "실패"),
]


@login_required
def review_list(request):
    status_filter = request.GET.get("status", "needs_review")

    candidates = Candidate.objects.filter(
        validation_status=status_filter,
    ).select_related("primary_category")

    total = candidates.count()
    page = int(request.GET.get("page", 1))
    offset = (page - 1) * REVIEW_PAGE_SIZE
    page_candidates = candidates[offset : offset + REVIEW_PAGE_SIZE]
    has_more = candidates[
        offset + REVIEW_PAGE_SIZE : offset + REVIEW_PAGE_SIZE + 1
    ].exists()

    template = (
        "candidates/partials/review_list_content.html"
        if request.htmx
        else "candidates/review_list.html"
    )
    return render(
        request,
        template,
        {
            "candidates": page_candidates,
            "page": page,
            "has_more": has_more,
            "total": total,
            "status_filter": status_filter,
            "status_choices": STATUS_CHOICES,
        },
    )


@login_required
def review_detail(request, pk):
    candidate = get_object_or_404(Candidate, pk=pk)

    primary_resume = candidate.resumes.filter(is_primary=True).first()
    careers = candidate.careers.all()
    educations = candidate.educations.all()
    certifications = candidate.certifications.all()
    language_skills = candidate.language_skills.all()
    logs = candidate.extraction_logs.all()[:10]

    template = (
        "candidates/partials/review_detail_content.html"
        if request.htmx
        else "candidates/review_detail.html"
    )
    return render(
        request,
        template,
        {
            "candidate": candidate,
            "primary_resume": primary_resume,
            "careers": careers,
            "educations": educations,
            "certifications": certifications,
            "language_skills": language_skills,
            "logs": logs,
        },
    )


@login_required
def review_confirm(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    candidate = get_object_or_404(Candidate, pk=pk)
    candidate.validation_status = Candidate.ValidationStatus.CONFIRMED
    candidate.save(update_fields=["validation_status", "updated_at"])

    ExtractionLog.objects.create(
        candidate=candidate,
        action=ExtractionLog.Action.HUMAN_CONFIRM,
        note="사람이 검토 확인",
    )

    return HttpResponse(
        status=204,
        headers={"HX-Redirect": "/candidates/review/"},
    )


@login_required
def review_reject(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    candidate = get_object_or_404(Candidate, pk=pk)
    candidate.validation_status = Candidate.ValidationStatus.FAILED
    candidate.save(update_fields=["validation_status", "updated_at"])

    reason = request.POST.get("reason", "")
    ExtractionLog.objects.create(
        candidate=candidate,
        action=ExtractionLog.Action.HUMAN_REJECT,
        note=reason,
    )

    return HttpResponse(
        status=204,
        headers={"HX-Redirect": "/candidates/review/"},
    )


# -- Search views (Phase 2) ---------------------------------------------------

SEARCH_PAGE_SIZE = 20


@login_required
def candidate_list(request):
    """Main search page: candidate list + category tabs + floating chatbot."""
    category_filter = request.GET.get("category")
    page = int(request.GET.get("page", 1))

    categories = Category.objects.all()

    # Get session for search state
    session_id = request.GET.get("session_id")
    session = None
    filters = {}
    if session_id:
        session = SearchSession.objects.filter(
            pk=session_id, user=request.user, is_active=True
        ).first()
        if session:
            filters = session.current_filters

    # If category tab clicked, override filter
    if category_filter:
        filters["category"] = category_filter
    elif category_filter == "":
        filters.pop("category", None)

    # Execute search
    if filters:
        candidates = hybrid_search(
            filters,
            semantic_query=filters.pop("_semantic_query", None),
            limit=200,
        )
        total = len(candidates)
        offset = (page - 1) * SEARCH_PAGE_SIZE
        page_candidates = candidates[offset : offset + SEARCH_PAGE_SIZE]
        has_more = len(candidates) > offset + SEARCH_PAGE_SIZE
    else:
        qs = Candidate.objects.select_related("primary_category").order_by(
            "-updated_at"
        )
        total = qs.count()
        offset = (page - 1) * SEARCH_PAGE_SIZE
        page_candidates = qs[offset : offset + SEARCH_PAGE_SIZE]
        has_more = qs[offset + SEARCH_PAGE_SIZE : offset + SEARCH_PAGE_SIZE + 1].exists()

    # Get last search summary for status bar
    last_turn = None
    if session:
        last_turn = session.turns.order_by("-turn_number").first()

    # Template selection
    if request.htmx:
        hx_target = request.headers.get("HX-Target", "")
        if hx_target == "candidate-list":
            template = "candidates/partials/candidate_list.html"
        else:
            template = "candidates/partials/candidate_list.html"
    else:
        template = "candidates/search.html"

    return render(
        request,
        template,
        {
            "candidates": page_candidates,
            "categories": categories,
            "active_category": category_filter or (filters.get("category") if filters else None),
            "total": total,
            "page": page,
            "has_more": has_more,
            "session": session,
            "last_turn": last_turn,
        },
    )


@login_required
def candidate_detail(request, pk):
    """Candidate detail page."""
    candidate = get_object_or_404(
        Candidate.objects.select_related("primary_category"),
        pk=pk,
    )
    careers = candidate.careers.all()
    educations = candidate.educations.all()
    certifications = candidate.certifications.all()
    language_skills = candidate.language_skills.all()
    primary_resume = candidate.resumes.filter(is_primary=True).first()

    template = (
        "candidates/partials/candidate_detail_content.html"
        if request.htmx
        else "candidates/detail.html"
    )
    return render(
        request,
        template,
        {
            "candidate": candidate,
            "careers": careers,
            "educations": educations,
            "certifications": certifications,
            "language_skills": language_skills,
            "primary_resume": primary_resume,
        },
    )


@login_required
def search_chat(request):
    """Handle text search query from chatbot. Returns JSON."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    body = json.loads(request.body)
    user_text = body.get("message", "").strip()
    session_id = body.get("session_id")

    if not user_text:
        return JsonResponse({"error": "메시지를 입력해주세요."}, status=400)

    # Get or create session
    session = None
    if session_id:
        session = SearchSession.objects.filter(
            pk=session_id, user=request.user, is_active=True
        ).first()

    if not session:
        # Deactivate old sessions
        SearchSession.objects.filter(user=request.user, is_active=True).update(
            is_active=False
        )
        session = SearchSession.objects.create(user=request.user)

    # Parse query via LLM
    parsed = parse_search_query(user_text, session.current_filters)

    # Apply action
    action = parsed.get("action", "new")
    new_filters = parsed.get("filters", {})

    if action == "new":
        filters = new_filters
    elif action == "narrow":
        filters = {**session.current_filters, **new_filters}
    else:  # broaden
        filters = new_filters

    # Execute search
    semantic_query = parsed.get("semantic_query")
    results = hybrid_search(filters, semantic_query=semantic_query)
    result_count = len(results)

    # Update AI message with count
    ai_message = parsed.get("ai_message", "")
    if not ai_message:
        ai_message = f"{result_count}명의 후보자를 찾았습니다."

    # Save turn
    turn_number = session.turns.count() + 1
    SearchTurn.objects.create(
        session=session,
        turn_number=turn_number,
        input_type="text",
        user_text=user_text,
        ai_response=ai_message,
        filters_applied=filters,
        result_count=result_count,
    )

    # Update session
    session.current_filters = filters
    session.save(update_fields=["current_filters", "updated_at"])

    return JsonResponse({
        "session_id": str(session.pk),
        "ai_message": ai_message,
        "result_count": result_count,
        "filters": filters,
        "action": action,
    })


@login_required
def voice_transcribe(request):
    """Handle voice audio upload → Whisper transcription. Returns JSON."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    audio = request.FILES.get("audio")
    if not audio:
        return JsonResponse({"error": "오디오 파일이 없습니다."}, status=400)

    try:
        text = transcribe_audio(audio)
        return JsonResponse({"text": text})
    except RuntimeError as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def chat_history(request):
    """Return chat messages for a session as HTML partial."""
    session_id = request.GET.get("session_id")
    turns = []
    if session_id:
        session = SearchSession.objects.filter(
            pk=session_id, user=request.user
        ).first()
        if session:
            turns = session.turns.order_by("turn_number")

    return render(
        request,
        "candidates/partials/chat_messages.html",
        {"turns": turns},
    )
```

- [ ] **6.4: Update URLs**

Replace `candidates/urls.py`:

```python
from django.urls import path

from . import views

app_name = "candidates"

urlpatterns = [
    # Phase 2: Search UI
    path("", views.candidate_list, name="candidate_list"),
    path("<uuid:pk>/", views.candidate_detail, name="candidate_detail"),
    path("search/", views.search_chat, name="search_chat"),
    path("voice/", views.voice_transcribe, name="voice_transcribe"),
    path("chat-history/", views.chat_history, name="chat_history"),
    # Phase 1: Review UI
    path("review/", views.review_list, name="review_list"),
    path("review/<uuid:pk>/", views.review_detail, name="review_detail"),
    path("review/<uuid:pk>/confirm/", views.review_confirm, name="review_confirm"),
    path("review/<uuid:pk>/reject/", views.review_reject, name="review_reject"),
]
```

- [ ] **6.5: Run tests — expect PASS**

```bash
uv run pytest tests/test_search_views.py -v
```

- [ ] **6.6: Commit**

```bash
git add candidates/views.py candidates/urls.py tests/test_search_views.py
git commit -m "feat: search views + URL routing (list, detail, chat, voice)"
```

---

## Task 7: 프론트엔드 템플릿 — 메인 검색 페이지

**Files:**
- Create: `candidates/templates/candidates/search.html`
- Create: `candidates/templates/candidates/partials/candidate_list.html`
- Create: `candidates/templates/candidates/partials/candidate_card.html`
- Create: `candidates/templates/candidates/partials/search_status_bar.html`

- [ ] **7.1: Create search.html (full page)**

Create `candidates/templates/candidates/search.html`:

```html
{% extends "common/base.html" %}

{% block title %}후보자 검색 — synco{% endblock %}

{% block content %}
<div class="flex flex-col h-screen">
  <!-- Header -->
  <header class="sticky top-0 z-10 bg-white border-b border-gray-200 px-4 py-3">
    <h1 class="text-heading text-gray-900">후보자</h1>
  </header>

  <!-- Category tabs -->
  <div class="sticky top-[52px] z-10 bg-white border-b border-gray-100 px-4 py-2 overflow-x-auto">
    <div class="flex gap-2 whitespace-nowrap">
      <a href="/candidates/"
         hx-get="/candidates/"
         hx-target="#candidate-list"
         hx-push-url="true"
         class="px-3 py-1.5 rounded-full text-[13px] font-medium transition
                {% if not active_category %}bg-primary text-white{% else %}bg-gray-100 text-gray-500 hover:bg-gray-200{% endif %}">
        전체
      </a>
      {% for cat in categories %}
      <a href="/candidates/?category={{ cat.name }}"
         hx-get="/candidates/?category={{ cat.name }}"
         hx-target="#candidate-list"
         hx-push-url="true"
         class="px-3 py-1.5 rounded-full text-[13px] font-medium transition
                {% if active_category == cat.name %}bg-primary text-white{% else %}bg-gray-100 text-gray-500 hover:bg-gray-200{% endif %}">
        {{ cat.name }}
      </a>
      {% endfor %}
    </div>
  </div>

  <!-- Search status bar -->
  <div id="search-status-bar">
    {% include "candidates/partials/search_status_bar.html" %}
  </div>

  <!-- Candidate list -->
  <div id="candidate-list" class="flex-1 overflow-y-auto">
    {% include "candidates/partials/candidate_list.html" %}
  </div>
</div>

<!-- Floating chatbot button -->
<button id="chatbot-toggle"
        onclick="toggleChatbot()"
        class="fixed bottom-20 right-4 lg:bottom-6 lg:right-6 w-14 h-14 lg:w-[60px] lg:h-[60px]
               bg-primary text-white rounded-full shadow-lg hover:bg-primary-dark
               flex items-center justify-center transition z-40"
        aria-label="AI 검색 열기">
  <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>
  </svg>
</button>

<!-- Chatbot modal -->
{% include "candidates/partials/chatbot_modal.html" %}
{% endblock %}

{% block extra_js %}
{% load static %}
<script src="{% static 'candidates/chatbot.js' %}"></script>
{% endblock %}
```

- [ ] **7.2: Create candidate_list.html partial**

Create `candidates/templates/candidates/partials/candidate_list.html`:

```html
<div class="px-4 py-3 space-y-2">
  {% for c in candidates %}
    {% include "candidates/partials/candidate_card.html" with candidate=c %}
  {% empty %}
    <div class="text-center py-16 text-gray-400">
      <svg class="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
      </svg>
      <p class="text-[14px]">검색 결과가 없습니다</p>
      <p class="text-[13px] mt-1">다른 조건으로 검색해보세요</p>
    </div>
  {% endfor %}

  {% if has_more %}
  <div hx-get="/candidates/?page={{ page|add:1 }}{% if active_category %}&category={{ active_category }}{% endif %}"
       hx-target="this"
       hx-swap="outerHTML"
       hx-trigger="revealed"
       class="py-4 text-center">
    <span class="text-gray-400 text-[13px]">더 불러오는 중...</span>
  </div>
  {% endif %}
</div>
```

- [ ] **7.3: Create candidate_card.html**

Create `candidates/templates/candidates/partials/candidate_card.html`:

```html
<a href="/candidates/{{ candidate.pk }}/"
   hx-get="/candidates/{{ candidate.pk }}/"
   hx-target="#main-content"
   hx-push-url="true"
   class="block bg-white rounded-lg border border-gray-200 p-4 hover:border-primary/30 hover:shadow-sm transition">
  <div class="flex items-start justify-between">
    <div class="min-w-0 flex-1">
      <h3 class="text-[16px] font-semibold text-gray-900 truncate">{{ candidate.name }}</h3>
      <p class="text-[13px] text-gray-500 mt-0.5 truncate">
        {% if candidate.current_company %}{{ candidate.current_company }}{% endif %}
        {% if candidate.current_position %} · {{ candidate.current_position }}{% endif %}
      </p>
    </div>
    <div class="flex items-center gap-2 ml-3 shrink-0">
      {% if candidate.total_experience_years %}
      <span class="text-[12px] font-medium text-primary bg-primary-light px-2 py-0.5 rounded-full">
        {{ candidate.total_experience_years }}년
      </span>
      {% endif %}
    </div>
  </div>
  <div class="flex items-center gap-2 mt-2">
    {% if candidate.primary_category %}
    <span class="text-[11px] text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
      {{ candidate.primary_category.name }}
    </span>
    {% endif %}
    {% for edu in candidate.educations.all|slice:":1" %}
    <span class="text-[11px] text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
      {{ edu.institution }}
    </span>
    {% endfor %}
  </div>
</a>
```

- [ ] **7.4: Create search_status_bar.html**

Create `candidates/templates/candidates/partials/search_status_bar.html`:

```html
{% if last_turn %}
<div class="px-4 py-2 bg-primary-light border-b border-primary/10 cursor-pointer"
     onclick="toggleChatbot()">
  <p class="text-[13px] text-primary font-medium truncate">
    🔍 "{{ last_turn.user_text }}" — {{ last_turn.result_count }}명 찾음
  </p>
</div>
{% else %}
<div class="px-4 py-2 bg-gray-50 border-b border-gray-100">
  <p class="text-[13px] text-gray-400">전체 후보자 {{ total }}명</p>
</div>
{% endif %}
```

- [ ] **7.5: Commit**

```bash
mkdir -p candidates/templates/candidates/partials
git add candidates/templates/
git commit -m "feat: main search page templates (list, card, status bar)"
```

---

## Task 8: 프론트엔드 — 챗봇 모달 + JavaScript

**Files:**
- Create: `candidates/templates/candidates/partials/chatbot_modal.html`
- Create: `candidates/templates/candidates/partials/chat_messages.html`
- Create: `candidates/static/candidates/chatbot.js`

- [ ] **8.1: Create chatbot_modal.html**

Create `candidates/templates/candidates/partials/chatbot_modal.html`:

```html
<!-- Chatbot overlay -->
<div id="chatbot-overlay"
     class="fixed inset-0 bg-black/30 z-40 hidden"
     onclick="toggleChatbot()"></div>

<!-- Chatbot modal -->
<div id="chatbot-modal"
     class="fixed z-50 hidden
            bottom-0 left-0 right-0 h-[85vh] rounded-t-2xl
            lg:bottom-6 lg:right-6 lg:left-auto lg:top-auto lg:w-[380px] lg:h-[520px] lg:rounded-2xl
            bg-white shadow-2xl flex flex-col"
     role="dialog"
     aria-modal="true"
     aria-label="AI 검색">

  <!-- Header -->
  <div class="flex items-center justify-between px-4 py-3 border-b border-gray-100">
    <h2 class="text-[15px] font-semibold text-gray-900">synco AI 검색</h2>
    <button onclick="toggleChatbot()" class="text-gray-400 hover:text-gray-600 p-1" aria-label="닫기">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4"/>
      </svg>
    </button>
  </div>

  <!-- Drag handle (mobile) -->
  <div class="lg:hidden flex justify-center py-1">
    <div class="w-10 h-1 bg-gray-300 rounded-full"></div>
  </div>

  <!-- Messages area -->
  <div id="chat-messages" class="flex-1 overflow-y-auto px-4 py-3 space-y-3">
    <!-- Welcome message -->
    <div class="flex gap-2">
      <div class="bg-gray-100 rounded-2xl rounded-tl-sm px-3 py-2 max-w-[80%]">
        <p class="text-[14px] text-gray-900">안녕하세요! 어떤 후보자를 찾으시나요?</p>
      </div>
    </div>
  </div>

  <!-- Input bar -->
  <div class="border-t border-gray-100 px-3 py-3 safe-area-pb">
    <div class="flex items-center gap-2">
      <!-- Mic button -->
      <button id="mic-btn"
              onclick="toggleRecording()"
              class="w-10 h-10 flex items-center justify-center rounded-full bg-primary text-white hover:bg-primary-dark transition shrink-0"
              aria-label="음성 검색">
        <svg id="mic-icon" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M19 11a7 7 0 01-14 0m14 0a7 7 0 00-14 0m14 0v1a7 7 0 01-14 0v-1m7 8v4m-4 0h8M12 1a3 3 0 00-3 3v7a3 3 0 006 0V4a3 3 0 00-3-3z"/>
        </svg>
        <svg id="mic-recording-icon" class="w-5 h-5 hidden" fill="currentColor" viewBox="0 0 24 24">
          <rect x="6" y="6" width="12" height="12" rx="2"/>
        </svg>
        <span id="mic-spinner" class="hidden btn-spinner"></span>
      </button>

      <!-- Text input -->
      <input id="chat-input"
             type="text"
             placeholder="텍스트로 입력하세요..."
             class="flex-1 border border-gray-200 rounded-full px-4 py-2 text-[14px]
                    focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/30"
             onkeydown="if(event.key==='Enter')sendMessage()">

      <!-- Send button -->
      <button onclick="sendMessage()"
              class="w-10 h-10 flex items-center justify-center rounded-full text-primary hover:bg-primary-light transition shrink-0"
              aria-label="전송">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19V5m0 0l-7 7m7-7l7 7"/>
        </svg>
      </button>
    </div>
  </div>
</div>
```

- [ ] **8.2: Create chat_messages.html partial**

Create `candidates/templates/candidates/partials/chat_messages.html`:

```html
<!-- Welcome message -->
<div class="flex gap-2">
  <div class="bg-gray-100 rounded-2xl rounded-tl-sm px-3 py-2 max-w-[80%]">
    <p class="text-[14px] text-gray-900">안녕하세요! 어떤 후보자를 찾으시나요?</p>
  </div>
</div>

{% for turn in turns %}
  <!-- User message -->
  <div class="flex justify-end">
    <div class="bg-primary text-white rounded-2xl rounded-tr-sm px-3 py-2 max-w-[80%]">
      <p class="text-[14px]">{{ turn.user_text }}
        {% if turn.input_type == "voice" %}<span class="text-[11px] opacity-70"> 🎤</span>{% endif %}
      </p>
    </div>
  </div>

  <!-- AI response -->
  <div class="flex gap-2">
    <div class="bg-gray-100 rounded-2xl rounded-tl-sm px-3 py-2 max-w-[80%]">
      <p class="text-[14px] text-gray-900">{{ turn.ai_response }}</p>
    </div>
  </div>
{% endfor %}
```

- [ ] **8.3: Create chatbot.js**

Create `candidates/static/candidates/chatbot.js`:

```javascript
/* synco chatbot — voice + text search */
(function () {
  "use strict";

  let sessionId = sessionStorage.getItem("synco_session_id") || null;
  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;

  /* ── Modal toggle ──────────────────────────── */
  window.toggleChatbot = function () {
    const modal = document.getElementById("chatbot-modal");
    const overlay = document.getElementById("chatbot-overlay");
    const toggle = document.getElementById("chatbot-toggle");
    const isOpen = !modal.classList.contains("hidden");

    if (isOpen) {
      modal.classList.add("hidden");
      overlay.classList.add("hidden");
      toggle.classList.remove("hidden");
      refreshCandidateList();
    } else {
      modal.classList.remove("hidden");
      overlay.classList.remove("hidden");
      toggle.classList.add("hidden");
      document.getElementById("chat-input").focus();
      scrollChat();
    }
  };

  /* ── Send text message ─────────────────────── */
  window.sendMessage = function () {
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    if (!text) return;

    input.value = "";
    appendUserMessage(text);
    appendThinking();
    doSearch(text, "text");
  };

  /* ── Voice recording ───────────────────────── */
  window.toggleRecording = function () {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  function startRecording() {
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then(function (stream) {
        audioChunks = [];
        mediaRecorder = new MediaRecorder(stream);
        mediaRecorder.ondataavailable = function (e) {
          audioChunks.push(e.data);
        };
        mediaRecorder.onstop = function () {
          stream.getTracks().forEach(function (t) { t.stop(); });
          handleRecordingComplete();
        };
        mediaRecorder.start();
        isRecording = true;
        setMicState("recording");
      })
      .catch(function () {
        showToast("마이크 권한을 허용해주세요");
      });
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.stop();
    }
    isRecording = false;
  }

  function handleRecordingComplete() {
    setMicState("processing");
    var blob = new Blob(audioChunks, { type: "audio/webm" });
    var formData = new FormData();
    formData.append("audio", blob, "voice.webm");

    fetch("/candidates/voice/", {
      method: "POST",
      headers: { "X-CSRFToken": getCSRF() },
      body: formData,
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        setMicState("idle");
        if (data.error) {
          showToast(data.error);
          return;
        }
        appendUserMessage(data.text, true);
        appendThinking();
        doSearch(data.text, "voice");
      })
      .catch(function () {
        setMicState("idle");
        showToast("음성 인식에 실패했습니다. 텍스트로 입력해주세요.");
      });
  }

  /* ── Search API call ───────────────────────── */
  function doSearch(text, inputType) {
    fetch("/candidates/search/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRF(),
      },
      body: JSON.stringify({
        message: text,
        session_id: sessionId,
        input_type: inputType,
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        removeThinking();
        if (data.error) {
          appendAIMessage(data.error);
          return;
        }
        sessionId = data.session_id;
        sessionStorage.setItem("synco_session_id", sessionId);
        appendAIMessage(data.ai_message);
        updateStatusBar(text, data.result_count);
      })
      .catch(function () {
        removeThinking();
        appendAIMessage("검색 중 오류가 발생했습니다.");
      });
  }

  /* ── Chat UI helpers ───────────────────────── */
  function appendUserMessage(text, isVoice) {
    var container = document.getElementById("chat-messages");
    var div = document.createElement("div");
    div.className = "flex justify-end";
    div.innerHTML =
      '<div class="bg-primary text-white rounded-2xl rounded-tr-sm px-3 py-2 max-w-[80%]">' +
      '<p class="text-[14px]">' + escapeHtml(text) +
      (isVoice ? ' <span class="text-[11px] opacity-70">🎤</span>' : "") +
      "</p></div>";
    container.appendChild(div);
    scrollChat();
  }

  function appendAIMessage(text) {
    var container = document.getElementById("chat-messages");
    var div = document.createElement("div");
    div.className = "flex gap-2";
    div.innerHTML =
      '<div class="bg-gray-100 rounded-2xl rounded-tl-sm px-3 py-2 max-w-[80%]">' +
      '<p class="text-[14px] text-gray-900">' + escapeHtml(text) + "</p></div>";
    container.appendChild(div);
    scrollChat();
  }

  function appendThinking() {
    var container = document.getElementById("chat-messages");
    var div = document.createElement("div");
    div.id = "thinking-indicator";
    div.className = "flex gap-2";
    div.innerHTML =
      '<div class="bg-gray-100 rounded-2xl rounded-tl-sm px-3 py-2">' +
      '<p class="text-[14px] text-gray-400">생각 중' +
      '<span class="inline-flex ml-1"><span class="animate-bounce" style="animation-delay:0ms">.</span>' +
      '<span class="animate-bounce" style="animation-delay:150ms">.</span>' +
      '<span class="animate-bounce" style="animation-delay:300ms">.</span></span></p></div>';
    container.appendChild(div);
    scrollChat();
  }

  function removeThinking() {
    var el = document.getElementById("thinking-indicator");
    if (el) el.remove();
  }

  function scrollChat() {
    var container = document.getElementById("chat-messages");
    container.scrollTop = container.scrollHeight;
  }

  /* ── Mic button states ─────────────────────── */
  function setMicState(state) {
    var btn = document.getElementById("mic-btn");
    var icon = document.getElementById("mic-icon");
    var recIcon = document.getElementById("mic-recording-icon");
    var spinner = document.getElementById("mic-spinner");

    icon.classList.add("hidden");
    recIcon.classList.add("hidden");
    spinner.classList.add("hidden");

    if (state === "idle") {
      btn.className = btn.className.replace(/bg-red-500|bg-gray-400/g, "bg-primary");
      icon.classList.remove("hidden");
    } else if (state === "recording") {
      btn.className = btn.className.replace(/bg-primary|bg-gray-400/g, "bg-red-500");
      recIcon.classList.remove("hidden");
    } else if (state === "processing") {
      btn.className = btn.className.replace(/bg-primary|bg-red-500/g, "bg-gray-400");
      spinner.classList.remove("hidden");
    }
  }

  /* ── Refresh candidate list ────────────────── */
  function refreshCandidateList() {
    var url = "/candidates/";
    if (sessionId) url += "?session_id=" + sessionId;
    htmx.ajax("GET", url, { target: "#candidate-list", swap: "innerHTML" });
  }

  function updateStatusBar(query, count) {
    var bar = document.getElementById("search-status-bar");
    if (bar) {
      bar.innerHTML =
        '<div class="px-4 py-2 bg-primary-light border-b border-primary/10 cursor-pointer" onclick="toggleChatbot()">' +
        '<p class="text-[13px] text-primary font-medium truncate">🔍 "' +
        escapeHtml(query) + '" — ' + count + "명 찾음</p></div>";
    }
  }

  /* ── Toast ─────────────────────────────────── */
  function showToast(msg) {
    var container = document.getElementById("toast-container");
    if (!container) return;
    var div = document.createElement("div");
    div.className = "bg-gray-800 text-white text-[13px] px-4 py-2 rounded-lg shadow-lg";
    div.textContent = msg;
    container.appendChild(div);
    setTimeout(function () { div.remove(); }, 3000);
  }

  /* ── Util ──────────────────────────────────── */
  function getCSRF() {
    var el = document.querySelector("[name=csrfmiddlewaretoken]");
    if (el) return el.value;
    var cookie = document.cookie.match(/csrftoken=([^;]+)/);
    return cookie ? cookie[1] : "";
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  /* ── ESC to close ──────────────────────────── */
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      var modal = document.getElementById("chatbot-modal");
      if (modal && !modal.classList.contains("hidden")) {
        toggleChatbot();
      }
    }
  });
})();
```

- [ ] **8.4: Create static directory**

```bash
mkdir -p candidates/static/candidates
```

- [ ] **8.5: Commit**

```bash
git add candidates/templates/candidates/partials/chatbot_modal.html candidates/templates/candidates/partials/chat_messages.html candidates/static/
git commit -m "feat: chatbot modal + voice recording + search JS"
```

---

## Task 9: 프론트엔드 — 후보자 상세 페이지

**Files:**
- Create: `candidates/templates/candidates/detail.html`
- Create: `candidates/templates/candidates/partials/candidate_detail_content.html`

- [ ] **9.1: Create detail.html (full page)**

Create `candidates/templates/candidates/detail.html`:

```html
{% extends "common/base.html" %}

{% block title %}{{ candidate.name }} — synco{% endblock %}

{% block content %}
{% include "candidates/partials/candidate_detail_content.html" %}

<!-- Floating chatbot button (on detail page too) -->
<button id="chatbot-toggle"
        onclick="toggleChatbot()"
        class="fixed bottom-20 right-4 lg:bottom-6 lg:right-6 w-14 h-14 lg:w-[60px] lg:h-[60px]
               bg-primary text-white rounded-full shadow-lg hover:bg-primary-dark
               flex items-center justify-center transition z-40"
        aria-label="AI 검색 열기">
  <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>
  </svg>
</button>

{% include "candidates/partials/chatbot_modal.html" %}
{% endblock %}

{% block extra_js %}
{% load static %}
<script src="{% static 'candidates/chatbot.js' %}"></script>
{% endblock %}
```

- [ ] **9.2: Create candidate_detail_content.html**

Create `candidates/templates/candidates/partials/candidate_detail_content.html`:

```html
<div class="px-4 py-4">
  <!-- Back button + name -->
  <div class="flex items-center gap-3 mb-4">
    <a href="/candidates/"
       hx-get="/candidates/"
       hx-target="#main-content"
       hx-push-url="true"
       class="text-gray-400 hover:text-gray-600">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
      </svg>
    </a>
    <h1 class="text-heading text-gray-900">{{ candidate.name }}</h1>
  </div>

  <!-- Basic info -->
  <section class="bg-white rounded-lg border border-gray-200 p-4 mb-3">
    <h2 class="text-[13px] font-medium text-gray-400 uppercase tracking-wider mb-3">기본 정보</h2>
    <div class="space-y-2 text-[14px]">
      {% if candidate.birth_year %}<p><span class="text-gray-500">생년:</span> {{ candidate.birth_year }}</p>{% endif %}
      {% if candidate.primary_category %}<p><span class="text-gray-500">카테고리:</span> {{ candidate.primary_category.name }}</p>{% endif %}
      {% if candidate.current_company %}<p><span class="text-gray-500">현재:</span> {{ candidate.current_company }} {{ candidate.current_position }}</p>{% endif %}
      {% if candidate.total_experience_years %}<p><span class="text-gray-500">총 경력:</span> {{ candidate.total_experience_years }}년</p>{% endif %}
      {% if candidate.email %}<p><span class="text-gray-500">이메일:</span> {{ candidate.email }}</p>{% endif %}
      {% if candidate.phone %}<p><span class="text-gray-500">연락처:</span> {{ candidate.phone }}</p>{% endif %}
    </div>
  </section>

  <!-- Career timeline -->
  {% if careers %}
  <section class="bg-white rounded-lg border border-gray-200 p-4 mb-3">
    <h2 class="text-[13px] font-medium text-gray-400 uppercase tracking-wider mb-3">경력</h2>
    <div class="space-y-3">
      {% for career in careers %}
      <div class="flex gap-3">
        <div class="flex flex-col items-center">
          <div class="w-2.5 h-2.5 rounded-full {% if career.is_current %}bg-primary{% else %}bg-gray-300{% endif %}"></div>
          {% if not forloop.last %}<div class="w-0.5 flex-1 bg-gray-200 mt-1"></div>{% endif %}
        </div>
        <div class="pb-3 flex-1 min-w-0">
          <div class="flex items-baseline gap-2">
            <span class="text-[14px] font-medium text-gray-900">{{ career.company }}</span>
            {% if career.is_current %}<span class="text-[11px] text-primary font-medium">현직</span>{% endif %}
          </div>
          <p class="text-[13px] text-gray-500">{{ career.position }}{% if career.department %} · {{ career.department }}{% endif %}</p>
          <p class="text-[12px] text-gray-400">{{ career.start_date }} — {{ career.end_date|default:"현재" }}</p>
          {% if career.duties %}<p class="text-[13px] text-gray-600 mt-1">{{ career.duties|truncatewords:30 }}</p>{% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
  </section>
  {% endif %}

  <!-- Education -->
  {% if educations %}
  <section class="bg-white rounded-lg border border-gray-200 p-4 mb-3">
    <h2 class="text-[13px] font-medium text-gray-400 uppercase tracking-wider mb-3">학력</h2>
    <div class="space-y-2">
      {% for edu in educations %}
      <div class="text-[14px]">
        <span class="font-medium text-gray-900">{{ edu.institution }}</span>
        {% if edu.degree %}<span class="text-gray-500"> · {{ edu.degree }}</span>{% endif %}
        {% if edu.major %}<span class="text-gray-500"> · {{ edu.major }}</span>{% endif %}
        {% if edu.end_year %}<span class="text-[12px] text-gray-400 ml-1">{{ edu.end_year }}</span>{% endif %}
      </div>
      {% endfor %}
    </div>
  </section>
  {% endif %}

  <!-- Certifications + Language -->
  {% if certifications or language_skills %}
  <section class="bg-white rounded-lg border border-gray-200 p-4 mb-3">
    <h2 class="text-[13px] font-medium text-gray-400 uppercase tracking-wider mb-3">자격증 · 어학</h2>
    <div class="flex flex-wrap gap-2">
      {% for cert in certifications %}
      <span class="text-[12px] bg-gray-100 text-gray-700 px-2 py-1 rounded">{{ cert.name }}{% if cert.acquired_date %} ({{ cert.acquired_date }}){% endif %}</span>
      {% endfor %}
      {% for lang in language_skills %}
      <span class="text-[12px] bg-primary-light text-primary px-2 py-1 rounded">{{ lang.language }}{% if lang.test_name %} {{ lang.test_name }}{% endif %}{% if lang.score %} {{ lang.score }}{% endif %}</span>
      {% endfor %}
    </div>
  </section>
  {% endif %}

  <!-- Confidence score -->
  {% if candidate.confidence_score %}
  <section class="bg-white rounded-lg border border-gray-200 p-4 mb-3">
    <h2 class="text-[13px] font-medium text-gray-400 uppercase tracking-wider mb-3">파싱 신뢰도</h2>
    <div class="flex items-center gap-3">
      <div class="flex-1 bg-gray-200 rounded-full h-2">
        <div class="h-2 rounded-full {% if candidate.confidence_score >= 0.8 %}bg-green-500{% elif candidate.confidence_score >= 0.6 %}bg-yellow-500{% else %}bg-red-500{% endif %}"
             style="width: {{ candidate.confidence_score|floatformat:0 }}%"
             {% with pct=candidate.confidence_score|floatformat:0 %}
             style="width: calc({{ candidate.confidence_score }} * 100%)"
             {% endwith %}>
        </div>
      </div>
      <span class="text-[13px] font-medium text-gray-600">{{ candidate.confidence_score|floatformat:0 }}%</span>
    </div>
  </section>
  {% endif %}
</div>
```

- [ ] **9.3: Commit**

```bash
git add candidates/templates/candidates/detail.html candidates/templates/candidates/partials/candidate_detail_content.html
git commit -m "feat: candidate detail page with career timeline"
```

---

## Task 10: 통합 — 랜딩 페이지 변경 + CSRF + 최종 연결

**Files:**
- Modify: `main/urls.py` — 루트를 candidates로 변경
- Modify: `templates/common/base.html` — CSRF cookie 설정
- Modify: `main/settings.py` — CSRF_USE_SESSIONS 확인

- [ ] **10.1: Update root URL to point to candidates**

Edit `main/urls.py` to add root redirect:

```python
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", lambda r: redirect("/candidates/"), name="root"),
    path("candidates/", include("candidates.urls")),
    path("accounts/", include("accounts.urls")),
    path("contacts/", include("contacts.urls")),
    path("meetings/", include("meetings.urls")),
    path("intelligence/", include("intelligence.urls")),
]
```

Note: accounts.urls의 `path("")` 패턴이 있을 수 있으므로, candidates를 먼저 배치하고 accounts는 `accounts/` 프리픽스로 이동. 기존 accounts의 루트 URL 패턴이 있다면 수정 필요 — 확인 후 조정.

- [ ] **10.2: Ensure CSRF cookie is available for JS fetch**

Add to `main/settings.py`:

```python
# CSRF — make token available to JS via cookie
CSRF_COOKIE_HTTPONLY = False
```

- [ ] **10.3: Run full test suite**

```bash
uv run pytest -v
```

- [ ] **10.4: Run dev server and manual test**

```bash
uv run python manage.py runserver 0.0.0.0:8000
```

Test at `http://49.247.46.171:8000/candidates/`:
1. 후보자 리스트 표시
2. 카테고리 탭 필터링
3. 후보자 카드 클릭 → 상세 페이지
4. 플로팅 버튼 → 챗봇 모달 열기/닫기
5. 텍스트 검색 "회계 10년차" → 결과 확인
6. 음성 검색 (마이크 → Whisper → 결과)

- [ ] **10.5: Commit**

```bash
git add main/urls.py main/settings.py
git commit -m "feat: wire up Phase 2 — root redirect + CSRF config"
```

---

## Task 11: 전체 테스트 + 린트

- [ ] **11.1: Run full test suite**

```bash
uv run pytest -v
```

Fix any failures.

- [ ] **11.2: Run linter**

```bash
uv run ruff check .
uv run ruff format .
```

- [ ] **11.3: Final commit**

```bash
git add -A
git commit -m "chore: lint + format Phase 2 code"
```
