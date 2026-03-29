# 임베딩 기반 관계 분석 설계서

**Date:** 2026-03-29
**Status:** Draft v7 (v6 + Feel Lucky exemplar 기반 이유 생성 규칙 명확화)
**Replaces:** `analyze_contact_relationship()` 모놀리식 LLM 분석

---

## 1. 문제

현재 `analyze_contact_relationship()`는 연락처 1건당 Claude CLI 1회 호출(30~120초).
임포트 후 AnalysisJob을 수동 실행하면 100건 × LLM = 200분 대기, ~$5 비용.

함수 내부에 스코어링 + 감정분석 + 할일추출 + 인사이트생성 + DB저장이 전부 묶여 있어서,
감정분석만 필요한 상황에서도 전체가 실행됨.

---

## 2. 설계 원칙

### 2.1 사용자 여정 연속성

사용자의 행동 → 즉각적 피드백 → 이후 어디로 가든 결과가 반영되어 있어야 한다.

```
엑셀 업로드
  ↓ 즉각 피드백
  "100건 등록되었습니다. 골드 12명, 주의 필요 8명"
  ↓ 사용자가 대시보드 탭
  방금 임포트한 데이터 기반의 대시보드 (오늘의 업무, Feel Lucky, 티어 분포)
  ↓ 사용자가 연락처 탭
  티어 뱃지 + 감정 아이콘이 이미 붙어있는 목록
  ↓ 사용자가 특정 연락처 탭
  유사 고객이 준비된 상세 화면
```

임포트 완료 시점에 **스코어링은 즉시 완료**, 임베딩 + 감정분류 + 할일감지는 **백그라운드에서 점진적으로 완성**된다.
사용자가 이후 어느 화면으로 이동하든 기본 결과(티어 뱃지, 스코어)는 즉시 보이며,
분석 진행 중인 항목은 "분석 중" skeleton으로 표시한다 — 빈 화면이나 "결과 없음"과는 구분되어야 한다.

### 2.2 모듈 분리 + 자동 오케스트레이션

- 각 기능은 하나의 일만 하는 독립 함수로 분리
- 사용자에게 "분석 실행" 버튼을 누르게 하지 않음
- 시스템이 맥락(어떤 화면, 어떤 데이터 상태)을 보고 필요한 함수만 자동 조합

### 2.3 비용 효율

- 저렴한 처리(임베딩 $0.001, 감정분류 0ms, 스코어 <1ms): 적극 선행 실행
- 비싼 처리(LLM $0.02, 10~30초): 해당 화면 진입 시 자동 실행 + 캐시

### 2.4 Graceful Degradation

외부 API(Gemini) 장애 시에도 CRM 기본 기능은 반드시 작동해야 한다.

- **연락처 저장은 무조건 성공.** 분석 파이프라인 실패가 임포트 실패로 이어지면 안 됨
- 분석 실패 시: 기존 Python 규칙 기반 스코어만 계산, 임베딩/감정/할일은 다음 기회에 처리
- 사용자에게 에러를 노출하지 않되, 분석 결과가 없는 항목은 "미분석" 상태로 표시

### 2.5 읽기 가이드 (에이전트별 참조 범위)

Orchestrator가 각 서브에이전트를 디스패치할 때, 설계서 전문이 아닌 해당 역할에 필요한 섹션만 입력으로 전달한다.

| 서브에이전트 | 입력 섹션 | 참고 섹션 |
|-------------|-----------|-----------|
| **Engineer** | 1-8, 11, 13(Phase 1-4), 15.1 | 12(비용) |
| **Code Critic** | 15.1 + 해당 구현 섹션(3-8, 11) | — |
| **UX** | 1-2, 6.6(오케스트레이션 요약), 10, 13(Phase 5), 15.2 | — |
| **UX Critic** | 15.2 + 해당 구현 섹션(10) | — |

### 2.6 통과 조건 요약

상세 체크리스트는 섹션 15. 여기서는 핵심만 요약.

- **Code:** pytest 통과, ruff 클린, migration reversible, Gemini 장애 시 연락처 저장 정상, 감정/할일에 LLM 호출 없음
- **UX:** HTMX 네비게이션 패턴 준수, 임베딩 없으면 유사 고객 숨김, 모바일/데스크탑 레이아웃, 한국어 존대말

### 2.7 설정값 테이블

| 값 | 용도 | 근거 |
|----|------|------|
| `3072` | 임베딩 차원 수 | gemini-embedding-001 고정 |
| `100건` | Gemini 배치 제한 / 청킹 단위 | API 제한 |
| `2000자` | `build_contact_text` 최대 길이 | Gemini 8192토큰 제한의 안전 마진 |
| `0.05` | 할일 감지 margin threshold | 실측 8/8 정확도 (섹션 8) |
| `0.01` | 감정분류 neutral fallback margin | TBD — 실측 검증 필요 |
| `24시간` | `ensure_deep_analysis` 캐시 유효 기간 | 일 1회 분석 빈도 가정 |
| `80자` | Task title truncate 길이 | UI 1줄 표시 기준 |
| `5건` | 대시보드 할일 최대 표시 | 모바일 스크롤 최적화 |
| `20건` | `ensure_sentiments_and_tasks` 대상 건수 상한 | 동기 호출 페이지 로드 지연 방지 (Gemini 장애 복구 시 대량 미분류 건 보호) |
| `3초` | `ensure_embedding` Gemini API 타임아웃 | 동기 호출 페이지 로드 지연 방지 |
| `3초` | `ensure_sentiments_and_tasks` Gemini API 타임아웃 | ensure_embedding과 동일 기준 |
| `3초` | HTMX 폴링 간격 (`every 3s`) | 기존 코드베이스 패턴과 통일 |
| `5분` | 폴링 완료 판정 타임아웃 | ImportBatch 생성 후 5분 경과 시 완료 간주 (스레드 사망 대응) |
| `7일` | FortunateInsight dismiss 만료 기간 | 만료 후 재추천 허용 (임베딩 변경 시 새 이유 반영) |

---

## 3. 인프라 변경

### 3.1 pgvector

PostgreSQL 16에 pgvector 확장 설치.

**개발 DB (docker-compose):**
```yaml
image: pgvector/pgvector:pg16
```

**운영 DB (49.247.45.243):**
`pgvector/pgvector:pg16` 이미지로 교체. 동일 major 버전(PG16)이므로 데이터 볼륨(`/mnt/synco-pgdata/`) 호환.

**운영 적용 절차:**
1. 운영 DB pg_dump 백업
2. 테스트 환경에서 이미지 교체 + 볼륨 마운트 검증
3. 검증 후 운영 적용
4. `CREATE EXTENSION IF NOT EXISTS vector;` 실행

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 3.2 Python 의존성

```toml
# pyproject.toml에 추가
"google-genai>=1.0.0",
"pgvector>=0.4.0",
# numpy는 pgvector 의존성으로 자동 설치됨
```

### 3.3 환경변수

`.env`에 `GEMINI_API_KEY` 이미 존재. `.env.example`에 항목 추가:
```
# AI - Gemini Embedding
GEMINI_API_KEY=
```

---

## 4. 데이터 모델 변경

### 4.1 ContactEmbedding (신규 모델)

Contact 모델에 벡터를 직접 넣지 않고 별도 테이블로 분리.
이유: 임베딩은 재생성될 수 있고, Contact 쿼리 성능에 영향 주지 않도록.

```python
from pgvector.django import VectorField

class ContactEmbedding(BaseModel):
    contact = models.OneToOneField(Contact, on_delete=models.CASCADE, related_name="embedding")
    vector = VectorField(dimensions=3072)         # gemini-embedding-001 = 3072차원
    source_text = models.TextField()               # 임베딩 생성에 사용된 원문
    source_hash = models.CharField(max_length=64)  # SHA-256 해시 (변경 감지용)
    model_version = models.CharField(max_length=50, default="gemini-embedding-001")

    class Meta:
        db_table = "contact_embeddings"
```

**인덱스:** 1000건 이하 brute-force. 1000건 초과 시 hnsw 인덱스 추가 migration으로 대응.

### 4.2 ImportBatch (신규 모델)

임포트 단위로 분석 진행 상태를 추적하는 경량 job record.
FC 전체가 아닌 **이번 임포트 건만** 폴링 대상으로 좁히기 위해 도입.

```python
class ImportBatch(BaseModel):
    fc = models.ForeignKey(User, on_delete=models.CASCADE, related_name="import_batches")
    contact_count = models.PositiveIntegerField()          # 이번 임포트의 연락처 수
    interaction_count = models.PositiveIntegerField()      # 이번 임포트의 인터랙션 수
    embedding_done = models.BooleanField(default=False)    # 연락처 임베딩 완료
    sentiment_done = models.BooleanField(default=False)    # 감정 분류 완료
    task_done = models.BooleanField(default=False)         # 할일 감지 완료
    error_message = models.TextField(blank=True, default="")  # 실패 시 에러 요약

    class Meta:
        db_table = "import_batches"
        ordering = ["-created_at"]
```

**배치 귀속:** Interaction에 `import_batch` FK를 두어 "이번 임포트에서 생성된 인터랙션"을 정확히 집계한다.
Task는 `source_interactions` M2M으로 Interaction에 연결한다. 동일 Task가 여러 배치에서 감지될 수 있으므로
FK(1:1)가 아닌 M2M이어야 배치별 집계(`Task.objects.filter(source_interactions__import_batch=batch)`)가 정확하다.
Contact는 여러 임포트에 걸쳐 존재할 수 있어 FK를 두지 않는다.

**할일 감지 완료 마커:** Interaction에 `task_checked = BooleanField(default=False)`를 추가한다.
`sentiment`는 값 자체가 처리 완료 마커 역할(`""` = 미처리)을 하지만, Task는 부재가 "할일 없음"과 "감지 미시도"를
구분할 수 없다. `task_checked`로 이 모호성을 해소한다.
- `task_checked=False`: 할일 감지 미시도 또는 임베딩 부분 실패 → 재시도 대상
- `task_checked=True`: 판별 로직이 실제로 수행됨 (결과가 Task 0건이어도 재시도 안 함)
- 배치 처리 시 임베딩이 None인 인터랙션은 `task_checked=False` 유지 (부분 실패 보호)

**상태 전이:**
```
생성 (임포트 직후)
  → embedding_done=True (embed_contacts_batch 완료)
  → sentiment_done=True (classify_sentiments_batch 완료)
  → task_done=True (detect_tasks_batch 완료)
  → is_complete (세 플래그 모두 True)
```

`is_complete` 프로퍼티:
```python
@property
def is_complete(self) -> bool:
    return self.embedding_done and self.sentiment_done and self.task_done
```

### 4.3 Task 모델 — `source_interaction` FK → M2M 변경

기존 `source_interaction = ForeignKey(Interaction)` (1:1)을 `source_interactions = ManyToManyField(Interaction)` (다:다)로 변경.

```python
# contacts/models.py — Task 모델 변경
# 삭제:
source_interaction = models.ForeignKey("Interaction", on_delete=models.SET_NULL, null=True, blank=True)

# 추가:
source_interactions = models.ManyToManyField("Interaction", blank=True, related_name="detected_tasks")
```

**이유:** `get_or_create(fc, contact, title)`로 Task 중복을 방지하되, 동일 Task가 여러 배치에서 감지될 때
각 배치의 Interaction을 모두 연결해야 배치별 집계(`Task.objects.filter(source_interactions__import_batch=batch)`)가 정확하다.
FK(1:1)에서는 최초 배치의 Interaction만 가리키므로, 이후 배치에서 재감지된 Task가 집계에서 누락된다.

