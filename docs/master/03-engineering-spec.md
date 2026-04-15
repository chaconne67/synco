# synco 개발 기획문서

> **마스터 문서 · 단일 진실 소스**
> 작성: 2026-04-16 · 범위: 현재 코드 기준 · 앱·모델·URL·배포를 한 문서에서 본다
> 자매 문서: [01-business-plan.md](01-business-plan.md) · [02-work-process.md](02-work-process.md)

이 문서는 "synco가 실제로 어떻게 구현되어 있는가" 만을 기술한다. 미래 계획은 12장에만 둔다. 1~11장은 **지금 레포에서 작동하는 것**이 기준이다.

---

## 1. 기술 스택

| 레이어 | 기술 | 비고 |
|---|---|---|
| 언어 | Python 3.13 | |
| 웹 프레임워크 | Django 5.2 | |
| 프런트 | HTMX + Django Templates + Tailwind CSS | SPA 느낌의 하이브리드 |
| 폰트 | Pretendard Variable | CDN 로드 |
| DB | PostgreSQL 16 + **pgvector** | 임베딩 저장 |
| AI — 파싱/문서생성 | **Gemini** (Google) — 1.5/2.0/3.0 flash-lite | `data_extraction` 에서 Gemini Batch API |
| AI — 검색·대화 | **Claude API** (Anthropic) | 자연어 → 필터 변환 |
| AI — 음성 | OpenAI **Whisper** STT | `/voice/transcribe/` |
| 패키지 | **uv** | `uv.lock` 커밋 필수 |
| 린트/포맷 | **ruff** (check + format) | |
| 테스트 | pytest | `uv run pytest -v` |
| 컨테이너 | Docker Compose + Swarm | |
| 리버스 프록시 | nginx | `/deploy/nginx/` |
| 로그인 | 카카오 OAuth | `accounts.backends.KakaoBackend` |

> **중요**: 사업계획서 6장은 "AI = Claude API"라고 표기하지만, 실제 레포에서는 이력서 구조화 파싱·문서 생성에 **Gemini Batch API**가 쓰이고, 자연어 검색·대화에 Claude가 쓰인다. 두 모델이 역할을 분담한다.

---

## 2. 저장소 구조

```
/home/work/synco
├── accounts/                 # 사용자·조직·멤버십·Gmail·Telegram·알림 설정
├── candidates/               # 후보자 + 이력서 + 검수 + 벡터 검색
├── clients/                  # 고객사 + 계약 + 참고 마스터 데이터
├── projects/                 # 프로젝트·Application·ActionItem·대시보드·뉴스피드
├── data_extraction/          # Gemini Batch 이력서 추출 파이프라인
├── common/                   # BaseModel, 공통 Mixin
├── main/                     # Django 프로젝트 루트 (settings, urls)
├── templates/                # 공통 base, 컴포넌트
├── static/                   # 빌드 산출물 (css/js)
├── assets/
│   └── ui-sample/            # 디자인 기준 HTML 목업 (SoT)
├── synco-extension/          # Chrome 확장 (후보자 소싱)
├── scripts/                  # 운영 스크립트
├── deploy/
│   ├── docker-stack-synco.yml
│   └── nginx/
├── docs/
│   ├── master/               # ← 이 마스터 3종
│   ├── design-system.md
│   ├── designs/              # UI 목업·인터랙션 플랜
│   └── archive/              # 레거시 plans/forge/inspection (과거 기록)
├── tests/
├── deploy.sh                 # 원클릭 배포 진입점
├── dev.sh                    # 개발 서버 + Tailwind watch
├── docker-compose.yml
├── Dockerfile
├── manage.py
├── pyproject.toml
├── uv.lock
├── tailwind.config.js
├── CLAUDE.md                 # AI 코딩 규칙
└── README.md
```

---

## 3. 인프라 구성

| 서버 | IP | 역할 | 비고 |
|---|---|---|---|
| 운영/개발 | 49.247.46.171 | synco 앱 배포 + 개발 | Docker Swarm + nginx |
| DB | 49.247.45.243 | PostgreSQL 상시 | `/mnt/synco-pgdata/`, 100GB 디스크 |
| 코코넛 | 49.247.38.186 | 별도 프로젝트 | **참조 금지** |

