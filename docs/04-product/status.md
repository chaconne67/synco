# synco MVP 개발 현황

**Version:** v0.3.0
**Date:** 2026-03-29
**Tech Stack:** Django 5.2 + HTMX + Tailwind CSS + Claude AI + Gemini Embedding + pgvector

---

## 구현 완료 기능

### 1. 카카오 OAuth 인증
- 카카오 로그인 → 콜백 → 유저 생성/로그인 → 역할 선택(FC/CEO) → 대시보드
- `KakaoBackend` 커스텀 인증 백엔드
- 개발/배포 Redirect URI 분리 (`http://49.247.46.171:8000`, `https://synco.kr`)

### 2. 연락처 관리 (CRUD + 검색 + 필터)
- 연락처 생성/조회/수정/삭제
- 실시간 검색 (이름/회사명, HTMX `keyup delay:300ms`)
- 업종별 필터 (제조/유통/IT/서비스/금융)
- 접점 기록 타임라인 (통화/미팅/메시지/메모 + 감정) + **인라인 수정/삭제**
- 무한 스크롤 (20건씩 로드, HTMX `hx-trigger="revealed"`)
- 연락처 목록: 티어 emoji 표시 + 모바일 감정 텍스트 직접 노출

### 3. 엑셀 AI 임포트 (핵심 기능)

**3단계 플로우:**

| 단계 | 내용 | 기술 |
|------|------|------|
| Step 1 | 파일 업로드 (최대 5MB) | openpyxl, 프론트 SheetJS 검증 |
| Step 2 | AI 헤더 감지 + 컬럼 매핑 + 미리보기 | Claude CLI (`claude --print`) |
| Step 3 | 임포트 실행 + 관계 스코어 계산 + **백그라운드 임베딩 분석** | threading + ImportBatch |

**AI 헤더 감지 + 컬럼 매핑:**
- `detect_header_and_map()` — 헤더 유무를 AI가 판단, 헤더 없는 엑셀도 데이터 패턴으로 매핑
- 매핑 대상: 이름, 전화번호, 회사명, 업종, 지역, 매출규모, 직원수, 미팅일자, 미팅시간, 메모
- 사용자가 AI 매핑 결과를 미리보기에서 수정 가능

**멀티시트 처리:**
- `classify_sheets()` — AI가 각 시트를 분석하여 연락처 시트 자동 판별
- 시트 선택 UI: "합쳐서 처리" / "시트 선택" 옵션 제공

**임포트 후 자동 분석 파이프라인 (v0.3.0 신규):**
- 동기: Python 스코어 계산 → ImportBatch 생성
- 백그라운드: Gemini 임베딩 → 감정분류 → 할일감지 → 스코어 재계산
- HTMX 폴링으로 단계별 진행 상태 표시 ("추천 준비 중 / 대화 분위기 분석 중 / 할 일 찾는 중")
- 완료 시 감정 분포 + 감지된 할일 수 표시
- Gemini API 장애 시 연락처 저장은 정상 진행 (Graceful Degradation)

### 4. 임베딩 기반 관계 분석 (v0.3.0 신규)

**Gemini Embedding + pgvector 기반 분석 시스템:**

| 기능 | 함수 | API | 비용 |
|------|------|-----|------|
| 연락처 임베딩 | `embed_contact`, `embed_contacts_batch` | Gemini | ~$0.001/100건 |
| 감정분류 | `classify_sentiment`, `classify_sentiments_batch` | 없음 (cosine) | 0 |
| 할일감지 | `detect_task`, `detect_tasks_batch` | 없음 (cosine) | 0 |
| 유사 고객 검색 | `find_similar_contacts` | 없음 (pgvector) | 0 |
| 유망 고객 추천 | `find_contacts_like` | 없음 (pgvector+numpy) | 0 |
| 심층 분석 | `generate_summary`, `generate_insights` | Claude | ~$0.02/건 |