**migration 주의:** M2M 변경은 중간 테이블 생성이므로, 기존 `source_interaction` FK 데이터를 M2M으로 마이그레이션하는
`RunPython` 단계가 필요하다 (reverse_func 포함).

**reverse_func 데이터 손실 정책:** M2M → FK 복원 시 `source_interactions.first()`만 FK로 복원하고 나머지 연결은 유실된다.
이는 의도된 손실이다 — rollback은 비상 시에만 사용하며, M2M 도입 후 쌓인 다중 연결은 FK 구조로 무손실 복원이 불가능하다.

### 4.4 Contact 모델 — 변경 없음

기존 `relationship_score`, `relationship_tier`, `closeness_score`, `business_urgency_score` 필드 그대로 사용.

---

## 5. 모듈 구조

### 5.1 파일 구조

모든 함수는 **하나의 일만** 수행. 파이프라인 호출자가 조합.

```
common/
  embedding.py          # Gemini API 래퍼

intelligence/
  services/
    __init__.py         # 기존 호환용 re-export (아래 목록)
    embedding.py        # embed_contact, embed_contacts_batch
    sentiment.py        # classify_sentiment, classify_sentiments_batch
    task_detect.py      # detect_task, detect_tasks_batch
    scoring.py          # calculate_relationship_score (기존 이동)
    similarity.py       # find_similar_contacts, find_contacts_like
    orchestration.py    # ensure_embedding, ensure_sentiments_and_tasks, ensure_deep_analysis
    deep_analysis.py    # generate_summary, generate_insights (LLM 온디맨드)
    briefing.py         # generate_dashboard_briefing (기존 이동)
    excel.py            # detect_header_and_map, classify_sheets (기존 이동)
```

### 5.2 `__init__.py` re-export 목록

기존 import 경로(`from intelligence.services import ...`) 호환:

```python
# intelligence/services/__init__.py
from .scoring import calculate_relationship_score
from .briefing import generate_dashboard_briefing
from .excel import detect_header_and_map, classify_sheets
from .sentiment import classify_sentiment, classify_sentiments_batch
from .task_detect import detect_task, detect_tasks_batch
from .embedding import embed_contact, embed_contacts_batch
from .similarity import find_similar_contacts, find_contacts_like
from .orchestration import ensure_embedding, ensure_sentiments_and_tasks, ensure_deep_analysis
```

### 5.3 각 함수 명세

**함수 계약 요약 (상세는 아래 각 함수 참조):**

| 함수 | 입력 | 출력 | 실패 시 | API |
|------|------|------|---------|-----|
| `get_embedding` | str | list[float] \| None | None | Gemini |
| `get_embeddings_batch` | list[str] | list[list[float] \| None] | 실패 인덱스 None | Gemini |
| `embed_contact` | Contact | ContactEmbedding \| None | None, 기존 유지 | Gemini |
| `embed_contacts_batch` | list[Contact] | list[ContactEmbedding] | 실패 건 스킵 | Gemini |
| `classify_sentiment` | str, embedding=None | "positive"/"neutral"/"negative" | "" | 없음(numpy) |
| `classify_sentiments_batch` | list[Interaction], embeddings=None | None (bulk_update) | 스킵 | 없음(numpy) |
| `detect_task` | Interaction, embedding=None | Task \| None | None | 없음(numpy) |
| `detect_tasks_batch` | list[Interaction], embeddings=None | list[Task] | 감지 건만 | 없음(numpy) |
| `calculate_relationship_score` | Contact | None (in-place) | — | 없음 |
| `find_similar_contacts` | Contact, n | list[(Contact, float)] | [] | 없음(pgvector) |
| `find_contacts_like` | tiers, fc, n | list[dict(contact, similarity, exemplar)] | [] | 없음(pgvector+numpy) |
| `ensure_embedding` | Contact | ContactEmbedding \| None | None | Gemini |
| `ensure_sentiments_and_tasks` | Contact | None | 스킵 | Gemini(조건부) + numpy |
| `ensure_deep_analysis` | Contact | RelationshipAnalysis \| None | stale 반환 | Claude |
| `generate_summary` | Contact | str | "" | Claude |
| `generate_insights` | Contact | list[dict] | [] | Claude |

#### `common/embedding.py` — Gemini API 래퍼

```python
from google import genai

_client = None  # lazy 초기화

def _get_client():
    """Gemini client를 lazy 초기화. import 시 API 호출 안 함."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client

def get_embedding(text: str) -> list[float] | None:
    """단일 텍스트 → 3072차원 벡터. Gemini API 1회 호출.
    실패 시 None 반환 (caller가 처리)."""

def get_embeddings_batch(texts: list[str]) -> list[list[float] | None]:
    """N개 텍스트 → N개 벡터.
    Gemini 배치 제한 = 100건. 100건 초과 시 내부에서 100건 단위로 청킹.
    부분 실패 시 실패한 인덱스는 None으로 채움.
    반환 리스트 길이는 항상 입력 texts 길이와 동일."""
```

#### `intelligence/services/embedding.py` — Contact 임베딩

```python
def build_contact_text(contact) -> str:
    """Contact 메타데이터 + 메모 + 최근 인터랙션을 하나의 텍스트로 조합.

    조합 순서:
    1. "{name} {company_name} {industry} {region} {revenue_range}"
    2. "메모: {memo[:200]}" (있는 경우)
    3. 최근 인터랙션 5건: "- {type}: {summary[:100]}" (있는 경우)

    최대 길이: 2000자 (초과 시 truncate). Gemini embedding 입력 제한 8192토큰 이내.
    빈 필드는 생략."""

def embed_contact(contact) -> ContactEmbedding | None:
    """1건 임베딩 생성/갱신.
    source_text의 SHA-256 해시를 source_hash와 비교, 동일하면 스킵.
    Gemini API 실패 시 None 반환, 기존 임베딩 유지."""

def embed_contacts_batch(contacts: list) -> list[ContactEmbedding]:
    """N건 배치 임베딩. 내부에서 100건 단위 청킹.
    개별 실패 건은 스킵하고 성공한 건만 반환.
    update_or_create로 기존 임베딩 갱신."""
```

#### `intelligence/services/sentiment.py` — 감정 분류

레퍼런스 벡터 정의 및 초기화 전략은 **섹션 7** 참조.

```python
def classify_sentiment(text: str, embedding: list[float] | None = None) -> str:
    """단일 텍스트 → "positive"/"neutral"/"negative".
    embedding이 주어지면 재사용, 없으면 내부에서 get_embedding(text) 호출.
    판정: margin ≤ 0.01이면 "neutral" fallback (설정값 테이블 2.7 참조).
    API 실패 시 빈 문자열 반환.

    주의: 호출자가 이미 get_embedding()을 시도하고 None을 받은 경우,
    embedding=None으로 넘기면 내부에서 동일 API를 재호출한다.
    이 경우 호출자가 classify_sentiment 자체를 스킵해야 한다 (6.5절 참조)."""

def classify_sentiments_batch(interactions: list[Interaction], embeddings: list[list[float]] | None = None) -> None:
    """N건 인터랙션의 감정 일괄 분류.
    embeddings가 주어지면 재사용, 없으면 get_embeddings_batch로 생성.
    레퍼런스와 cosine similarity 비교 → bulk_update.
    이미 sentiment가 있는 건은 스킵."""
```

#### `intelligence/services/task_detect.py` — 할일 감지

레퍼런스 벡터 정의 및 초기화 전략은 **섹션 7** 참조. 판별 로직 상세는 **섹션 8** 참조.

```python
def detect_task(interaction: Interaction, embedding: list[float] | None = None) -> Task | None:
    """단일 인터랙션 → 할일 감지.
    embedding이 주어지면 재사용, 없으면 내부에서 get_embedding 호출.
    max(task/followup/promise 유사도) - not_task 유사도 > 0.05 이면 Task 생성.
    Task 필드: title=summary[:80], source=AI_EXTRACTED, due_date=None.
    get_or_create로 중복 방지 (fc + contact + title 기준).
    생성/재사용 여부와 무관하게 source_interactions.add(interaction) 호출.
    → 동일 Task가 여러 배치에서 감지되어도 각 배치의 집계에 반영됨.

    처리 완료 후 interaction.task_checked=True 설정 + save(update_fields=["task_checked"]).
    Task 생성 여부와 무관하게 감지 로직이 실행되었으면 True로 마킹.
    → ensure_sentiments_and_tasks에서 재시도 대상 판별에 사용.

    주의: 호출자가 이미 get_embedding()을 시도하고 None을 받은 경우,
    embedding=None으로 넘기면 내부에서 동일 API를 재호출한다.
    이 경우 호출자가 detect_task 자체를 스킵해야 한다 (6.5절 참조).
    이때 task_checked는 False 유지 → 다음 기회에 재시도."""

def detect_tasks_batch(interactions: list[Interaction], embeddings: list[list[float]] | None = None) -> list[Task]:
    """N건 일괄 감지.
    embeddings가 주어지면 재사용, 없으면 get_embeddings_batch로 생성.
    레퍼런스 비교 → 감지 건만 Task 생성.
    각 Task에 source_interactions.add(interaction) 호출.

    task_checked 마킹 규칙:
    - 임베딩이 None이 아닌(= 판별 로직이 실제로 수행된) 인터랙션에만 task_checked=True.
    - 임베딩이 None인(= Gemini 부분 실패로 판별 불가) 인터랙션은 task_checked=False 유지.
    - bulk_update 대상은 전체가 아닌, 판별 수행 건만.
    (get_embeddings_batch는 부분 실패 시 해당 인덱스를 None으로 채움 — 섹션 5.3 참조)"""
```

#### `intelligence/services/scoring.py` — 관계 스코어

```python
def calculate_relationship_score(contact) -> None:
    """기존 Python 규칙 기반 스코어 계산. 코드 변경 없이 이동만."""
```

#### `intelligence/services/similarity.py` — 유사도 검색

```python
def find_similar_contacts(contact, n=5) -> list[tuple[Contact, float]]:
    """pgvector cosine distance 쿼리로 유사 연락처 검색.
    contact에 임베딩이 없으면 빈 리스트 반환.
    반환: [(Contact, similarity_score), ...] similarity_score는 0~1."""

def find_contacts_like(reference_tier="gold", target_tier="yellow", fc=None, n=10):
    """골드 고객 임베딩의 중심 벡터 계산 → target_tier 중 유사한 N건 반환.
    중심 벡터 계산 대상: 해당 티어 연락처 중 **임베딩이 있는 건만** 사용.
    (초기 배포/backfill 전에는 골드 전원에 임베딩이 없을 수 있음)
    fallback 체인:
      1. 골드 + 임베딩 있는 연락처 → 중심 벡터 계산
      2. 골드 0건 → green + 임베딩 있는 연락처로 fallback
      3. green도 0건 → 빈 리스트 반환

    반환: list[dict] — 각 항목:
      - contact: Contact 객체
      - similarity: float (0~1)
      - exemplar: Contact (레퍼런스 티어 중 이 후보와 가장 유사한 1건)
    exemplar 선택: 후보별로 레퍼런스 연락처 전원과 cosine similarity를 비교하여
    가장 높은 1건을 선택. Python 내 numpy 연산이므로 추가 API 호출 없음."""
```

#### `intelligence/services/orchestration.py` — ensure_* 헬퍼