### DB
- **운영**: `postgresql://synco:<pw>@49.247.45.243:5432/synco` · PostgreSQL 16 컨테이너 · `restart: always`
- **개발**: `postgresql://synco:synco@localhost:5432/synco` · Docker Compose 로컬 컨테이너

### 포트 정책
| 포트 | 용도 |
|---|---|
| 8000 | 개발 서버 (`runserver`) — 호스트 직접 실행 |
| 8080 | Docker web 컨테이너 (배포 테스트) — `docker compose --profile deploy` |
| 443/80 | 운영 nginx → gunicorn |

**원칙**: 개발과 운영 포트는 절대 겹치지 않는다. 8000이 점유됐으면 회피하지 말고 점유 프로세스를 제거.

---

## 4. Django 앱 목록

```python
# main/settings.py
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "candidates",
    "clients",
    "projects",
    "data_extraction",
]
```

| 앱 | 역할 |
|---|---|
| **accounts** | `User`(UUID PK, AbstractUser 확장, Kakao OAuth), `Organization`, `Membership`, `InviteCode`, `TelegramBinding`, `TelegramVerification`, `EmailMonitorConfig`, `NotificationPreference` |
| **candidates** | `Category`, `Candidate`(이력서 구조화 필드 포함), `Resume`(여러 버전), `Education`/`Career`/`Certification`/`LanguageSkill`, `ExtractionLog`, `SearchSession`/`SearchTurn`, `CandidateEmbedding`(pgvector), `DiscrepancyReport`, `ValidationDiagnosis`, `CandidateComment` |
| **clients** | `Client`, `Contract`, **참고 마스터**: `UniversityTier`, `CompanyProfile`, `PreferredCert` |
| **projects** | `Project`, `Application`, `ActionType`, `ActionItem`, `Submission`/`SubmissionDraft`, `Interview`, `MeetingRecord`, `ProjectApproval`, `ProjectContext`, `Notification`, `PostingSite`, `AutoAction`, `NewsSource`/`NewsArticle`/`NewsArticleRelevance`, `ResumeUpload` |
| **data_extraction** | `GeminiBatchJob`, `GeminiBatchItem` — Drive 이력서 일괄 추출 파이프라인 추적 |
| **common** | `BaseModel`(UUID PK + TimestampMixin) 등 |

---

## 5. 도메인 모델

### 5.1 accounts

```
User (UUID PK, AbstractUser)
  ├─ kakao_id, phone, company_name, industry, region
  ├─ push_subscription (JSON)
  └─ Membership (1:1) → Organization
                       └─ role: owner / consultant / viewer
                       └─ status: active / pending / rejected

Organization
  ├─ name, plan(basic/standard/premium/partner)
  ├─ db_share_enabled, logo
  └─ (reverse) memberships, clients, projects

InviteCode            — org + role + max_uses + expires_at + is_active
TelegramBinding       — user 1:1, chat_id
TelegramVerification  — 6자리 코드, 만료, 시도 횟수(max 5)
EmailMonitorConfig    — 암호화된 Gmail OAuth credentials (BinaryField)
NotificationPreference— user 1:1, 4종×2채널 JSON
```

### 5.2 candidates

```
Category              — 직무 카테고리
Candidate             — 이력서 구조화 + owned_by(Organization) + validation/consent 상태
  ├─ Resume (1:N)     — 여러 버전, drive_file_id, status(pending/text_only/structured)
  ├─ Education (1:N)
  ├─ Career (1:N)
  ├─ Certification (1:N)
  ├─ LanguageSkill (1:N)
  ├─ ExtractionLog    — 파싱 로그/신뢰도
  ├─ CandidateEmbedding (1:1) — pgvector
  ├─ DiscrepancyReport (1:N) — 위조/변조 탐지 결과
  ├─ ValidationDiagnosis     — 검수 진단
  └─ CandidateComment (1:N)

SearchSession          — 자연어 검색 대화 세션
 └─ SearchTurn (1:N)   — 한 턴 (user 입력 + AI 응답)
```

### 5.3 clients

```
Client
  ├─ name, industry, size, region, contact_persons(JSON), notes, organization(FK)
  └─ Contract (1:N)    — start_date, end_date, terms, status

# 참고 마스터
UniversityTier         — SKY/SSG/JKOS/KDH/INSEOUL/SCIENCE_ELITE/REGIONAL/해외 3단계
CompanyProfile         — 대기업/중견/중소/외국계/스타트업, KOSPI/KOSDAQ/비상장
PreferredCert          — 카테고리 11종, level(상/중/하), aliases
```