**감정분류/할일감지:** LLM 호출 없이 레퍼런스 벡터와 cosine similarity로 판정. 레퍼런스 벡터는 lazy 초기화 + 파일 캐시.

**자동 오케스트레이션:**

| 사용자 행동 | 시스템 자동 실행 | 사용자가 보는 것 |
|------------|----------------|----------------|
| 엑셀 임포트 | 동기: score / BG: embed+classify+detect | 즉시 티어 + 수초 후 감정/할일 |
| 연락처 상세 | HTMX lazy-load: ensure+find_similar | 기본 정보 즉시 + 유사 고객 비동기 |
| 미팅 리포트 | 즉시 렌더 + AI 분석 lazy-load | 기본 정보 즉시 + AI 분석 비동기 |
| 인터랙션 추가 | classify+detect+score+re-embed | 감정/스코어/할일 즉시 |

### 5. 관계 스코어링 (Relationship Scoring)

**5단계 티어 시스템 (가중평균: 업무 긴급도 60% + 친밀도 40%):**

| 티어 | 이모지 | 점수 | 의미 |
|------|--------|------|------|
| **골드** | ⭐ | 80+ | 핵심 고객, 업무 진행 중 + 관계 좋음 |
| **양호** | 🟢 | 60-79 | 긍정 반응, 정기 접촉 유지 |
| **주의** | 🟡 | 40-59 | 접촉 뜸해짐 or 반응 미온 |
| **위험** | 🔴 | 20-39 | 오래 연락 없음 or 부정 반응 |
| **미분석** | ⚪ | 0-19 | 데이터 부족 |

### 6. FC 대시보드 (5개 섹션)

| 섹션 | 아이콘 | 내용 | 데이터 소스 |
|------|--------|------|------------|
| **오늘의 업무** | 체크보드 | ±7일 이내 할일 5건 + 더보기 + 밀린 업무 배너 | Task 모델 |
| **미팅 일정** | 캘린더 | 오늘 → 없으면 이번주 fallback | Meeting |
| **AI 브리핑** | 번개 | 비서 스타일 사전 브리핑, 기회/소식/리마인드 | Brief (Claude AI) |
| **Feel Lucky** | 별 | AI 발견 유망 고객 + 이유, dismiss 가능 | FortunateInsight |
| **분석 현황** | 차트 | 티어 분포 바 + 관리율 + 주의 필요 + 자동 분석 진행 표시 | Contact 집계 |

**v0.3.0 디자인 개선:**
- 모든 섹션 타이틀에 primary 색상 SVG 아이콘 통일
- AI 브리핑 카드: `bg-gray-50 border-primary/15` 강조 배경
- Feel Lucky 카드: `bg-amber-50/50` 따뜻한 추천 톤
- 빈 상태: 모든 섹션에 아이콘 + 안내 텍스트 통일
- 오늘의 업무: ±7일 필터 + 밀린 업무 별도 배너