```python
def ensure_embedding(contact) -> ContactEmbedding | None:
    """contact에 임베딩이 없으면 생성. 있으면 스킵.
    판단 기준: ContactEmbedding.objects.filter(contact=contact).exists()
    Gemini API 타임아웃 3초 적용.
    Gemini API 실패 또는 타임아웃 시 None 반환.
    호출 컨텍스트: HTMX lazy-load endpoint에서 호출되므로 메인 페이지 렌더와 무관."""

def ensure_sentiments_and_tasks(contact) -> None:
    """contact의 인터랙션 중 미분석 건을 찾아 감정분류 + 할일감지를 일괄 처리.

    대상 선정:
    - 감정분류 대상: sentiment=""인 인터랙션
    - 할일감지 대상: task_checked=False인 인터랙션
    - 임베딩 생성 대상: 위 두 집합의 합집합
      (감정분류와 할일감지 모두 인터랙션 임베딩을 공유하므로 1회만 생성)

    sentiment=""와 task_checked=False는 독립적으로 판별한다.
    - sentiment 성공 + task 실패: sentiment≠"", task_checked=False → 할일감지만 재시도
    - 둘 다 미처리: sentiment="", task_checked=False → 둘 다 재시도
    - 둘 다 완료: sentiment≠"", task_checked=True → 대상 아님

    임베딩 1회 생성 → classify_sentiments_batch + detect_tasks_batch에 주입.
    detect_tasks_batch가 임베딩 성공 건에 한해 task_checked=True bulk_update.
    (임베딩이 None인 건은 task_checked=False 유지 → 다음 기회에 재시도)

    ⚠️ 성능/복원력 계약:
    - 인터랙션 임베딩 생성은 Gemini API 호출이므로, 이 함수는 조건부로 외부 API에 의존한다.
    - 대상 건수 상한: 최대 20건만 처리. 초과분은 무시하고 다음 페이지 진입 시 재시도.
      (정상 흐름에서는 백그라운드에서 이미 처리되므로 잔여 건은 소량.
       Gemini 장애 복구 직후 대량 미분류 건이 쌓였을 때 페이지 로드 보호.)
    - Gemini API 타임아웃: ensure_embedding과 동일하게 3초 적용.
      타임아웃/실패 시 감정분류·할일감지 모두 스킵, 페이지 렌더링 정상 진행.
      (실패 시 task_checked는 False 유지 → 다음 페이지 진입 시 재시도)

    대상 0건이면 스킵. select_related로 N+1 방지."""

def ensure_deep_analysis(contact) -> RelationshipAnalysis | None:
    """contact의 최근 RelationshipAnalysis가 유효한지 확인, 없거나 만료면 LLM 실행.
    캐시 유효 기준:
      1. RelationshipAnalysis.created_at이 24시간 이내
      2. AND 분석 이후 새 인터랙션이 없음:
         - 인터랙션 0건 → 조건 2는 자동 충족 (새 인터랙션 없음과 동치)
         - 인터랙션 있음 → latest().created_at < analysis.created_at
         (주의: latest()는 인터랙션 0건 시 DoesNotExist를 raise하므로,
          반드시 exists() 체크 후 호출하거나 first()로 대체해야 함)
    만료 시: generate_summary + generate_insights 호출 → 새 RelationshipAnalysis 생성.
    LLM 실패 시 기존 분석(stale이라도) 반환. 기존 분석도 없으면 None."""
```

#### `intelligence/services/deep_analysis.py` — LLM 심층 분석 (온디맨드)

```python
def generate_summary(contact) -> str:
    """관계 요약 한 문단. LLM 1회. 타임아웃 60초.
    프롬프트: 현재 analyze_contact_relationship()의 "summary" 부분 분리.
    입력: contact 정보 + 최근 인터랙션 30건 + 미팅 10건 (현행과 동일).
    Claude CLI(call_claude_json) 사용 — Gemini가 아닌 기존 Claude 유지.
    실패 시 빈 문자열 반환."""

def generate_insights(contact) -> list[dict]:
    """유망 인사이트 추출. LLM 1회. 타임아웃 60초.
    [{"reason": "...", "type": "personal_event/promotion/business_opportunity"}]
    실패 시 빈 리스트 반환."""
```

**Claude vs Gemini 역할 분리:**
- **Gemini:** 임베딩 생성 전용 (embedding.py)
- **Claude:** 자연어 생성 전용 (deep_analysis.py, briefing.py, excel.py)
- `common/claude.py`는 유지. `common/embedding.py`가 추가됨.

---

## 6. 파이프라인 조합 — 자동 오케스트레이션

**설계 원칙:** 모듈은 잘게 쪼개되, 사용자에게 버튼을 누르게 하지 않는다.
시스템이 맥락(어떤 화면을 열었는가, 어떤 데이터가 있는가)을 보고
필요한 함수만 자동으로 조합 실행한다. 사용자는 완성된 결과만 본다.

### 6.1 엑셀 임포트 후 — 2단계 처리

연락처 저장(동기)과 분석(백그라운드)을 분리 (원칙 2.4 적용).

#### 6.1.1 백그라운드 스레드 안전 규칙 (필수)

프로토타입 단계에서는 스레드를 사용하되, 아래 규칙은 **전부 필수**:

| 규칙 | 이유 |
|------|------|
| `daemon=False` | daemon 스레드는 프로세스 종료 시 강제 kill → 부분 커밋 위험. 단, 배포 시 gunicorn worker 종료가 백그라운드 스레드 완료까지 지연될 수 있으므로 인지할 것 |
| 동기 저장 루프 완료 후 스레드 시작 | autocommit 모드에서 루프 종료 시점에 모든 데이터가 이미 커밋되어 있으므로 안전. 향후 명시적 `@transaction.atomic` 블록으로 임포트를 묶는 구현으로 변경하면 그때는 `transaction.on_commit()` 사용 |
| `try/finally: connection.close()` | 스레드별 DB 커넥션이 자동 반환되지 않음 → 커넥션 풀 고갈 |
| `logger.exception()` | "조용히 실패" = 사용자에게 안 보여줌이지 기록 안 남김이 아님 |

> **왜 `transaction.on_commit()`을 쓰지 않는가:**
> 현재 임포트는 행별 `create()` 반복(autocommit)이다. 전체를 `@transaction.atomic`으로 감싸면
> 99번째 건 에러 시 98건이 롤백되어 부분 성공이라는 장점을 잃는다.
> 이 기능은 "전부 아니면 전무"가 아니라 "가능한 만큼 저장"이 사용자 기대와 맞으므로,
> autocommit + 루프 완료 후 스레드 시작이 더 적합하다.

장기적으로는 Celery/Django-Q 등 태스크 큐로 전환. 스레드는 프로토타입 한정.

```python
# contacts/views.py — contact_import_confirm 완료 시

# === 동기 (즉시 완료, 실패 불가) ===
contacts = [created contacts]
new_interactions = [created interactions with memo]

# Python 스코어 계산 (<1ms/건, API 의존 없음)
for contact in all_fc_contacts:
    calculate_relationship_score(contact)

# === ImportBatch 생성 (동기) ===
batch = ImportBatch.objects.create(
    fc=request.user,
    contact_count=len(contacts),
    interaction_count=len(new_interactions),
)

# === 백그라운드 스레드 (분석 파이프라인) ===
# 실패해도 연락처 저장에 영향 없음
def _run_import_analysis(batch_id, contact_ids, interaction_ids):
    from django.db import connection
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    try:
        batch = ImportBatch.objects.get(id=batch_id)
        contacts = Contact.objects.filter(id__in=contact_ids)
        interactions = Interaction.objects.filter(id__in=interaction_ids)

        # Step 1: 배치 임베딩 (Gemini API, 100건 단위 청킹)
        embed_contacts_batch(contacts)
        batch.embedding_done = True
        batch.save(update_fields=["embedding_done"])

        # Step 2: 인터랙션 임베딩 1회 생성 → 감정분류 + 할일감지에 공유
        # (동일 텍스트에 대해 Gemini API를 2번 호출하지 않음)
        texts = [i.summary for i in interactions]
        interaction_embeddings = get_embeddings_batch(texts)

        # Step 3: 감정 분류 (임베딩 재사용)
        classify_sentiments_batch(interactions, embeddings=interaction_embeddings)
        batch.sentiment_done = True
        batch.save(update_fields=["sentiment_done"])

        # Step 4: 할일 감지 (임베딩 재사용)
        detect_tasks_batch(interactions, embeddings=interaction_embeddings)
        batch.task_done = True
        batch.save(update_fields=["task_done"])

        # Step 5: 스코어 재계산 (감정 반영)
        for contact in contacts:
            calculate_relationship_score(contact)
    except Exception:
        logger.exception("Import analysis pipeline failed for batch %s", batch_id)
        ImportBatch.objects.filter(id=batch_id).update(
            error_message=f"Pipeline failed: {traceback.format_exc()[:500]}"
        )
    finally:
        connection.close()

# 동기 저장 루프 완료 후 스레드 시작
# autocommit 모드이므로 이 시점에 모든 데이터가 이미 커밋됨
Thread(target=_run_import_analysis, args=(batch.id, contact_ids, interaction_ids), daemon=False).start()
```

#### 6.1.2 사용자 경험 — 즉시 결과 + 점진적 완성

사용자 경험은 2단계이며, **백그라운드 완료 시점은 보장되지 않는다.**
"3~5초 후 완료"는 희망 가정이 아니라, 미완료 시 UX가 별도 처리되어야 하는 조건.

1. **즉시**: "100건 등록되었습니다" + Python 기반 티어 뱃지 (스코어만) + "분석 준비 중" 상태 표시
2. **백그라운드 완료 시**: HTMX 폴링으로 감정 아이콘 + 할일 자동 추가 업데이트
   - 완료 전 다른 화면 이동 가능하되, 해당 화면에서도 미완료 상태를 명시 (10.2절 참조)

**Gemini API 장애 시:** 백그라운드 스레드가 실패 → `logger.exception()`으로 기록.
연락처/스코어는 정상. 다음 번 해당 연락처를 열 때 `ensure_embedding`이 재시도.

#### 6.1.3 임포트 분석 상태 폴링 endpoint

임포트 완료 화면에서 **이번 임포트 배치**의 분석 진행 상태를 HTMX 폴링으로 조회한다.
`batch_id`를 기준으로 폴링하므로 기존 연락처·연속 임포트·여러 탭과 무관하게 정확한 상태를 반환한다.

```python
# intelligence/views.py
@login_required
def import_analysis_status(request, batch_id):
    """HTMX 폴링 endpoint: 특정 ImportBatch의 분석 진행 상태 반환.

    반환 데이터:
    - batch_id: 이번 임포트 배치 ID
    - contact_count: 이번 임포트의 연락처 수
    - interaction_count: 이번 임포트의 인터랙션 수
    - embedding_done: 연락처 임베딩 완료 여부
    - sentiment_done: 감정 분류 완료 여부
    - task_done: 할일 감지 완료 여부
    - sentiment_counts: 이번 배치의 감정 분포 (Interaction.objects.filter(import_batch=batch) 기반)
    - tasks_detected: 이번 배치에서 감지된 할일 수 (Task.objects.filter(source_interactions__import_batch=batch) 기반, M2M)
    - is_complete: 세 단계 모두 완료 여부
    - error_message: 파이프라인 에러 시 메시지

    완료 판정:
    1. embedding_done AND sentiment_done AND task_done → 완료
    2. error_message가 비어있지 않음 → 에러로 완료 (부분 실패 포함)
    3. batch.created_at으로부터 5분 경과 → 타임아웃 완료 (안전장치)

    HTMX 응답:
    - 진행 중: partial HTML (단계별 진행 상태) + hx-trigger="every 3s" 유지
    - 완료: 최종 결과 partial HTML + 폴링 중단 (hx-trigger 제거)
    """
    batch = get_object_or_404(ImportBatch, pk=batch_id, fc=request.user)
```