### 5.4 projects — 핵심 도메인

FINAL-SPEC 재설계(2026-04-14)에 따른 3층 구조.

```
Project
  ├─ client (FK Client), organization (FK Organization)
  ├─ title, jd_text, jd_file, jd_source, jd_drive_file_id, jd_raw_text, jd_analysis(JSON)
  ├─ requirements(JSON), posting_text, posting_file_name
  ├─ assigned_consultants (M2M User)
  ├─ created_by (FK User)
  ├─ phase: searching / screening        ← ActionItem에서 자동 파생
  ├─ status: open / closed               ← confirm_hire 또는 수동
  ├─ result: success / fail / ""         ← closed일 때만
  ├─ deadline (Date), closed_at, note
  ├─ CheckConstraints:
  │    - open → closed_at is null
  │    - open → result = ""
  │    - result != "" → status = closed
  └─ indexes: (phase,status) / (deadline) / (organization,status)

ActionType (DB 테이블, 관리자 페이지에서 편집)
  ├─ code, label_ko, phase, default_channel, output_kind
  ├─ sort_order, is_active, is_protected
  ├─ description, suggests_next (JSON list of codes)
  └─ 보호 4개: pre_meeting, submit_to_client, interview_round, confirm_hire

Application (순수 매칭 객체)
  ├─ project (FK), candidate (FK)
  ├─ notes
  ├─ hired_at, dropped_at, drop_reason, drop_note
  ├─ created_by (FK User)
  ├─ UniqueConstraint(project, candidate)
  ├─ UniqueConstraint(project) WHERE hired_at IS NOT NULL   ← 프로젝트당 성사 1명
  ├─ @property is_active: dropped_at is None and hired_at is None
  ├─ @property current_state: 최신 완료 ActionItem.code → state 매핑 or "matched"/"dropped"/"hired"
  └─ @property pending_actions: prefetch-aware

ActionItem (1급 업무 단위)
  ├─ application (FK), action_type (FK, PROTECT)
  ├─ title, channel, scheduled_at, due_at, completed_at
  ├─ status: pending / done / skipped / cancelled
  ├─ result(text), note(text)
  ├─ assigned_to (FK User), created_by (FK User)
  ├─ parent_action (self FK, SET_NULL)  ← 자동 체인 추적
  └─ QuerySet 헬퍼: pending / done / overdue / due_soon(days) / for_user

# Submission 계열 (구조화된 서류 작성)
Submission            — ActionItem(code=submit_to_client)과 1:1
 ├─ consultant, template, document_file
 ├─ submitted_at, client_feedback, feedback_received_at
 └─ 관계: submission ← action_item (OneToOne via action_item FK)

SubmissionDraft       — Submission 1:1, 7단계 파이프라인
 ├─ status (generated/consultation/finalized/masked/converted/downloaded)
 ├─ auto_draft_json, consultation_input, final_content_json
 ├─ masking_config, output_format, output_language
 └─ OutputFormat: word/pdf/hwp · OutputLanguage: ko/en

Interview             — ActionItem(code=interview_round)과 1:1
 └─ round, type, result, scheduled_at, notes

MeetingRecord         — ActionItem(code=pre_meeting)과 1:1
 └─ file_name, transcript, analysis_status, summary

# Project 부속
ProjectApproval       — 프로젝트 충돌 시 Owner 승인 큐
 ├─ status: pending / approved / rejected
 ├─ conflict_type, reason
 └─ approver (FK User)

ProjectContext        — 프로젝트 메모/컨텍스트 스냅샷
Notification          — user, kind, payload(JSON), read_at
PostingSite           — 채용 공고 사이트 등록·해제 로그
AutoAction            — AI 제안 자동 액션 (사용자 승인 후 ActionItem으로 전환)
ResumeUpload          — 프로젝트 단위 이력서 업로드 추적 (Candidate 연결 전 단계)

# 뉴스피드
NewsSource            — 소스 URL, 타입(rss/youtube/twitter), 카테고리
NewsArticle           — 기사 본문/요약/상태, summary_status
NewsArticleRelevance  — (user, article) 페어 관련성 점수
```

### 5.5 data_extraction