### 7. 미팅 관리
- 미팅 생성/조회/수정/취소/**삭제**
- 연락처 상세에서 바로 미팅 예약 가능
- 미팅 상세에서 메모 작성 → Interaction 자동 연결
- 무한 스크롤 (20건씩)
- 리포트 모달: 기본 정보 즉시 + AI 분석 HTMX lazy-load (스켈레톤 UI)

### 8. AI 브리핑
- Brief 모델 (company_analysis, action_suggestion, insights JSON)
- `generate_dashboard_briefing()` — 비서 스타일 AI 브리핑 생성
- 대시보드 lazy-load (당일 캐시 → 없으면 생성)

### 9. HTMX SPA 네비게이션
- 모든 페이지 전환: HTMX `hx-get` + `hx-target="#main-content"` + `hx-push-url="true"`
- 동적 base 템플릿: `request.htmx|yesno` 분기
- 검색/필터: partial만 교체
- 바텀 네비 액티브 상태: JS URL 기반 자동 갱신

### 10. 반응형 디자인
- 모바일 (기본): max-w-md, 바텀 네비 4탭
- 데스크탑 (lg): max-w-7xl, 좌측 사이드바 네비, bg-white 콘텐츠 영역 구분
- 연락처 목록: 모바일 감정 텍스트 직접 노출, 데스크탑 tooltip

### 11. UX 개선
- **글로벌 로딩 애니메이션**: 모든 form submit + HTMX POST 버튼에 자동 스피너
- **무한 스크롤**: 연락처, 미팅, 매칭, 인터랙션 타임라인
- **모달 컨테이너**: 리포트 보기 등 팝업 UI (base.html `#modal-container`)
- **CSRF 처리**: `CSRF_TRUSTED_ORIGINS` + `SECURE_PROXY_SSL_HEADER` (nginx 프록시)
- **인라인 CRUD**: 인터랙션 수정/삭제, 할일 수정/삭제/완료 — 페이지 새로고침 없이 HTMX

---

## 인프라 & 배포

### 서버 구성

| 서버 | IP | 역할 |
|------|-----|------|
| **운영/개발** | 49.247.46.171 | synco 앱 배포 + 개발 (Docker Swarm + Nginx) |
| **DB** | 49.247.45.243 | PostgreSQL 16 + pgvector 상시 운용 |

### 포트 정책

| 포트 | 용도 | 환경 |
|------|------|------|
| **8000** | 개발 서버 (`runserver`) | 호스트 직접 실행 |
| **8080** | Docker web 컨테이너 (배포 테스트) | `docker compose --profile deploy` |
| **443/80** | 운영 (nginx → gunicorn) | Docker Swarm |

### 배포 방식
- Docker Swarm 기반, `deploy-synco.sh` 원클릭 배포
- 배포 전 `makemigrations --check` 자동 검증 + DB 백업
- Static: whitenoise (Django 직접 서빙)
- SSL: Let's Encrypt (synco.kr)
- Claude CLI: Docker 이미지에 Node.js + `@anthropic-ai/claude-code` 설치

### 개발 환경
- `docker compose up -d` → DB 컨테이너만 시작 (web은 `profiles: ["deploy"]`로 제외)
- Django: 호스트에서 직접 실행 `uv run python manage.py runserver 0.0.0.0:8000`
- 개발 DB: pgvector/pgvector:pg16 (로컬 컨테이너), 운영 DB와 분리

---

## 프로젝트 구조

```
synco/
├── main/                    # Django 프로젝트 설정
├── common/                  # 공유 유틸리티
│   ├── claude.py            # Claude CLI 호출 (call_claude, call_claude_json)
│   ├── embedding.py         # Gemini API 래퍼 (get_embedding, get_embeddings_batch)
│   └── mixins.py            # BaseModel (UUID PK + Timestamp)
├── accounts/                # 인증 + 대시보드
│   ├── models.py            # User (AbstractUser 확장, 카카오 OAuth)
│   ├── views.py             # 로그인, OAuth, FC 대시보드 5섹션, 설정, 할일 전체/밀린 업무
│   └── templates/           # 대시보드 (5섹션 파셜 + _task_card), 로그인, 역할선택
├── contacts/                # 연락처 + 접점 + 업무
│   ├── models.py            # Contact (관계 스코어링), Interaction (+import_batch, task_checked), Task (+source_interactions M2M)
│   ├── views.py             # CRUD, 검색, AI 임포트 파이프라인, 접점 CRUD, Task CRUD, AI section lazy-load
│   └── templates/           # 목록, 상세, 폼, 임포트, AI section/skeleton, 수정/삭제 폼
├── meetings/                # 미팅
│   ├── models.py            # Meeting
│   ├── views.py             # CRUD + 취소 + 삭제 + 무한 스크롤
│   └── templates/           # 목록, 상세, 폼
├── intelligence/            # AI 기능
│   ├── models.py            # Brief, Match, AnalysisJob, RelationshipAnalysis, FortunateInsight, ContactEmbedding, ImportBatch
│   ├── views.py             # 브리핑, 매칭, 리포트 모달(lazy-load), 임포트 폴링, dismiss
│   ├── services/            # 모듈별 서비스 함수 (Phase 2-3 분리)
│   │   ├── __init__.py      # re-export (기존 import 경로 호환)
│   │   ├── scoring.py       # calculate_relationship_score
│   │   ├── embedding.py     # build_contact_text, embed_contact, embed_contacts_batch
│   │   ├── sentiment.py     # classify_sentiment, classify_sentiments_batch
│   │   ├── task_detect.py   # detect_task, detect_tasks_batch
│   │   ├── similarity.py    # find_similar_contacts, find_contacts_like
│   │   ├── orchestration.py # ensure_embedding, ensure_sentiments_and_tasks, ensure_deep_analysis
│   │   ├── deep_analysis.py # generate_summary, generate_insights
│   │   ├── briefing.py      # generate_dashboard_briefing
│   │   ├── excel.py         # detect_header_and_map, classify_sheets
│   │   └── _references.py   # 레퍼런스 벡터 관리 (lazy init + 파일 캐시)
│   ├── management/commands/ # backfill_embeddings
│   └── templates/           # 브리핑, 매칭, 리포트 모달(lazy-load), 분석 폴링
├── templates/common/        # 공통 템플릿
│   ├── base.html            # 루트 레이아웃 + 모달 컨테이너 + 글로벌 로딩 핸들러
│   └── nav_*.html           # 모바일/데스크탑 네비
├── .cache/                  # 레퍼런스 벡터 캐시 (.gitignore)
└── static/
    └── manifest.json        # PWA 매니페스트
```

---

## 데이터 모델

### User (accounts)
AbstractUser 확장, UUID PK
- `kakao_id` — 카카오 OAuth 식별자
- `role` — fc / ceo
- `phone`, `company_name`, `industry`, `region`, `revenue_range`, `employee_count`

### Contact (contacts)
BaseModel (UUID + Timestamp)
- `fc` → User FK, `ceo` → User FK (nullable)
- `name`, `phone`, `company_name`, `industry`, `region`, `revenue_range`, `employee_count`, `memo`
- `last_interaction_at` — 최근 접점일
- **관계 스코어링 필드:** `relationship_score` (0-100), `relationship_tier` (gold/green/yellow/red/gray), `business_urgency_score`, `closeness_score`, `score_updated_at`
- 제약조건: UniqueConstraint(fc, phone)

### Interaction (contacts)
- `type` — call / meeting / message / memo
- `summary`, `sentiment` — positive / neutral / negative
- `import_batch` → ImportBatch FK (nullable) ✨ v0.3.0
- `task_checked` — BooleanField (할일 감지 시도 여부) ✨ v0.3.0

### Task (contacts)
- `fc` → User FK, `contact` → Contact FK (nullable)
- `title`, `due_date`, `is_completed`
- `source` — manual / ai_extracted
- `source_interactions` → Interaction M2M ✨ v0.3.0 (FK→M2M 변경)

### Meeting (meetings)
- `title`, `scheduled_at`, `scheduled_end_at`, `location`, `status`

### ContactEmbedding (intelligence) ✨ v0.3.0
- `contact` → Contact OneToOne
- `vector` — VectorField(3072) (pgvector)
- `source_text`, `source_hash` (SHA-256, 변경 감지), `model_version`

### ImportBatch (intelligence) ✨ v0.3.0
- `fc` → User FK
- `contact_count`, `interaction_count`
- `embedding_done`, `sentiment_done`, `task_done` — 단계별 완료 플래그
- `error_message`, `is_complete` (property)

### Brief (intelligence)
- `company_analysis`, `action_suggestion`, `insights` (JSONField)

### RelationshipAnalysis (intelligence)
- `contact`, `fc`, `business_signals` (JSON), `relationship_signals` (JSON)
- `ai_summary`, `extracted_tasks` (JSON), `fortunate_insights` (JSON)

### FortunateInsight (intelligence)
- `contact`, `fc`, `reason`, `signal_type`, `expires_at`, `is_dismissed`
- `unique_together = ["fc", "contact"]` ✨ v0.3.0

### Match (intelligence)
- `score`, `industry_fit`, `region_proximity`, `size_balance`, `synergy_description`

---

## AI 통합

### Claude 호출 방식
- **Claude Code CLI** (`claude --print`) subprocess 호출
- Docker 이미지에 Node.js + claude CLI 설치, 인증 파일 볼륨 마운트
- `common/claude.py`: `call_claude(prompt)`, `call_claude_json(prompt)`

### Gemini Embedding ✨ v0.3.0
- **Gemini API** (`google-genai`) — 임베딩 전용
- `common/embedding.py`: `get_embedding(text)`, `get_embeddings_batch(texts)`
- Lazy 초기화, 100건 단위 청킹, 부분 실패 시 해당 인덱스 None

### AI 기능 목록

| 기능 | 함수 | API | 상태 |
|------|------|-----|------|
| 엑셀 헤더 감지 + 컬럼 매핑 | `detect_header_and_map()` | Claude | ✅ |
| 엑셀 시트 분류 | `classify_sheets()` | Claude | ✅ |
| 연락처 임베딩 | `embed_contact()`, `embed_contacts_batch()` | Gemini | ✅ v0.3.0 |
| 감정 분류 (임베딩) | `classify_sentiment()`, `classify_sentiments_batch()` | 없음 | ✅ v0.3.0 |
| 할일 감지 (임베딩) | `detect_task()`, `detect_tasks_batch()` | 없음 | ✅ v0.3.0 |
| 유사 고객 검색 | `find_similar_contacts()` | 없음 | ✅ v0.3.0 |
| 유망 고객 추천 | `find_contacts_like()` | 없음 | ✅ v0.3.0 |
| 심층 분석 | `generate_summary()`, `generate_insights()` | Claude | ✅ v0.3.0 |
| 대시보드 AI 브리핑 | `generate_dashboard_briefing()` | Claude | ✅ |
| 순수 Python 스코어 계산 | `calculate_relationship_score()` | 없음 | ✅ |
| 비즈니스 매칭 | — | — | ⚠️ 모델만 |

### Claude vs Gemini 역할 분리
- **Gemini:** 임베딩 생성 전용 (embedding.py)
- **Claude:** 자연어 생성 전용 (deep_analysis.py, briefing.py, excel.py)

---

## 의존성

| 패키지 | 용도 |
|--------|------|
| django 5.2 | 웹 프레임워크 |
| django-htmx | HTMX 미들웨어 |
| psycopg[binary] | PostgreSQL 드라이버 |
| python-dotenv | .env 환경 변수 |
| dj-database-url | DATABASE_URL 파싱 |
| httpx | 카카오 OAuth HTTP 클라이언트 |
| django-widget-tweaks | 폼 필드 Tailwind 렌더링 |
| openpyxl | 엑셀 파싱 |
| gunicorn | 운영 WSGI 서버 |
| whitenoise | Static 파일 서빙 |
| google-genai | Gemini Embedding API ✨ v0.3.0 |
| pgvector | PostgreSQL 벡터 검색 ✨ v0.3.0 |

---

## 미구현 / 예정

| 기능 | 우선순위 | 비고 |
|------|---------|------|
| 매칭 알고리즘 | 높음 | 업종·지역·규모 기반 자동 매칭 |
| CEO 대시보드 | 중간 | 프로필 완성도, 매칭 피드, 에이전트 요청 |
| 미팅 리마인더 | 중간 | Push 알림 |
| 성과 분석 대시보드 | 중간 | 현재 placeholder |
| 전체 데이터 backfill | 높음 | `python manage.py backfill_embeddings` 운영 1회 실행 |
| CSV 임포트 | 낮음 | 현재 Excel만 지원 |
| 과금 (크레딧/구독) | 낮음 | Phase 2 |