**HTMX 패턴:** 기존 `analysis_progress.html`의 `hx-trigger="every 3s"` + `hx-swap="outerHTML"` 패턴 재사용.
완료 시 응답 HTML에서 `hx-trigger`를 제거하여 폴링 자동 중단.

**URL:** `intelligence/analysis/import-status/<uuid:batch_id>/` → `main/urls.py`에 추가

**임포트 완료 화면에서의 사용:**
```html
<!-- import_result.html -->
<div hx-get="{% url 'import_analysis_status' batch.id %}"
     hx-trigger="every 3s"
     hx-swap="outerHTML">
  {% include "intelligence/partials/analysis_progress.html" %}
</div>
```

### 6.2 대시보드 — 있는 데이터로 자동 구성

```python
# Feel Lucky 섹션 — 임베딩 있는 연락처 중 자동 추천
insights = find_contacts_like(reference_tier="gold", target_tier="yellow", fc=user)

# 오늘의 업무: Task 쿼리 (임포트에서 감지된 AI 할일 포함)
# 티어 분포: Contact 집계 (Python)
# AI 브리핑: generate_dashboard_briefing() (LLM 1회/일, 현행 유지)
#   - 임포트 직후라면 당일 캐시된 브리핑 무효화 → 새 데이터 반영 브리핑 생성
```

### 6.3 연락처 상세 — 기본 즉시 렌더 + AI 영역 lazy-load

기본 정보(메타데이터, 접점 타임라인, 미팅 이력)는 DB 조회만으로 즉시 렌더링.
AI 영역(유사 고객, 감정 보완, 할일 보완)은 별도 HTMX lazy-load endpoint로 분리.

6.4절 미팅 리포트와 동일한 패턴: 사용자는 페이지를 즉시 보고, AI 결과는 비동기로 채워진다.

```python
# contacts/views.py — contact_detail (즉시 렌더)
def contact_detail(request, pk):
    contact = get_object_or_404(Contact, pk=pk, fc=request.user)
    interactions = contact.interactions.order_by("-created_at")[:20]
    # DB 조회만. Gemini API 호출 없음. 즉시 렌더.
    return render(request, "contacts/partials/contact_detail_content.html", {
        "contact": contact,
        "interactions": interactions,
    })

# contacts/views.py — contact_ai_section (HTMX lazy-load)
def contact_ai_section(request, pk):
    """연락처 상세 내 AI 영역. hx-get으로 lazy-load.
    ensure_embedding → ensure_sentiments_and_tasks → find_similar 순차 실행.
    (ensure_embedding 완료 후에야 find_similar가 의미 있으므로 직렬이 맞음)
    전체 실패해도 빈 partial 반환 — 페이지 본문에 영향 없음."""
    contact = get_object_or_404(Contact, pk=pk, fc=request.user)

    # Step 1: 임베딩 없으면 생성 (Gemini API, 타임아웃 3초)
    ensure_embedding(contact)

    # Step 2: 감정 미분류 + 할일 미감지 보완 (Gemini API 조건부, 타임아웃 3초)
    ensure_sentiments_and_tasks(contact)

    # Step 3: 유사 고객 조회 (pgvector, <10ms, 임베딩 없으면 빈 리스트)
    similar = find_similar_contacts(contact, n=3)

    return render(request, "contacts/partials/contact_ai_section.html", {
        "contact": contact,
        "similar_contacts": similar,
    })
```

**HTMX 패턴:**
```html
<!-- contact_detail_content.html 내부 -->
<div hx-get="{% url 'contact_ai_section' contact.pk %}"
     hx-trigger="load"
     hx-swap="outerHTML">
  {% include "contacts/partials/contact_ai_skeleton.html" %}
</div>
```

**URL:** `contacts/<uuid:pk>/ai/` → `main/urls.py`에 추가

### 6.4 미팅 리포트 — 비동기 로딩

리포트 모달에서 LLM(15초)을 동기 대기하면 모바일 이탈률이 높다.
모달을 즉시 열고, AI 분석 부분만 HTMX lazy-load.

```python
# intelligence/views.py — contact_report
def contact_report(request, contact_pk):
    contact = get_object_or_404(Contact, pk=contact_pk, fc=request.user)

    # 기본 정보는 즉시 렌더링 (DB 조회만)
    analysis = RelationshipAnalysis.objects.filter(contact=contact, fc=request.user).first()
    # analysis가 있으면 캐시 사용, 없으면 빈 상태로 렌더

    return render(request, "intelligence/partials/contact_report_modal.html", {
        "contact": contact,
        "analysis": analysis,  # None일 수 있음
        "needs_analysis": analysis is None or _is_stale(analysis, contact),
    })

# 별도 HTMX endpoint: AI 분석 부분만
def contact_report_analysis(request, contact_pk):
    """모달 내부에서 hx-get으로 lazy-load. AI 분석 실행 후 partial 반환.
    인증: fc=request.user로 타인 연락처 접근 차단.
    HTMX 검증: 기존 코드베이스 패턴상 partial 전용 뷰에서 request.htmx
    체크를 하지 않음 (contact_report_modal 등 동일). 직접 URL 접근 시
    partial HTML만 반환되지만, 민감 데이터 노출이 아닌 레이아웃 불편이므로
    현행 패턴 유지. 필요 시 request.htmx 체크는 프로젝트 전체 미들웨어로 일괄 적용."""
    contact = get_object_or_404(Contact, pk=contact_pk, fc=request.user)
    analysis = ensure_deep_analysis(contact)
    return render(request, "intelligence/partials/report_analysis_section.html", {
        "analysis": analysis,
    })
```

**사용자 경험:**
1. 리포트 모달 즉시 열림 (기본 정보 + 인터랙션 이력)
2. AI 분석 섹션: 스켈레톤 UI → HTMX lazy-load → 15초 후 결과 교체
3. 캐시 있으면 (24시간 이내 + 새 인터랙션 없음) 즉시 표시

### 6.5 인터랙션 추가 시 — 자동 갱신

```python
# 새 인터랙션 저장 후

# 임베딩 1회 생성 → 감정분류 + 할일감지에 재사용 (중복 API 호출 방지)
embedding = get_embedding(interaction.summary)

# 임베딩 실패 시 감정분류/할일감지 스킵 (동일 API가 이미 실패했으므로 재호출 무의미)
# → sentiment=""·task_checked=False 유지 → ensure_sentiments_and_tasks에서 재시도
if embedding is not None:
    # 감정 분류 — 단건은 caller가 저장 (배치와 달리 bulk_update 안 함)
    sentiment = classify_sentiment(interaction.summary, embedding=embedding)
    if sentiment:
        interaction.sentiment = sentiment
        interaction.save(update_fields=["sentiment"])

    detect_task(interaction, embedding=embedding)  # 할일 감지 + task_checked=True 설정

calculate_relationship_score(contact)          # 스코어 재계산 (Python, 항상 성공)
embed_contact(contact)                         # 임베딩 갱신 (source_hash 비교, 변경 시만)
```

> **단건 vs 배치 저장 책임 차이:** `classify_sentiment(text) → str`은 순수 함수(반환만).
> `classify_sentiments_batch(interactions) → None`은 내부에서 `bulk_update`로 직접 저장.
> 단건 호출 시 반환값을 반드시 저장해야 한다.

Task 자동 생성 시 응답에 토스트 알림 포함:
"할일이 자동 감지되어 오늘의 업무에 추가되었습니다"

### 6.6 자동 오케스트레이션 정리

| 사용자 행동 | 시스템 자동 실행 | 사용자가 보는 것 |
|------------|----------------|----------------|
| 엑셀 임포트 | 동기: score / BG: embed+classify+detect | "100건 등록" + 티어 (즉시) + 감정/할일 (수초 후) |
| 대시보드 이동 | find_contacts_like + 집계 | 오늘의 업무(할일 반영) + Feel Lucky + 티어 분포 |
| 연락처 목록 | 없음 (이미 계산됨) | 스코어/감정 아이콘 |
| 연락처 상세 | 즉시 렌더 + AI 영역 HTMX lazy-load (ensure+find_similar) | 기본 정보 즉시 + 유사 고객/감정/할일 비동기 |
| 미팅 리포트 | 즉시 열림 + AI 부분 HTMX lazy-load | 기본 정보 즉시 + AI 분석 비동기 |
| 인터랙션 추가 | classify+detect+score+re-embed | 감정/스코어/할일 즉시 + 토스트 |

**원칙:** 저렴한 처리는 적극 선행. 비싼 처리(LLM)는 비동기 + 캐시. 실패해도 기본 기능 동작.

---

## 7. 레퍼런스 벡터 관리

감정 분류와 할일 감지가 모두 레퍼런스 벡터 패턴을 사용한다.

### 초기화 전략: Lazy + 파일 캐시

```python
# 서버 시작 시 Gemini API를 호출하지 않음 (import 시 API 호출 없음)
# 첫 사용 시 Gemini API 호출 → JSON 파일로 캐시
# 이후 서버 재시작 시 파일에서 로드 (API 호출 없음)
# API 장애 시 캐시 파일이 있으면 사용, 없으면 해당 기능 스킵

CACHE_DIR = ".cache/"
SENTIMENT_CACHE = ".cache/sentiment_refs.json"
TASK_CACHE = ".cache/task_refs.json"
```

**캐시 무효화:** 레퍼런스 문장을 코드에서 변경하면, 문장 해시 비교로 자동 감지하여 재생성.
기존 분류 결과는 영향 없음 (이미 저장된 sentiment/task는 유지).

### cosine similarity 계산

Python(numpy)에서 계산. 레퍼런스 벡터가 3~4개이므로 DB 쿼리 불필요.
`find_similar_contacts`만 pgvector DB-side cosine distance 사용.

### 감정 분류 레퍼런스

```python
SENTIMENT_REFS = {
    "positive": "고객이 적극적으로 관심을 보이며 계약을 논의하고 다음 미팅을 요청했다",
    "neutral": "일반적인 안부 통화를 했고 특별한 진전은 없었다",
    "negative": "고객이 명확하게 거절했고 더 이상 연락을 원하지 않는다고 했다",
}
```

### 할일 감지 레퍼런스

```python
TASK_REFS = {
    "task": "견적서를 보내기로 약속했고 다음주까지 회신해야 한다",
    "followup": "다시 연락하기로 했고 자료를 준비해서 전달해야 한다",
    "promise": "보험 상품 비교표를 만들어서 보내주기로 했다",
    "not_task": "일반적인 안부를 나누었고 특별한 약속은 없었다",
}
```

---

## 8. 할일 감지 상세

### 판별 로직

1. 인터랙션 summary를 임베딩 (배치에서는 이미 생성된 벡터 재사용)
2. `task`/`followup`/`promise` 레퍼런스 중 최대 유사도 vs `not_task` 유사도 비교
3. `max(task_scores) - not_task_score > 0.05` 이면 Task 생성 (margin threshold)
   - 실측: threshold 없이는 75% 정확도, 0.05 적용 시 100% (8/8)