```
GeminiBatchJob
  ├─ display_name, source, model_name, status (preparing→...→ingested)
  ├─ category_filter, parent_folder_id
  ├─ request_file_path, result_file_path
  ├─ gemini_file_name, gemini_batch_name
  ├─ total_requests, successful_requests, failed_requests
  └─ metadata(JSON), error_message

GeminiBatchItem
  ├─ job (FK), request_key, drive_file_id, file_name
  ├─ category_name, status
  ├─ raw_text_path, primary_file(JSON), other_files(JSON), filename_meta(JSON)
  ├─ response_json, error_message, metadata
  └─ candidate (FK, SET_NULL) ← 추출 결과와 생성된 Candidate 연결
```

---

## 6. URL 맵

### 6.1 최상위 (`main/urls.py`)

```python
path("admin/", admin.site.urls)
path("", home)                                      # 멤버십 상태에 따른 라우팅
path("dashboard/", dashboard)
path("dashboard/todo/",    dashboard_todo_partial)   # HTMX
path("dashboard/actions/", dashboard_actions)        # HTMX
path("dashboard/team/",    dashboard_team)           # HTMX
path("",             include("accounts.urls"))       # /accounts/* login/settings 등
path("candidates/",  include("candidates.urls"))
path("clients/",     include("clients.urls"))
path("reference/",   include("clients.urls_reference"))
path("voice/",       include("projects.urls_voice"))  # Whisper 전사 등 — 사이드바 메뉴엔 없음
path("projects/",    include("projects.urls"))
path("telegram/",    include("projects.urls_telegram"))
path("org/",         include("accounts.urls_org"))
path("superadmin/",  include("accounts.urls_superadmin"))
path("news/",        include("projects.urls_news"))
```

### 6.2 사용자-대면 주요 경로

**accounts**
```
/accounts/login/               — 카카오 로그인 페이지
/accounts/kakao/callback/      — OAuth 콜백
/accounts/settings/            — 설정 페이지 (프로필/이메일/텔레그램/알림 탭)
/accounts/invite/              — 초대코드 입력
/accounts/pending/             — 승인 대기
/accounts/rejected/            — 거절됨
/accounts/email/connect/       — Gmail OAuth 시작
/accounts/email/callback/      — Gmail OAuth 콜백
/accounts/email/settings/      — 모니터 필터 설정
/accounts/email/disconnect/    — 연결 해제
/org/                          — 팀 관리 (Owner)
/org/members/, /org/invites/, /org/info/
/superadmin/                   — 수퍼 관리자 영역
```

**candidates**
```
/candidates/                   — 리스트 + 자연어 검색
/candidates/<uuid:pk>/         — 상세
/candidates/review/            — 검수 대기열
/candidates/review/<uuid:pk>/  — 검수 상세 (confirm/reject)
/candidates/<uuid:pk>/comment/ — 댓글 작성 (HTMX)
/candidates/search/chat/       — 자연어 검색 세션
```

**projects**
```
/projects/                                 — 리스트 (칸반/보드/테이블)
/projects/new/                              — 생성
/projects/<uuid:pk>/                        — 상세 (탭 구조)
/projects/<uuid:pk>/edit/                   — 수정
/projects/<uuid:pk>/delete/
/projects/<uuid:pk>/close/                  — 종료
/projects/<uuid:pk>/reopen/                 — 재오픈
/projects/<uuid:pk>/tab/overview/           — HTMX 탭
/projects/<uuid:pk>/tab/search/
/projects/<uuid:pk>/tab/submissions/
/projects/<uuid:pk>/tab/interviews/
/projects/<uuid:pk>/analyze-jd/             — JD AI 분석
/projects/<uuid:pk>/jd-results/
/projects/<uuid:pk>/drive-picker/
/projects/<uuid:pk>/matching/               — 매칭 결과
/projects/<uuid:pk>/submissions/new/        — Submission 생성
/projects/<uuid:pk>/submissions/<uuid:sub_pk>/
    (update/delete/submit/feedback/download/draft/...)
/projects/<uuid:pk>/submissions/<uuid:sub_pk>/draft/generate|consultation|
    consultation-audio|finalize|review|convert|preview/
/projects/<uuid:pk>/interviews/...          — CRUD
/projects/<uuid:pk>/posting/...             — JD 게시
/projects/<uuid:pk>/context/                — 프로젝트 메모
/projects/<uuid:pk>/auto-actions/           — 자동 액션 제안
/projects/<uuid:pk>/resumes/upload|status|process/
/projects/<uuid:pk>/candidates/add/         — 후보자 추가 (Application 생성)
/projects/<uuid:pk>/applications/partial/   — HTMX
/projects/<uuid:pk>/applications/drop|restore|hire/
/projects/<uuid:pk>/actions/partial/        — HTMX
/projects/<uuid:pk>/actions/new|complete|skip|reschedule|propose-next/
/projects/approvals/                        — 승인 큐 (Owner)
/projects/approvals/<uuid>/decide/
/projects/approvals/<uuid>/cancel/
```

**clients**
```
/clients/                       — 리스트
/clients/new/                   — 생성
/clients/<uuid:pk>/             — 상세 + 계약 이력
/clients/<uuid:pk>/edit/
/clients/<uuid:pk>/contracts/...
/reference/                     — 참고 마스터 인덱스 (Owner)
/reference/universities/, /reference/companies/, /reference/certs/
```

**voice** (현재 사이드바 메뉴에 없음, 잔재)
```
/voice/transcribe/              — 음성 → 텍스트 (Whisper)
/voice/intent/                  — 의도 파싱
/voice/preview/                 — 액션 미리보기
/voice/confirm/                 — 액션 확정
/voice/context/                 — 컨텍스트 조회
/voice/history/, /voice/reset/
/voice/meeting/upload|status|apply/
```

**news / telegram**
```
/news/                          — 뉴스피드
/news/feed/, /news/mark-read/
/telegram/webhook/              — 봇 웹훅
```

### 6.3 HTMX vs 일반 페이지
- 페이지 전환: `hx-get` + `hx-target="main"` + `hx-push-url="true"`
- 폼 제출: `hx-post` + specific target
- 페이지 전체가 HTMX-native이므로 대부분의 엔드포인트가 partial을 반환

---

## 7. 뷰 카탈로그 (요약)

### 7.1 projects/views.py (~2,960줄)
| 그룹 | 주요 뷰 |
|---|---|
| 리스트·생성 | `project_list`, `project_check_collision`, `project_create` |
| 상세·탭 | `project_detail`, `project_tab_overview/search/submissions/interviews`, `project_applications_partial`, `project_timeline_partial` |
| 수정·종료 | `project_update`, `project_delete`, `project_close`, `project_reopen` |
| JD | `analyze_jd`, `jd_results`, `drive_picker`, `start_search_session`, `jd_matching_results` |
| Submission | `submission_create/update/delete/submit/feedback/download` |
| Draft 파이프라인 | `submission_draft`, `draft_generate/consultation/consultation_audio/finalize/review/convert/preview` |
| Interview | `interview_create/update/delete/result` |
| Posting | `posting_generate/edit/download/sites`, `posting_site_add/update/delete` |
| Approval | `approval_queue`, `approval_decide`, `approval_cancel` |
| 대시보드 | `dashboard`, `dashboard_actions`, `dashboard_todo_partial`, `dashboard_team` |
| 프로젝트 컨텍스트 | `project_context`, `project_context_save/resume/discard` |
| 자동 액션 | `project_auto_actions`, `auto_action_apply/dismiss` |
| Resume 업로드 | `resume_upload`, `resume_process_pending`, `resume_upload_status`, `resume_link_candidate`, `resume_discard`, `resume_retry`, `resume_unassigned`, `resume_assign_project` |
| Application | `project_add_candidate`, `application_drop/restore/hire`, `application_actions_partial` |
| ActionItem | `action_create/complete/skip/reschedule/propose_next` |

### 7.2 projects/views_voice.py
Whisper·LLM 기반 10개 뷰. 메인 네비에서는 제거되어 있어 현재는 **미연결 상태**지만 코드는 살아있다 (음성 검색 레거시).

### 7.3 candidates/views.py
| 그룹 | 주요 뷰 |
|---|---|
| 리스트·상세 | `candidate_list`, `candidate_detail`, `comment_create` |
| 검수 | `review_list`, `review_detail`, `review_confirm`, `review_reject` |
| 검색 | `search_chat`, `chat_history`, `voice_transcribe` |