### Task 생성 필드

```python
task, created = Task.objects.get_or_create(
    fc=interaction.fc,
    contact=interaction.contact,
    title=interaction.summary[:80],        # 80자 truncate
    defaults={
        "source": Task.Source.AI_EXTRACTED,
        "due_date": None,                  # 임베딩으로는 날짜 추출 불가
        "is_completed": False,
    },
)
task.source_interactions.add(interaction)  # 생성/재사용 무관하게 항상 연결
```

`get_or_create`로 중복 방지 (fc + contact + title 기준).
`source_interactions`는 M2M이므로 동일 Task가 여러 배치의 Interaction에 연결될 수 있다.
→ 배치별 집계(`Task.objects.filter(source_interactions__import_batch=batch)`)가 정확해진다.

---

## 9. Feel Lucky 개선

### 현재

LLM이 각 연락처를 분석하여 `FortunateInsight` 생성. AnalysisJob 전체 실행 시에만 생성됨.

### 변경 후

`find_contacts_like()` 시그니처 및 계약은 **섹션 5.3 similarity.py** 참조.

**로직:**
1. FC의 골드 티어 연락처 중 **임베딩이 있는 건만** 수집 → 평균 벡터(centroid) 계산
   - 골드 연락처는 있지만 임베딩이 전부 없으면 (backfill 전) → green fallback
   - fallback도 임베딩 0건이면 빈 리스트 반환
2. 옐로우/레드 티어 중 centroid와 유사도 높은 순 정렬
3. 상위 N건 각각에 대해, 레퍼런스 티어 연락처 중 **가장 유사한 1건(exemplar)**을 선택
4. exemplar의 메타데이터와 후보의 메타데이터를 비교하여 "유망한 이유" 생성

**exemplar 선택 규칙:**
centroid는 후보 검색(ranking)에만 사용하고, 이유 생성에는 사용하지 않는다.
후보별로 레퍼런스 연락처 전원과 cosine similarity를 비교하여 가장 높은 1건을 exemplar로 선택한다.
Python numpy 연산이므로 추가 API 호출 없음. 레퍼런스 연락처가 보통 수십 명 이하이므로 비용 무시 가능.

**"유망한 이유" 텍스트 생성 (exemplar 기반):**
```python
# result["exemplar"]: 이 후보와 가장 유사한 골드/그린 연락처 1건
exemplar = result["exemplar"]
contact = result["contact"]

reasons = []
if contact.industry and contact.industry == exemplar.industry:
    reasons.append(f"{exemplar.name}({exemplar.company_name})과 같은 {contact.industry} 업종")
if contact.region and contact.region == exemplar.region:
    reasons.append(f"같은 {contact.region} 지역")
if not reasons:
    reasons.append(f"골드 고객 {exemplar.name}({exemplar.company_name})과 프로필이 유사합니다")
```

**빈 상태 (골드+그린 모두 0건):** Feel Lucky 섹션에 안내 카드 표시:
"고객 데이터가 쌓이면 AI가 유망 고객을 추천합니다"

---

## 10. UI 변경 사항

### 10.1 수정 대상 템플릿

| 템플릿 | 변경 | 방향 |
|--------|------|------|
| `contacts/import_result.html` | 임포트 완료 화면 보강 | 티어 분포 바 + 분석 결과 숫자 요약 + CTA 상태 전환 (아래 상세) |
| `contacts/partials/contact_list_items.html` | 티어 뱃지 추가 | 기존 건강 dot을 티어 emoji로 대체 (중복 제거) |
| `contacts/partials/contact_detail_content.html` | AI 영역 lazy-load 삽입 | 기본 정보 즉시 렌더 + AI skeleton 자리 확보 |
| `contacts/partials/contact_ai_section.html` | 신규 | 유사 고객 + 감정/할일 보완 결과 (lazy-load 대상) |
| `contacts/partials/contact_ai_skeleton.html` | 신규 | AI 영역 로딩 중 skeleton UI |
| `accounts/partials/dashboard/section_tasks.html` | 할일 급증 대응 | 최대 5건 + "N건 더 보기" 링크 |
| `accounts/partials/dashboard/section_feel_lucky.html` | 임베딩 기반 재구성 | FortunateInsight → find_contacts_like 결과 |
| `accounts/partials/dashboard/section_analysis.html` | 분석 버튼 제거 | 자동 분석 상태 표시로 대체 |
| `intelligence/partials/contact_report_modal.html` | 비동기 분석 로딩 | AI 섹션을 HTMX lazy-load + 스켈레톤 |
| `intelligence/partials/report_analysis_section.html` | 신규 | AI 분석 결과 partial (lazy-load 대상) |

### 10.2 임포트 완료 화면

#### 즉시 표시 (동기 완료 직후)

```
✅ 이번에 등록한 100건의 기본 분석이 준비되었습니다

[티어 분포 바: ⭐3 🟢15 🟡42 🔴12 ⚪28]  ← 대시보드 분석 섹션의 progress bar 재사용

── 추가 분석 진행 중 ──────────────────
  추천 준비 중 ··· ◌
  대화 분위기 분석 중 ··· ◌
  할 일 찾는 중 ··· ◌

[■ 이번에 등록한 연락처 보기]  [대시보드에서 전체 현황 보기]
```

#### 백그라운드 완료 시 (HTMX 폴링으로 점진 업데이트)

```
✅ 이번 임포트 요약이 준비되었습니다

[티어 분포 바: ⭐3 🟢15 🟡42 🔴12 ⚪28]

── 이번 임포트 분석 결과 ──────────────────
  😊 긍정 45건  😐 보통 30건  😟 부정 5건
  할 일 8건 감지됨 → [오늘의 업무에서 확인 →]

[■ 대시보드에서 전체 현황 보기]  [이번에 등록한 연락처 보기]
```

**CTA 전환:** HTMX 폴링 완료 응답에서 CTA 영역도 함께 교체. 분석 완료 시 "대시보드에서 전체 현황 보기"를 기본 강조로 전환.

#### 상태 전이 규칙

분석이 백그라운드로 처리되므로, **완료 시점은 보장되지 않는다:**

- **즉시**: "이번에 등록한 100건의 기본 분석이 준비되었습니다" + 티어 분포 (Python 스코어 기반) + 분석 영역 "추천 준비 중 / 대화 분위기 분석 중 / 할 일 찾는 중"
- **백그라운드 완료 시**: 임포트 완료 화면에서 HTMX 폴링으로 분석 영역 업데이트, CTA 강조가 "대시보드에서 전체 현황 보기"로 전환
- **분석 완료 전 대시보드/목록 이동 시**: **기존 데이터는 그대로 유지.** 페이지 전체를 skeleton으로 덮지 않는다.
  이번 임포트의 영향을 받는 영역(Feel Lucky, 오늘의 업무)만 부분적으로 상태 chip을 표시:
  "방금 가져온 데이터의 추가 분석이 진행 중입니다. 기존 정보는 먼저 확인하실 수 있습니다."
  페이지 진입 5초 후 `setTimeout` + `htmx.ajax`로 해당 영역을 **1회만 자동 재조회**하여 완료 여부를 반영한다.
  (폴링 수명주기 관리 불필요. 5초 후 1회 호출이므로 endpoint 추가 없이 기존 서버 렌더링 그대로 사용.)
- 기존 `import_result.html`의 "AI가 관계를 분석하고 있습니다" 스피너 배너 제거
- **HTMX 폴링은 임포트 완료 화면(`import_result.html`)에만 한정.** 대시보드/목록에서는 5초 후 1회 재조회만.

#### "분석 중" vs "결과 없음" 구분 (필수)

**임포트 완료 화면** (ImportBatch 기준):

| 상태 | UI 표시 | 조건 |
|------|---------|------|
| 분석 중 | skeleton + 단계별 진행 표시 | `batch.is_complete == False` AND 에러 없음 |
| 분석 완료 | 감정/할일 결과 표시 | `batch.is_complete == True` |
| 분석 완료 (부분 실패) | 성공 건 결과 표시 | `batch.error_message` 존재 또는 타임아웃 |
| 타임아웃 | 현재까지 결과 표시 | `batch.created_at`으로부터 5분 경과 |

**대시보드/목록** (FC 전체 기준):

| 상태 | UI 표시 | 조건 |
|------|---------|------|
| 분석 중 | 기존 데이터 유지 + 영향 영역에 상태 chip ("추가 분석 진행 중") | 최근 ImportBatch 중 미완료 건 존재 |
| 결과 없음 | "조건에 맞는 연락처가 없습니다" | 미완료 배치 없음 AND 유사 결과 0건 |

> **기존 데이터를 skeleton으로 덮지 않는다.** 이미 존재하는 Feel Lucky, 할일, 티어 분포는 그대로 표시.
> 이번 임포트의 영향을 받는 영역만 상태 chip으로 "추가 분석 진행 중"을 표시한다.
> 페이지 진입 5초 후 1회 자동 재조회(`setTimeout` + `htmx.ajax`)로 완료 여부를 반영.
> 1회 재조회 후에도 미완료면 다음 페이지 진입 시 최신 상태가 렌더링된다.

> **기존 "임베딩 비율 100% 미도달" 문제 해소:** ImportBatch의 단계별 플래그 기반이므로,
> Gemini API 에러로 일부 임베딩이 실패해도 파이프라인이 다음 단계로 진행하고
> 최종적으로 `is_complete`가 True가 된다. 5분 타임아웃은 스레드 자체가 죽은 경우의 안전장치.

`find_contacts_like()`가 빈 리스트를 반환할 때, 호출자는 위 상태를 구분할 수 있어야 한다.

### 10.3 연락처 목록

기존 건강 dot(`health_level` 기반)을 티어 emoji(`tier_emoji`)로 대체.
둘 다 관계 상태를 나타내므로 중복. 감정 아이콘은 최근 인터랙션 기준으로 목록에 함께 표시.
(티어 = 장기 관계 등급, 감정 = 최근 분위기. 목록에서 "골드인데 최근 부정적" 같은 판단이 가능해야 함)
감정 미분류(sentiment="") 연락처는 감정 아이콘 자리를 비워두거나 "—" 표시.

**감정 맥락 표시 — 모바일/데스크탑 분리:**
- **모바일**: 감정 아이콘 + 날짜를 텍스트로 직접 표시. tooltip에 의존하지 않는다.
- **데스크탑(lg)**: 감정 아이콘 + tooltip 보조 가능.
(모바일 터치 환경에서 tooltip은 동작이 불안정하므로, 핵심 정보는 hover 없이도 보여야 한다.)

**모바일:**
```
⭐ 삼진전자 김사장    제조업  경기    골드
  최근 소통 😊 긍정 · 3/25

🟢 동양기계 최부장    제조업  인천    양호
  최근 소통 😐 보통 · 3/22

🟡 대경산업 최대표    제조업  경기    주의
  최근 소통 😟 부정 · 3/20
```

**데스크탑(lg):**
```
⭐ 삼진전자 김사장    제조업  경기    골드   😊 ← tooltip: "최근 소통: 긍정 (3/25)"
🟢 동양기계 최부장    제조업  인천    양호   😐
🟡 대경산업 최대표    제조업  경기    주의   😟
```

### 10.4 연락처 상세 — 유사 고객 섹션

접점 기록 타임라인 위, 메모/미팅 버튼 아래에 삽입:

```
─── 유사 고객 ───
[⭐ 삼진전자 김사장] 같은 제조업, 경기   →
[🟢 동양기계 최부장] 같은 제조업         →

(탭하면 해당 연락처 상세로 이동)
```

카드 스타일: `bg-white rounded-2xl border border-gray-100 p-3` (디자인 시스템 Card 패턴)
유사도 수치 대신 자연어: "같은 제조업, 경기" (사용자에게 퍼센트는 비직관적)
임베딩 없는 경우 섹션 자체를 숨김.

### 10.5 대시보드 오늘의 업무

AI 감지 할일이 급증할 수 있으므로:
- 최대 5건 표시, "N건 더 보기" 링크
- AI 감지 할일은 별도 그룹으로 분리 표시. 그룹 헤더: "AI가 대화에서 감지한 할일"
- AI 감지 할일에 `AI` 뱃지 표시 (기존 `bg-primary-light text-primary` 스타일)
- Task title이 인터랙션 summary[:80]이므로 할일 제목이 아닌 대화 요약처럼 보일 수 있음.
  각 AI 감지 항목에 원본 인터랙션(연락처 상세)으로의 링크를 함께 제공하여 맥락 확인 가능하게 한다.

### 10.6 Feel Lucky 카드

기존 signal_type별 이모지 대신, 유사 이유 유형별 아이콘으로 시각적 다양성 유지:
- 업종 유사: 🏭
- 지역 유사: 📍
- 규모 유사: 📊
- 기본: 💡

dismiss 기능은 유지. `find_contacts_like` 결과를 FortunateInsight에 저장하여
기존 dismiss 로직 재사용. 저장 계약은 아래 참조.

#### FortunateInsight 저장 계약

**모델 변경:** `unique_together = ["fc", "contact"]` 추가.
기존 중복 row가 있으면 migration에서 정리. 우선순위: `is_dismissed=True`인 row를 우선 유지 (사용자 dismiss 의사 보존).
둘 다 dismissed이거나 둘 다 아닌 경우에만 `created_at` 최신 1건 유지. 나머지 삭제.

**upsert 규칙:** `update_or_create(fc=fc, contact=contact)` 사용.
같은 contact가 다시 추천되면 기존 row의 `reason`, `signal_type`, `expires_at`을 갱신하되
`is_dismissed`는 `defaults`에 포함하지 않아 기존 dismiss 상태를 보존한다.

```python
# Step 1: 기존 row의 만료 여부를 먼저 확인 (갱신 전)
existing = FortunateInsight.objects.filter(fc=fc, contact=contact).first()
should_reset_dismiss = (
    existing is not None
    and existing.is_dismissed
    and existing.expires_at is not None
    and existing.expires_at < now()
)

# Step 2: upsert (is_dismissed는 defaults에 포함하지 않음 → 기존 값 보존)
defaults = {
    "reason": generated_reason,
    "signal_type": signal_type,
    "expires_at": now() + timedelta(days=7),
}
if should_reset_dismiss:
    defaults["is_dismissed"] = False  # 만료된 dismissed → 리셋하여 재추천 허용

FortunateInsight.objects.update_or_create(
    fc=fc,
    contact=contact,
    defaults=defaults,
)
```

**dismiss 보존:**
- `is_dismissed=True`인 row는 대시보드 쿼리에서 제외.
- upsert 시 `is_dismissed`를 `defaults`에 포함하지 않아 기존 dismiss 상태를 보존.
- 단, 만료된 dismissed row(`expires_at < now()`)는 `is_dismissed=False`를 `defaults`에 추가하여 리셋.

**만료 정책:** `expires_at = now() + 7일` (upsert 시 갱신).
- 만료 전: dismiss 상태 유지 (대시보드에 표시 안 됨)
- 만료 후: upsert 시 `is_dismissed=False`로 리셋하여 다시 추천 대상이 될 수 있음
  (임베딩이 바뀌면서 추천 이유가 달라질 수 있으므로 유한 만료가 자연스러움)

**주의:** 만료 판정은 반드시 `update_or_create` 이전에 기존 row를 읽어서 수행.
`update_or_create`가 먼저 `expires_at`을 갱신하면 만료 여부가 항상 False가 된다.

**대시보드 쿼리:**
```python
FortunateInsight.objects.filter(fc=user, is_dismissed=False, expires_at__gt=now())
```
`expires_at__gt=now()` 조건으로 만료된 추천을 자동 제외한다.
`find_contacts_like`가 대시보드 진입 시마다 실행되어 현재 top N의 `expires_at`을 `now()+7일`로 갱신하므로,
top N에서 빠진 추천은 갱신되지 않아 7일 후 자연 만료된다. 별도 정리 로직 불필요.

### 10.7 대시보드 분석 섹션

"관계 분석 실행" 버튼 제거. **전체 고객 데이터** 기준의 분석 현황을 사용자 언어로 표시.
(10.2절 임포트 완료 화면은 "이번 임포트" 기준. 이 섹션은 "FC의 전체 고객" 기준. 기준이 다르므로 명확히 구분.)

**제목:** "전체 고객 데이터 분석 현황"

**분석 진행 중:**
```
전체 고객 데이터 분석 현황
추천 준비 중 · 대화 분위기 정리 중
[████████░░░░░░░░] ← 프로그레스바 (퍼센트 숫자 없음)
```

**분석 완료:**
```
전체 고객 데이터 분석 현황
추천 준비 완료 · 대화 분위기 분석 완료 · 관계 점수 최신
```

퍼센트 숫자를 표시하지 않는 이유: Gemini 부분 실패로 100%에 도달하지 못할 수 있다.
99%에 멈춰있으면 사용자가 불안해하므로, 프로그레스바만으로 "진행 중"을 전달한다.

**집계 기준 (내부 진행률 계산, UI에는 바만 노출):**
- 분모: `Contact.objects.filter(fc=user).count()`
- 임베딩: `ContactEmbedding.objects.filter(contact__fc=user).count()` / 분모
- 감정분류: `Interaction.objects.filter(fc=user).exclude(sentiment="").count()` / 전체 인터랙션 수
- 완료 판정: 임베딩 비율 ≥ 95% AND 감정분류 비율 ≥ 95% (부분 실패 허용)
- 완료 시 "완료" 상태 문구, 미완료 시 프로그레스바 표시

### 10.8 반응형 레이아웃

- 유사 고객: 모바일 세로 스택, 데스크탑(lg) 가로 그리드
- 임포트 요약: 모바일 세로 나열, 데스크탑 2열
- Feel Lucky: 현행 유지 (모바일 카드 스택)

---

## 11. 기존 코드 변경 범위

### 삭제

| 함수 | 파일 | 이유 |
|------|------|------|
| `analyze_contact_relationship()` | intelligence/services.py | 모듈 분리로 대체 |
| `analyze_sentiments()` | intelligence/services.py | 임베딩 방식으로 대체 |
| `map_excel_columns()` | intelligence/services.py | views.py에서 미참조, detect_header_and_map만 사용 |

### 이동 (리팩터링)

| 함수 | 현재 | 이동 |
|------|------|------|
| `calculate_relationship_score()` | intelligence/services.py | intelligence/services/scoring.py |
| `generate_dashboard_briefing()` | intelligence/services.py | intelligence/services/briefing.py |
| `detect_header_and_map()` | intelligence/services.py | intelligence/services/excel.py |
| `classify_sheets()` | intelligence/services.py | intelligence/services/excel.py |

### 수정

| 파일 | 변경 |
|------|------|
| contacts/views.py | 임포트 후 ImportBatch 생성 + 백그라운드 분석 파이프라인 호출. `contact_ai_section` lazy-load endpoint 추가 |
| contacts/models.py | Interaction에 `import_batch` FK 추가 (nullable, 기존 데이터 호환), `task_checked` BooleanField 추가 (default=False). Task의 `source_interaction` FK → `source_interactions` M2M 변경 |
| intelligence/views.py | contact_report 비동기 분석 + contact_report_analysis 신규 endpoint + import_analysis_status 폴링 endpoint (batch_id 기준) |
| intelligence/models.py | `ContactEmbedding` + `ImportBatch` 모델 추가. `FortunateInsight`에 `unique_together = ["fc", "contact"]` 추가 + 중복 row 정리 migration |
| docker-compose.yml | `postgres:16-alpine` → `pgvector/pgvector:pg16` |
| pyproject.toml | `google-genai`, `pgvector` 추가 |
| Dockerfile | 의존성 반영 |
| .env.example | `GEMINI_API_KEY` 항목 추가 |
| main/urls.py | `contact_ai_section` + `contact_report_analysis` + `import_analysis_status/<batch_id>` URL 추가 |
| 템플릿 10개 | 섹션 10 참조 |

---

## 12. 비용/성능 요약

| 시나리오 | 현재 | 변경 후 |
|---------|------|---------|
| 100건 임포트 | 임포트 자체는 LLM 3~4회 (헤더+감정). AnalysisJob 수동 실행 시 +100회 LLM, $2-5, 200분 | 연락처 임베딩 1배치 + 인터랙션 임베딩 1배치 + 감정분류/할일감지(Python cosine). ~$0.002, ~8초. LLM 0회 |
| 인터랙션 추가 | Python 스코어만 | + 감정분류 + 할일감지 + 임베딩 갱신, +0.1초 |
| Feel Lucky | AnalysisJob 전체 실행 필요 | pgvector 쿼리, <10ms |
| 심층 분석 (1건) | 수동 일괄 실행 | 온디맨드 LLM 1~2회 (요약+인사이트), $0.02, 15초. 비동기 로딩 |
| AI 브리핑 | LLM 1회/일 | 동일 |

---

## 13. 마이그레이션 전략

### Phase 1: 인프라

1. docker-compose.yml에서 `postgres:16-alpine` → `pgvector/pgvector:pg16`
2. 운영 DB: 백업 → 테스트 환경에서 이미지 교체 검증 → 운영 적용 → `CREATE EXTENSION vector`
3. `google-genai`, `pgvector` 패키지 추가 (pyproject.toml + Dockerfile)
4. `ContactEmbedding` + `ImportBatch` 모델 + migration

### Phase 2: 모듈 분리

5. `intelligence/services.py` → `intelligence/services/` 패키지 전환 (기존 함수 이동)
6. `__init__.py` re-export 설정 (기존 import 경로 호환)
7. `common/embedding.py` Gemini 래퍼 작성 (lazy 초기화)
8. 레퍼런스 벡터 + 파일 캐시 구현

### Phase 3: 서비스 함수 구현

9. embedding.py: `build_contact_text`, `embed_contact`, `embed_contacts_batch`
10. sentiment.py: `classify_sentiment`, `classify_sentiments_batch`
11. task_detect.py: `detect_task`, `detect_tasks_batch`
12. similarity.py: `find_similar_contacts`, `find_contacts_like`
13. orchestration.py: `ensure_embedding`, `ensure_sentiments_and_tasks`, `ensure_deep_analysis`
14. deep_analysis.py: `generate_summary`, `generate_insights` (기존 프롬프트 분리)

**Phase 3 의존관계 (병렬 디스패치 참고):**
```
9  (embedding.py)      ← 독립 (common/embedding.py만 의존)
14 (deep_analysis.py)  ← 독립 (기존 claude.py만 의존)
10 (sentiment.py)      ← 9 의존
11 (task_detect.py)    ← 9 의존      ← 10, 11, 12 병렬 가능
12 (similarity.py)     ← 9 의존
13 (orchestration.py)  ← 9, 10, 11, 14 의존 (마지막에 구현)
```