### 7.4 accounts/views.py
| 그룹 | 주요 뷰 |
|---|---|
| 진입 | `home`, `landing_page`, `kakao_login`, `kakao_callback` |
| 온보딩 | `invite_code_page`, `pending_approval_page`, `rejected_page` |
| 설정 | `settings_page`, `settings_profile`, `settings_email`, `settings_telegram`, `settings_notify` |
| Gmail | `email_connect`, `email_oauth_callback`, `email_settings`, `email_disconnect` |

### 7.5 clients/views.py
`client_list`, `client_create`, `client_detail`, `client_update`, `client_delete`, `contract_*`, 참고 마스터 뷰.

---

## 8. 템플릿 구조

```
templates/
├── common/
│   ├── base.html              — 사이드바 + 메인 레이아웃
│   ├── nav_sidebar.html       — 9개 메뉴 (HTMX)
│   ├── nav_bottom.html        — 모바일 하단
│   └── components/            — 토스트, 빈 상태
candidates/templates/candidates/
├── candidate_list.html · detail.html · search.html
├── review_list.html · review_detail.html
└── partials/                  — candidate_card, chatbot, chat_messages, comment_*, search_*
projects/templates/projects/
├── project_list.html · project_detail.html · project_form.html
└── partials/ (50+)            — kanban/board/table, 탭, Draft 6단계, 액션 모달, 대시보드 dash_full/actions/activity, 승인 카드, JD picker
accounts/templates/accounts/
├── settings.html · invite_code.html · pending_approval.html · rejected_page.html · landing.html
└── partials/                  — settings_*, org_info/members/invites
clients/templates/clients/
├── client_list.html · client_detail.html · client_form.html
├── reference_index.html
└── partials/                  — contract, ref import
```

HTMX partial 렌더링이 많아 각 앱의 `templates/**/partials/`에 대부분의 UI 상태가 들어있다. `base.html`은 사이드바와 메인 컨테이너만 제공하고, 탭 전환·상세 상태는 모두 partial 스왑으로 바뀐다.

---

## 9. 데이터 파이프라인 (구현 기준)

### 9.1 이력서 추출 (data_extraction)

```
drive_folder → list files → GeminiBatchJob 생성
             → GeminiBatchItem per 파일
             → 텍스트 추출 (Python)
             → Gemini Batch 요청 파일 빌드
             → Gemini Batch API 제출
             → 주기 폴링 → 결과 다운로드
             → response_json 저장 → Candidate 업서트
             → item.status = "ingested"
```

관리 커맨드: `data_extraction/management/commands/extract.py`

### 9.2 후보자 임베딩

```
Candidate 생성/수정 signal
  → 텍스트 합성(프로필+경력+학력+스킬)
  → Gemini/Claude 임베딩 호출
  → CandidateEmbedding.embedding(pgvector) 업서트
```

관리 커맨드: `candidates/management/commands/generate_embeddings.py`

### 9.3 JD 분석 + 매칭

```
analyze_jd 뷰
  → Claude API (jd_text / jd_raw_text 입력)
  → JSON 산출물: {must_have, nice_to_have, min_years, etc}
  → Project.jd_analysis, Project.requirements 저장
매칭
  → JD 임베딩 ↔ CandidateEmbedding cosine
  → + 구조 필터 (경력연수, 학력 tier, 자격증, 지역 등)
  → 제외: 기존 Application, 다른 프로젝트 잠금
  → Top N 반환
```

### 9.4 Submission Draft (6단계)

```
generate → consultation(input/audio) → finalize → (masking)
         → convert(Word/PDF/HWP) → preview → download
          ↓
    SubmissionDraft.status 단계별 전환
```

### 9.5 Gmail 이력서 자동 수집

```
check_email_resumes 커맨드
  → EmailMonitorConfig.get_credentials()
  → Gmail API: history_id 이후의 INBOX 메시지
  → 첨부 중 doc/docx/pdf/hwp 만 필터
  → ResumeUpload 생성 (status=pending)
  → Gemini Batch 큐에 추가
```

### 9.6 이력서 Discrepancy 스캔

```
scan_discrepancies 커맨드
  → email/phone 기준 동일 후보자 그룹 탐지
  → 버전 간 차이 (학력·경력·자격증) diff
  → 시간 모순 (학력-나이, 경력 겹침)
  → DiscrepancyReport 생성 (RED/YELLOW/BLUE)
```

### 9.7 뉴스 피드

```
fetch_news 커맨드
  → NewsSource 각각 크롤 (RSS/URL)
  → NewsArticle 생성
  → Gemini 요약 (summary_status)
  → 관련성 스코어 (NewsArticleRelevance)
```