### Phase 4: 파이프라인 연결

15. 엑셀 임포트 후 백그라운드 분석 파이프라인 연결
16. 인터랙션 추가 시 감정분류 + 할일감지 + 임베딩 갱신 연결
17. 연락처 상세에 ensure_* + find_similar 연결
18. 미팅 리포트 비동기 로딩 (HTMX lazy-load)

### Phase 5: UI 변경

19. 임포트 완료 화면 보강 (티어 분포 + 할일 미리보기)
20. 연락처 목록: 건강 dot → 티어 emoji
21. 연락처 상세: 유사 고객 섹션
22. 대시보드: Feel Lucky 임베딩 기반, 분석 섹션 변경, 할일 5건 제한
23. 리포트 모달: 스켈레톤 + lazy-load

### Phase 6: 정리

24. 기존 `analyze_contact_relationship()`, `analyze_sentiments()` 삭제
25. AnalysisJob: "관계 분석 실행" 버튼 제거, 자동 분석 상태 표시로 대체
26. 기존 데이터 backfill: management command로 전체 연락처 배치 임베딩 1회 실행

### 기존 데이터 backfill

마이그레이션 후 기존 연락처에 임베딩이 없으므로:

```bash
uv run python manage.py backfill_embeddings
```

- **시작 전 레퍼런스 캐시 선확인:** 감정분류/할일감지에 필요한 레퍼런스 벡터 캐시(`.cache/sentiment_refs.json`, `.cache/task_refs.json`)가 존재하는지 확인. 없으면 Gemini API로 생성. API 장애 시 감정/할일 단계를 스킵하지 않고 에러로 중단 (backfill은 재실행 가능하므로 조용히 스킵보다 명시적 실패가 나음)
- 모든 연락처에 대해 `embed_contacts_batch` 실행 (100건 단위)
- 모든 인터랙션에 대해 임베딩 1회 생성 후 감정분류 + 할일감지에 공유 (임포트 파이프라인과 동일 패턴):
  ```python
  for chunk in chunked(all_interactions, 100):
      texts = [i.summary for i in chunk]
      embeddings = get_embeddings_batch(texts)  # Gemini 1회
      classify_sentiments_batch(chunk, embeddings=embeddings)  # 재사용
      detect_tasks_batch(chunk, embeddings=embeddings)          # 재사용
  ```
- 운영 배포 후 1회 실행

---

## 14. Agent Team 구현 아키텍처

### 14.1 설계 원칙

스킬/도구가 특화된 서브에이전트를 Orchestrator가 순차 디스패치한다.
각 서브에이전트는 역할에 맞는 도구셋을 가지되, 에이전트 간 소통은 파일 기반 핸드오프로 대체한다.

**순차 디스패치를 선택한 이유:**

1. **의존 그래프가 선형이다.** UX 구현은 Engineer의 인터페이스에 의존하고, Critic 검증은 구현 완료에 의존한다. 실질적 병렬 구간이 없다.
2. **파일 핸드오프가 직접 소통보다 안정적이다.** 에이전트 간 직접 대화는 Orchestrator에서 추적이 안 되고, 같은 파일을 동시 수정하면 충돌이 발생한다. 파일로 남기면 누구나 읽을 수 있고 이력이 남는다.
3. **깨끗한 컨텍스트가 품질을 높인다.** 장시간 세션은 컨텍스트 윈도우 압축으로 초기 맥락이 손실될 위험이 있다. 서브에이전트가 명확한 입력(설계서 섹션 + 이전 산출물)으로 시작하면 hallucination 위험이 줄어든다.
4. **실패 시 해당 단계만 재실행 가능하다.** 단계별 입출력이 파일로 명확하므로 디버깅이 쉽다.

### 14.2 팀 구성

```
Orchestrator (메인 세션 = 팀 리더)
│
├─ Step 1: Engineer 서브에이전트
│   입력: 설계서 1-8, 11절 + 체크리스트 15.1절
│   산출물: intelligence/services/*.py, common/embedding.py, models.py,
│           migrations/, docker-compose.yml, pyproject.toml,
│           .agents/interface-spec.md (UX용 인터페이스 명세)
│
├─ Step 2: Code Critic 서브에이전트
│   입력: Engineer 산출물 + 체크리스트 15.1절
│   산출물: .agents/code-review.md
│   → FIXABLE → Engineer 재디스패치 (리뷰 파일 포함) → 재검증
│
├─ Step 3: UX 서브에이전트
│   입력: 설계서 10절 + .agents/interface-spec.md + 체크리스트 15.2절
│   산출물: templates/**/*.html, static/ 변경
│   → endpoint 추가 필요 시: .agents/ux-requests.md에 요청 명세 작성
│     → Orchestrator가 Engineer 재디스패치로 해결 후 UX 재디스패치
│
├─ Step 4: UX Critic 서브에이전트
│   입력: UX 산출물 + 체크리스트 15.2절
│   산출물: .agents/ux-review.md
│   → FIXABLE → UX 재디스패치 (리뷰 파일 포함) → 재검증
│
└─ Step 5: Orchestrator가 최종 /review 스킬 실행
    - Critic과 다른 축: SQL 안전성, 레이스 컨디션, 테스트 커버리지, Codex 크로스모델 리뷰
```

**산출물 파일 규칙:**
- Critic의 리뷰 파일은 `.agents/` 디렉토리에 생성 (`.gitignore` 대상)
- 리뷰 파일은 overwrite가 아닌 append. 회차별 타임스탬프 + 발견사항 누적
- 재검증 시 Critic은 이전 회차 피드백을 읽어서 수정 여부를 확인

| 서브에이전트 | 역할 | 도구 | 쓰기 권한 |
|-------------|------|------|----------|
| **Engineer** | Phase 1-4 (인프라, 모듈 분리, 서비스 함수, 파이프라인) | file_read, file_write, file_edit, bash, pytest, ruff, grep, glob | O |
| **UX** | Phase 5 (UI 변경 8개 템플릿, 반응형, UX 패턴) | file_read, file_write, file_edit, bash, browser, screenshot, grep, glob | O |
| **Code Critic** | Engineer 산출물의 코드 품질 + 설계서 정합성 검증 | file_read, grep, glob, bash (pytest, git diff) | X (`.agents/` 리뷰 파일만) |
| **UX Critic** | UX 산출물의 디자인 + UX 흐름 + 반응형 검증 | file_read, grep, glob, browser, screenshot | X (`.agents/` 리뷰 파일만) |

**Critic을 2개로 분리하는 이유:**
- 검증 축이 다르다: 코드 정확성 vs 화면 경험
- 읽는 파일이 다르다: `.py` vs `.html` + 렌더링 결과
- 도구가 다르다: pytest/grep vs browser/screenshot

### 14.2.1 UX Critic 전제 조건

UX Critic이 browser/screenshot 도구로 렌더링 결과를 검증하려면:

- 개발 서버가 기동 상태여야 함 (`uv run python manage.py runserver 0.0.0.0:8000`)
- 테스트 FC 계정으로 인증된 브라우저 세션 필요
- 최소한의 테스트 데이터 존재 (연락처 N건 + 인터랙션 + 미팅)

Orchestrator가 Step 4 디스패치 전에 전제 조건을 확보한다.
브라우저 기반 검증이 불가능한 환경에서는 템플릿 정적 분석 + 통과 조건 체크리스트로 대체.

### 14.3 소통 방식: 파일 기반 핸드오프

에이전트 간 직접 소통 대신, Orchestrator가 중재하고 파일이 인터페이스 역할을 한다.

```
           Orchestrator (순차 디스패치 + 중재)
           ┌──────┼──────┐──────────┐
           ↓      ↓      ↓          ↓
       Engineer  Code   UX       UX
                Critic           Critic
           │      ↑      │          ↑
           └──→ 산출물 ──→┘          │
              (.py 파일 +            │
          interface-spec.md)   산출물 (.html)
                              ──────┘
```

**핸드오프 파일:**

| 파일 | 작성자 | 독자 | 내용 |
|------|--------|------|------|
| `.agents/interface-spec.md` | Engineer | UX | 함수 시그니처, 반환값, endpoint URL, 컨텍스트 변수 |
| `.agents/code-review.md` | Code Critic | Engineer (재디스패치 시) | FIXABLE/INVESTIGATE 목록, 회차별 누적 |
| `.agents/ux-requests.md` | UX | Engineer (재디스패치 시) | 추가 필요한 endpoint, API 변경 요청 |
| `.agents/ux-review.md` | UX Critic | UX (재디스패치 시) | FIXABLE/INVESTIGATE 목록, 회차별 누적 |

### 14.4 실행 순서

```
Step 1: Engineer 구현
═══════════════════
1. Orchestrator → Engineer 디스패치
   입력: 설계서 1-8, 11절 + 체크리스트 15.1절
2. Engineer: Phase 1-4 구현
3. Engineer: .agents/interface-spec.md 작성
   - 함수 시그니처 (ensure_*, find_similar_contacts 등)
   - 서비스 함수 반환값, 컨텍스트 변수
   - endpoint URL, 파이프라인 동작 방식
4. Engineer 종료 → Orchestrator에 산출물 목록 반환

Step 2: Code Critic 검증 루프
═══════════════════
5. Orchestrator → Code Critic 디스패치
   입력: Engineer 산출물 + 체크리스트 15.1절
6. Code Critic: 산출물 읽고 검증 (.agents/code-review.md 1회차 작성)
7. FIXABLE 있으면:
   → Orchestrator → Engineer 재디스패치 (code-review.md 포함)
   → Engineer 수정
   → Orchestrator → Code Critic 재디스패치 (변경분만, 2회차 append)
   → 최대 3회 반복
8. INVESTIGATE 있으면: Orchestrator가 사용자에게 에스컬레이션

Step 3: UX 구현
═══════════════════
9. Orchestrator → UX 디스패치
    입력: 설계서 10절 + .agents/interface-spec.md + 체크리스트 15.2절
10. UX: Phase 5 구현 (interface-spec.md 기반)
11. UX가 추가 endpoint 필요 시:
    → .agents/ux-requests.md에 요청 명세 작성
    → UX 종료
    → Orchestrator → Engineer 재디스패치 (ux-requests.md 포함)
    → Engineer 수정 + interface-spec.md 업데이트
    → 경미한 변경: Step 5 /review에서 커버
    → 구조적 변경: Code Critic 재검증 (Step 2 반복)
    → Orchestrator → UX 재디스패치 (업데이트된 interface-spec.md 포함)
12. UX 종료 → Orchestrator에 산출물 목록 반환

Step 4: UX Critic 검증 루프
═══════════════════
13. Orchestrator → UX Critic 디스패치
    입력: UX 산출물 + 체크리스트 15.2절
14. UX Critic: 산출물 읽고 검증 (.agents/ux-review.md 1회차 작성)
15. FIXABLE 있으면:
    → Orchestrator → UX 재디스패치 (ux-review.md 포함)
    → UX 수정
    → Orchestrator → UX Critic 재디스패치 (변경분만, 2회차 append)
    → 최대 3회 반복
16. INVESTIGATE 있으면: Orchestrator가 사용자에게 에스컬레이션

Step 5: 최종 검증
═══════════════════
17. Orchestrator: /review 스킬 실행 (최종 범용 코드 품질 검증)
    - Critic과 다른 축: SQL 안전성, 레이스 컨디션,
      테스트 커버리지, Codex 크로스모델 리뷰
```

### 14.5 검증 루프 규칙