---

## 10. 관리 커맨드

| 앱 | 커맨드 | 목적 |
|---|---|---|
| accounts | `seed_dev_roles` | 개발용 역할 시드 |
| candidates | `generate_embeddings` | 벡터 재인덱싱 |
| candidates | `scan_discrepancies` | 이력서 불일치 스캔 |
| candidates | `backfill_candidate_details` | 레거시 필드 채우기 |
| candidates | `backfill_reason_left` | 퇴직 이유 채우기 |
| clients | `load_reference_data` | 참고 마스터 로드 |
| data_extraction | `extract` | Drive 일괄 추출 |
| projects | `seed_dummy_data` | 더미 시드 |
| projects | `check_email_resumes` | Gmail 이력서 폴링 |
| projects | `check_due_actions` | 마감 임박 액션 알림 |
| projects | `cleanup_failed_uploads` | 실패 업로드 정리 |
| projects | `send_reminders` | pending 액션 리마인더 |
| projects | `setup_telegram_webhook` | 텔레그램 웹훅 |
| projects | `fetch_news` | 뉴스 수집·요약 |
| projects | `process_meetings` | 사전미팅 녹음 분석 |

---

## 11. 개발/배포 워크플로우

### 11.1 로컬 개발

```bash
# DB만 docker로
docker compose up -d         # web은 profile=deploy 이므로 안 뜸

# Django는 호스트에서
./dev.sh                      # runserver + tailwind watch 동시 실행
# 포트 8000 고정. 점유되면 프로세스 제거

# 마이그레이션
uv run python manage.py makemigrations
uv run python manage.py migrate

# 테스트
uv run pytest -v
uv run pytest -q --create-db

# 린트/포맷
uv run ruff check .
uv run ruff format .
```

### 11.2 마이그레이션 규칙
- migration 파일 = 단일 진실 소스. 개발에서 `makemigrations` → git commit → 운영에서 `migrate` 만 실행.
- 운영 DB에서 직접 ALTER 금지, `makemigrations` 금지.
- migration 파일은 반드시 git 포함. `.gitignore`에 `*/migrations/` 추가 금지.
- `RunPython`에는 반드시 `reverse_func`.
- 위험한 변경은 2단계 분리 (새 컬럼 → 이전 컬럼 제거).
- makemigrations와 migrate는 하나의 작업 단위로 묶어서.

미생성 migration 확인:
```bash
uv run python manage.py makemigrations --check --dry-run
```

운영 미적용 확인:
```bash
ssh chaconne@49.247.46.171 "docker exec \$(docker ps -qf name=synco_web) python manage.py showmigrations | grep '\[ \]'"
```

### 11.3 배포 (`deploy.sh`)

Docker Swarm 기반. 파이프라인:

```
1. check_migrations   makemigrations --check --dry-run   (미생성 차단)
2. test               uv run pytest -q --create-db       (기본)
3. save               현재 소스/템플릿/런타임 secret → /home/docker/
4. backup_db          운영 DB pg_dump 백업
5. build              앱 이미지 + nginx 이미지 빌드
6. validate           릴리스 이미지로 check --deploy, migrate
7. deploy             docker stack deploy → rolling update
```

실행:
```bash
./deploy.sh
```

### 11.4 배포 자산 배치

```
# 레포 (SoT)
deploy.sh
deploy/docker-stack-synco.yml
deploy/nginx/{Dockerfile,nginx.conf}

# 운영 서버 (49.247.46.171)
/home/docker/synco/
├── .env.prod            # 운영 환경변수
├── .secrets/            # Google OAuth 등
├── .claude/             # Claude CLI auth sync
├── .claude.json
├── runtime/logs/
└── src/                 # deploy 시 rsync로 복사되는 현재 소스
/home/docker/nginx/{Dockerfile,nginx.conf}
/home/docker/docker-stack-synco.yml
```

---

## 12. 현재 완성도 & 잔재

### 12.1 완성 (네비게이션에 노출, 메인 플로우에서 작동)
- Kakao 로그인 · 조직/Membership · 초대코드 · 승인 플로우
- 후보자 DB + 이력서 파싱(Gemini Batch) + 검수 + 자연어 검색 + 벡터 임베딩
- 프로젝트 CRUD + 칸반/보드/테이블 뷰 + 충돌 승인 큐
- JD 분석(Claude) + 매칭
- Application + ActionItem + 자동 phase 파생 + 자동 체인 제안
- Submission + SubmissionDraft 6단계 파이프라인 + 면접/사전미팅
- 대시보드(현재 버전) + 대시보드 HTMX partials
- 클라이언트 CRUD + 계약 이력
- References(대학·기업·자격증)
- Newsfeed 수집·요약
- Django Admin
- 배포 파이프라인

### 12.2 부분 구현 (모델·URL은 있으나 UI/연결 미완성)
- **텔레그램**: 바인딩/인증 모델과 `urls_telegram.py` 존재, 봇 웹훅 수신은 가능. 단, 알림 발송 쪽 코드와 설정 탭의 UX가 60% 수준.
- **Gmail 모니터링**: OAuth 연결·credentials 암호화·`check_email_resumes` 커맨드 구현됨. 필터 세부 설정 UX 60% 수준.
- **음성 에이전트**: `projects/views_voice.py`와 `/voice/*` 라우트에 Whisper STT + 의도 파싱 + 사전미팅 녹음 분석이 10개 뷰로 살아 있음. **사이드바 네비게이션에서는 제거**되어 접근 경로 없음. 코드만 남아있는 레거시.

### 12.3 미구현 (문서에 있으나 아직 코드 없음)
- 대시보드 "🚨 오늘의 액션" 블록 (5개 쿼리 유니온 + 긴급도 스코어링 — 현재 `dashboard_actions`가 유사한 일을 하지만 P13 명세와 완전히 일치하지 않음)
- 내 파이프라인 Funnel (5단계 이상 세분화)
- `Notification` 모델은 있으나 drawer UI 미완
- 리포트 페이지 (performance, revenue, ProjectFee, OrgTarget)
- DB 공유 네트워크 (Phase 2 로드맵)
- Chrome Extension 후보자 소싱 (`synco-extension/` 폴더만 있음, 워크플로우 미연결)

### 12.4 디자인 재정리 진행
- `assets/ui-sample/*.html` 이 디자인 단일 진실 소스
- 현재 서비스 UI는 이 목업 기준으로 **재정리가 필요한 상태** — 모델과 기능은 완성이지만 UX/정보 구조가 마음에 안 듦
- 재정리 방향: 목업 먼저 완성 → 해당 화면에 필요한 데이터/뷰를 모델과 다시 매핑 → 템플릿 교체
- 대시보드 인터랙션 플랜: `docs/designs/dashboard-interaction-plan.md`

---

## 13. 컨벤션 요약

- **Python**: ruff(format + lint) + 타입 힌트
- **UI 텍스트**: 한국어 존대말 ("등록되었습니다")
- **코드/커밋**: 영어
- **HTMX 네비**: `hx-get` + `hx-target="main"` + `hx-push-url="true"`
- **HTMX Form**: `hx-post` + specific target
- **DB**: UUID PK, `BaseModel`(TimestampMixin)
- **동일인 판정**: email/phone만 자동 병합, name 기반 병합 금지
- **빌드 일관성**: 개발과 배포는 동일 레포 소스 + 동일 Dockerfile
- **임시방편 금지**: 인라인 스타일·하드코딩은 증상 치료. 원인을 고친다.
- **uv.lock 커밋 필수**

---

## 14. 참조

- 사업 전략: [01-business-plan.md](01-business-plan.md)
- 업무 흐름: [02-work-process.md](02-work-process.md)
- 디자인 시스템: `docs/design-system.md`
- UI 목업: `assets/ui-sample/*.html`
- 대시보드 인터랙션 원본(히스토리): `docs/archive/designs/dashboard-interaction-plan.md`
- Phase × Application 재설계 스펙 원본(히스토리): `docs/archive/designs/20260414-project-application-redesign/FINAL-SPEC.md` — 내용 요지는 이 문서 5.4절과 `02-work-process.md` 6장에 이미 녹여져 있다
- AI 코딩 규칙: `CLAUDE.md`

이전의 `docs/plans/headhunting-workflow/P01~P19.md`, forge 기록, inspection 보고서, reviews, Project/Application 재설계 논의 과정은 모두 `docs/archive/` 로 이동되어 과거 기록으로 보존된다. 현재 시점의 단일 진실 소스는 이 마스터 3종이다.