```
Orchestrator → Critic 디스패치 → 검증
                                  │
                  ├── 발견 0건 → 통과. 다음 Step 진행.
                  │
                  ├── FIXABLE N건 → Orchestrator가 구현 에이전트 재디스패치
                  │       │
                  │       ▼
                  │   구현 에이전트 수정 → Critic 재디스패치 (변경분만)
                  │       │
                  │       ├── 통과 → 끝
                  │       └── 또 발견 → 2차 수정 → 재검증
                  │               │
                  │               └── 3회차 도달 → STOP. 사용자 에스컬레이션
                  │
                  └── INVESTIGATE N건 → 즉시 사용자 에스컬레이션
                        (자동 해결 불가. 사람 판단 필요)
```

- **FIXABLE:** Orchestrator가 구현 에이전트 재디스패치 → Critic 재검증 (변경분만)
- **INVESTIGATE:** 즉시 사용자 에스컬레이션 (루프 진입 안 함)
- **최대 3회 루프.** 3회 미통과 시 사용자 에스컬레이션
- **재검증은 전체 리뷰가 아닌 수정된 부분만 대상**
- **Critic 재디스패치 시 이전 회차의 리뷰 파일을 입력으로 포함** (수정 여부 확인용)

---

## 15. 검증 통과 조건

Critic이 주관적으로 판단하지 않도록 사전 정의된 체크리스트로 판정한다.
구현 서브에이전트에게도 동일한 체크리스트를 입력으로 제공하여 1차 통과율을 높인다.

**통과 판정 로직:**
- 필수 항목 전체 PASS → 통과. 루프 종료.
- 필수 항목 1건이라도 FAIL → 미통과. FIXABLE로 분류, 수정 루프.
- 권장 항목 FAIL → review 파일에 기록만. 통과에 영향 없음.

### 15.1 Code Critic 통과 조건

#### 필수 (하나라도 FAIL이면 미통과)

**자동 검증 (커맨드 실행으로 판정)**
- [ ] `uv run pytest -v` 전체 통과
- [ ] `uv run ruff check .` + `uv run ruff format --check .` 클린
- [ ] `uv run python manage.py makemigrations --check --dry-run` → "No changes detected"

**Graceful Degradation (설계서 2.4절)**
- [ ] Gemini API 실패 시 연락처 저장 정상 진행 (테스트로 검증)
- [ ] `ensure_*` 함수 실패 시 `None`/빈값 반환 (`raise` 아님)
- [ ] `embed_contact()` 실패 시 기존 임베딩 유지 (삭제 안 함)
- [ ] 백그라운드 분석 실패 시 에러 로깅 (logger.exception). "조용히 실패" = 사용자에게 안 보여줌이지 기록 안 남김이 아님

**비용 효율 (설계서 2.3절, 12절)**
- [ ] `classify_sentiments_batch()`에 LLM 호출 없음 (임베딩 cosine similarity만)
- [ ] `detect_tasks_batch()`에 LLM 호출 없음 (임베딩 cosine similarity만)
- [ ] `find_contacts_like()`에 LLM 호출 없음 (pgvector 쿼리만)
- [ ] 배치 임베딩 100건 청킹 구현 (100건 초과 시 내부 분할)
- [ ] `source_hash` 비교로 불필요한 임베딩 재생성 방지 (설계서 5.3절 핵심 동작)

**데이터 모델 + 인프라 (설계서 3-4절)**
- [ ] migration에 `reverse_func` 포함 (reversible)
- [ ] `docker-compose.yml`에 `pgvector/pgvector:pg16` 이미지 반영
- [ ] `pyproject.toml`에 `google-genai`, `pgvector` 추가
- [ ] `.env.example`에 `GEMINI_API_KEY` 항목 존재
- [ ] `.cache/` 디렉토리 `.gitignore`에 포함
- [ ] `.agents/` 디렉토리 `.gitignore`에 포함
- [ ] FortunateInsight 모델에 `unique_together = ["fc", "contact"]` 추가
- [ ] FortunateInsight 중복 row 정리 migration (최신 1건 유지, 나머지 삭제, reverse_func 포함)

**모듈 분리 + 호환성 (설계서 5절, 11절)**
- [ ] `intelligence/services/__init__.py` re-export로 기존 import 경로 정상 동작
- [ ] 삭제 대상 함수 3건 제거 확인: `analyze_contact_relationship()`, `analyze_sentiments()`, `map_excel_columns()` (grep으로 호출부 없음 검증)
- [ ] 이동 대상 함수 4건 정위치 확인: `calculate_relationship_score` → scoring.py, `generate_dashboard_briefing` → briefing.py, `detect_header_and_map` → excel.py, `classify_sheets` → excel.py
- [ ] 수정 대상 파일 반영 확인: contacts/views.py (임포트 파이프라인), contacts/models.py (Interaction에 import_batch FK + task_checked BooleanField, Task의 source_interaction FK→source_interactions M2M 변경), intelligence/views.py (비동기 분석), intelligence/models.py (ContactEmbedding + ImportBatch + FortunateInsight unique_together 추가), main/urls.py (report_analysis endpoint)

**파이프라인 (설계서 6절)**
- [ ] 엑셀 임포트 백그라운드 스레드 예외 시 연락처 저장 rollback 안 됨
- [ ] `ensure_deep_analysis()` 캐시 유효성 2중 조건: created_at 24시간 이내 AND 분석 이후 새 인터랙션 없음
- [ ] 인터랙션 추가 시 classify_sentiment + detect_task + calculate_relationship_score + embed_contact 연결 (설계서 6.5절)
- [ ] `detect_task()` / `detect_tasks_batch()` 처리 완료 후 `task_checked=True` 설정 (Task 생성 여부 무관)
- [ ] `ensure_sentiments_and_tasks()` 대상 선정: `sentiment=""` (감정분류) + `task_checked=False` (할일감지) 합집합
- [ ] Gemini API 실패 시 `task_checked=False` 유지 (다음 기회 재시도)

**Feel Lucky / FortunateInsight (설계서 9절, 10.6절)**
- [ ] `find_contacts_like` 결과를 FortunateInsight에 `update_or_create(fc, contact)` 저장
- [ ] upsert 시 `is_dismissed`를 `defaults`에 포함하지 않음 (dismiss 보존)
- [ ] 만료된 dismissed 항목(`expires_at < now()`) upsert 시 `is_dismissed=False` 리셋
- [ ] `expires_at = now() + 7일` 설정
- [ ] 대시보드 쿼리: `filter(fc=user, is_dismissed=False, expires_at__gt=now())` (만료된 추천 자동 제외)

**백그라운드 스레드 안전성 (설계서 6.1.1절)**
- [ ] 모든 백그라운드 스레드에서 `try/finally: connection.close()` 패턴 사용 (커넥션 풀 고갈 방지)
- [ ] 백그라운드 스레드에 `daemon=False` (daemon 스레드는 프로세스 종료 시 강제 kill → 부분 커밋)
- [ ] 동기 저장 루프 완료 후 스레드 시작 (autocommit 모드에서 루프 종료 = 모든 데이터 커밋 완료)
- [ ] 백그라운드 스레드 예외 시 `logger.exception()` 호출 (`except: pass` 금지)

#### 권장 (FAIL이어도 통과, code-review.md에 기록)

- [ ] 레퍼런스 벡터 캐시 파일 없을 때 + API 장애 시 스킵 확인
- [ ] `find_contacts_like()` 골드 0건 → green fallback → 빈 리스트 경로 동작
- [ ] `detect_task()` margin threshold 0.05 적용
- [ ] `build_contact_text()` 최대 2000자 truncate
- [ ] 100건 임포트 시 Gemini API 호출 횟수가 연락처 임베딩 1배치 + 인터랙션 임베딩 1배치 (100건 단위 청킹, 감정/할일은 Python cosine이므로 API 호출 없음)

### 15.2 UX Critic 통과 조건

#### 필수 (하나라도 FAIL이면 미통과)

**HTMX 패턴 일관성**
- [ ] 모든 새 화면에서 `hx-get` + `hx-target="#main-content"` + `hx-push-url="true"` 패턴 사용
- [ ] 새 form에 글로벌 로딩 애니메이션 동작
- [ ] CSRF 토큰이 모든 POST form에 포함

**빈 상태/에러 상태 처리**
- [ ] 임베딩 없는 연락처: 유사 고객 섹션 숨김 (빈 섹션 노출 안 됨)
- [ ] HTMX lazy-load 실패 시 사용자에게 에러 상태 표시 (빈 화면 방치 안 됨)
- [ ] 리포트 모달: 스켈레톤 UI → 결과 교체 전환 구현 (LLM 15초 빈 화면 방지, 설계서 6.4절)

**"분석 중" vs "결과 없음" 구분 (설계서 10.2절)**
- [ ] 임포트 직후 대시보드: 기존 데이터 유지 + 영향 영역에 상태 chip ("추가 분석 진행 중"). 페이지 전체 skeleton 금지
- [ ] 분석 완료 후 결과 0건: "조건에 맞는 연락처가 없습니다" 텍스트 표시
- [ ] 임포트 완료 화면: CTA가 "이번에 등록한 연락처 보기" / "대시보드에서 전체 현황 보기"로 기준 구분. 완료 시 "대시보드에서 전체 현황 보기" 기본 강조
- [ ] 대시보드/목록: 페이지 진입 5초 후 1회 자동 재조회 (`setTimeout` + `htmx.ajax`). 폴링 아님

**모바일 정보 접근성**
- [ ] 연락처 목록: 모바일에서 감정 맥락을 텍스트로 직접 표시 ("😊 긍정 · 3/25"). tooltip에만 의존하지 않음

**사용자 언어**
- [ ] 임포트 완료 단계별 텍스트: "추천 준비 중 / 대화 분위기 분석 중 / 할 일 찾는 중" (기술 용어 "임베딩/감정분류" 금지)
- [ ] 대시보드 분석 섹션: "전체 고객 데이터 분석 현황" 제목으로 이번 임포트 기준과 구분

**반응형**
- [ ] 모바일(`max-w-md`)에서 레이아웃 깨지지 않음
- [ ] 데스크탑(`lg`)에서 레이아웃 깨지지 않음

**설계서 10절 UI 변경**
- [ ] 임포트 완료 화면: 티어 분포 바 표시
- [ ] 대시보드 할일: 최대 5건 + "N건 더 보기" 링크
- [ ] 연락처 목록: 건강 dot → 티어 emoji 대체 완료
- [ ] 대시보드 분석 섹션: "관계 분석 실행" 버튼 제거 → 자동 분석 상태 표시 (설계 원칙 2.2 "버튼을 누르게 하지 않음")

**기본 품질**
- [ ] UI 텍스트 한국어 존대말 ("등록되었습니다", "추가되었습니다")

#### 권장 (FAIL이어도 통과, ux-review.md에 기록)

- [ ] 유사 고객 카드: `docs/DESIGN.md` Card 패턴 준수 (`bg-white rounded-2xl border border-gray-100 p-3`)
- [ ] Feel Lucky: signal_type별 아이콘 분기 (🏭📍📊💡)
- [ ] 임포트 완료 백그라운드 폴링: 분석 영역 HTMX 업데이트
- [ ] 유사 고객: 모바일 세로 스택, 데스크탑 가로 그리드
- [ ] AI 감지 할일에 `AI` 뱃지 표시
- [ ] 연락처 목록: 데스크탑에서 감정 tooltip 보조 표시
