# synco 개발 기획문서

> **마스터 문서 · 단일 진실 소스 · 자립 문서**
> 작성: 2026-04-16 · 범위: 현재 코드 기준 · 스택·모델·URL·파이프라인·signal·서비스 레이어·배포
> 자매 문서: [01-business-plan.md](01-business-plan.md) · [02-work-process.md](02-work-process.md)

이 문서는 "synco가 실제로 어떻게 구현되어 있는가"를 **자립적**으로 기술한다. 외부 문서를 보지 않아도 신규 개발자가 저장소를 내려받아 개발·배포·디버깅을 시작할 수 있다. 미래 계획은 15장(완성도·잔재)과 16장(Phase 로드맵)에만 둔다.

---

## 1. 기술 스택

| 레이어 | 기술 | 비고 |
|---|---|---|
| 언어 | Python 3.13 | |
| 웹 프레임워크 | Django 5.2 | |
| 프런트 | HTMX + Django Templates + Tailwind CSS | SPA 느낌의 하이브리드 |
| 폰트 | Pretendard Variable | CDN 로드 |
| DB | PostgreSQL 16 + **pgvector** | 임베딩 저장 |
| AI — 이력서 파싱·JD 분석 | **Gemini** (Google) 1.5/2.0/3.0 flash-lite | `data_extraction` 앱이 Gemini Batch API 사용 |
| AI — 자연어 검색·대화 | **Claude API** (Anthropic) | 자연어 → ORM 필터 변환 |
| AI — 음성 | OpenAI **Whisper** STT | `/voice/transcribe/`, 사전미팅 녹음 STT |
| 패키지 관리 | **uv** | `uv.lock` 커밋 필수 |
| 린트/포맷 | **ruff** (check + format) | |
| 테스트 | pytest | `uv run pytest -v` |
| 컨테이너 | Docker Compose + Docker Swarm | |
| 리버스 프록시 | nginx | `/deploy/nginx/` |
| 로그인 | 카카오 OAuth | `accounts.backends.KakaoBackend` |
| 텔레그램 통합 | python-telegram-bot | webhook 기반 |

**AI 모델 역할 분담** — 두 LLM이 역할을 나눈다:
- **Gemini**: 대량·구조화 작업 — 이력서 batch 파싱, JD structured output, 뉴스 요약, 사전미팅 녹음 분석, SubmissionDraft 초안
- **Claude**: 대화형·문장 생성 — 자연어 검색 의도 파싱, 음성 에이전트 대화, 검색 챗봇
- **Whisper**: 음성 전사

---

## 2. 저장소 구조

```
/home/work/synco
├── accounts/                 # User·Organization·Membership·Gmail·Telegram·알림 설정
├── candidates/               # Candidate·Resume·Education/Career/Cert/Lang·검수·벡터 검색·SearchSession
├── clients/                  # Client·Contract·Reference 마스터(University/Company/Cert)
├── projects/                 # Project·Application·ActionType·ActionItem·Submission/Draft·Interview·MeetingRecord·Approval·Context·Notification·Posting·AutoAction·News·ResumeUpload + 대시보드 + views_voice + urls_telegram/news
├── data_extraction/          # GeminiBatchJob/Item — Drive 이력서 일괄 추출 파이프라인
├── common/                   # BaseModel(UUID PK + TimestampMixin), 공통 Mixin
├── main/                     # Django 프로젝트 루트 (settings, urls)
├── templates/                # 공통 base, 컴포넌트, nav
├── static/                   # Tailwind 빌드 산출물
├── assets/
│   └── ui-sample/            # 디자인 기준 HTML 목업 (단일 진실 소스)
├── synco-extension/          # Chrome 확장 (후보자 소싱) - 로드맵
├── scripts/                  # 운영 스크립트
├── deploy/
│   ├── docker-stack-synco.yml
│   └── nginx/
├── docs/
│   ├── master/               # ← 이 마스터 3종 (자립 문서)
│   ├── design-system.md
│   └── archive/              # 레거시 보관소 (언제든 삭제 가능, 마스터가 자립함)
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
| DB | 49.247.45.243 | PostgreSQL 16 상시 | `/mnt/synco-pgdata/`, 100GB 디스크 |
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

### SSH
```bash
ssh -o IdentityFile=~/.ssh/id_ed25519 chaconne@49.247.45.243  # DB
ssh -o IdentityFile=~/.ssh/id_ed25519 chaconne@49.247.46.171  # 운영 앱
```

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

| 앱 | 역할 | 주요 모델 |
|---|---|---|
| **accounts** | 사용자·조직·멤버십·OAuth·통합 설정 | User, Organization, Membership, InviteCode, TelegramBinding, TelegramVerification, EmailMonitorConfig, NotificationPreference |
| **candidates** | 후보자·이력서·검수·벡터 검색·위조 탐지 | Category, Candidate, Resume, Education, Career, Certification, LanguageSkill, ExtractionLog, SearchSession, SearchTurn, CandidateEmbedding, DiscrepancyReport, ValidationDiagnosis, CandidateComment |
| **clients** | 고객사·계약·참고 마스터 | Client, Contract, UniversityTier, CompanyProfile, PreferredCert |
| **projects** | 프로젝트·매칭·액션·추천·면접·승인·뉴스 | Project, Application, ActionType, ActionItem, Submission, SubmissionDraft, Interview, MeetingRecord, ProjectApproval, ProjectContext, Notification, PostingSite, AutoAction, NewsSource, NewsArticle, NewsArticleRelevance, ResumeUpload |
| **data_extraction** | Drive 이력서 Gemini Batch 추출 | GeminiBatchJob, GeminiBatchItem |
| **common** | 공통 Mixin (BaseModel 등) | — |

---

## 5. 도메인 모델

### 5.1 accounts

```
User (UUID PK, AbstractUser 확장)
  ├─ kakao_id (BigInt, unique, nullable)
  ├─ phone, company_name, industry, region, revenue_range, employee_count
  ├─ push_subscription (JSON)
  ├─ last_news_seen_at
  └─ Membership (1:1) → Organization
                       ├─ role: owner / consultant / viewer
                       └─ status: active / pending / rejected

Organization
  ├─ name, plan (basic/standard/premium/partner)
  ├─ db_share_enabled (bool), logo (File)
  └─ (reverse) memberships, clients, projects

InviteCode              code(8자), organization, role, max_uses, used_count, expires_at, is_active
                        → save() 오버라이드에서 8자 secure random 생성
TelegramBinding         user 1:1, chat_id, is_active, verified_at
TelegramVerification    6자리 코드 + 만료 + 시도(max 5) 블록
EmailMonitorConfig      user 1:1, gmail_credentials(BinaryField, 암호화), filter_labels/from, last_history_id
                        → encrypt/decrypt 헬퍼 (projects.services.email.crypto)
NotificationPreference  user 1:1, preferences(JSON) — 4종 × 2채널 검증
```

### 5.2 candidates

```
Category                직무 카테고리 (이력서 상위 분류)

Candidate               UUID PK, 이력서 구조화 필드 + 소유권 + 상태
  ├─ name, email, phone, birth_year, gender
  ├─ status: active / placed / inactive
  ├─ source: drive_import / manual / referral / chrome_ext / email
  ├─ total_experience_years (계산 필드)
  ├─ current_company, current_position
  ├─ salary_detail (JSON)
  ├─ validation_status, recommendation_status, consent_status
  ├─ category (FK Category), owned_by (FK Organization)
  ├─ Resume (1:N)      drive_file_id, file_name, status(pending/downloaded/text_only/structured), raw_text
  ├─ Education (1:N)   institution, major, degree, start/end_year, gpa
  ├─ Career (1:N)      company, position, start/end_date, is_current, responsibilities
  ├─ Certification (1:N)
  ├─ LanguageSkill (1:N)
  ├─ ExtractionLog     파싱 로그 + 신뢰도 태그 (source/inferred/generated)
  ├─ CandidateEmbedding (1:1)  embedding (pgvector)
  ├─ DiscrepancyReport (1:N)   위조/변조 탐지 결과 (RED/YELLOW/BLUE)
  ├─ ValidationDiagnosis       검수 진단 항목별
  └─ CandidateComment (1:N)    author + text

SearchSession           자연어 검색 대화 세션 (user, organization, query, status)
 └─ SearchTurn (1:N)    turn_number, user_input, ai_response
```

### 5.3 clients

```
Client                  name, industry, size, region, contact_persons(JSON), notes, organization(FK)
  ├─ Size: 대기업 / 중견 / 중소 / 외국계 / 스타트업
  └─ Contract (1:N)     start_date, end_date, terms, status(협의중/체결/만료/해지)

# 참고 마스터
UniversityTier          tier: SKY/SSG/JKOS/KDH/INSEOUL/SCIENCE_ELITE/REGIONAL/OVERSEAS_TOP/HIGH/GOOD
                        name, name_en, country, ranking, notes
                        unique_together (name, country)

CompanyProfile          name(unique), name_en, industry
                        size_category: 대기업/중견/중소/외국계/스타트업
                        listed: KOSPI/KOSDAQ/비상장/해외상장
                        revenue_range, employee_count_range, region

PreferredCert           name(unique), full_name
                        category: 회계재무/법률/기술엔지/IT/의료제약/무역물류/건설부동산/식품환경/어학/안전품질/기타
                        level: 상/중/하
                        aliases (JSON list) — 이력서 파싱 별칭 매칭용
```

### 5.4 projects — 핵심 도메인 (재설계 후)

synco의 가장 중요한 도메인. 3층 모델(Project · Application · ActionItem)로 headhunting workflow를 표현한다.

```
Project
  ├─ client (FK Client), organization (FK Organization)
  ├─ title, jd_text, jd_file, jd_source (upload/drive/text)
  ├─ jd_drive_file_id, jd_raw_text, jd_analysis (JSON)
  ├─ requirements (JSON)  ← JD 분석 결과가 검색 필터로 자동 세팅
  ├─ posting_text, posting_file_name
  ├─ assigned_consultants (M2M User)
  ├─ created_by (FK User)
  ├─ phase: searching / screening         ← 자동 파생 (6.1장)
  ├─ status: open / closed                ← 수동 또는 Hire signal
  ├─ result: success / fail / ""          ← closed일 때만 값
  ├─ deadline (Date), closed_at (DateTime), note (Text)
  │
  ├─ CheckConstraints:
  │    - open → closed_at IS NULL
  │    - open → result = ""
  │    - result != "" → status = closed
  └─ indexes: (phase,status) / (deadline) / (organization,status)

ActionType (DB 테이블, 관리자 페이지에서 편집)
  ├─ code (unique), label_ko
  ├─ phase (searching/screening/""), default_channel, output_kind (submission/interview/meeting/"")
  ├─ sort_order, is_active, is_protected
  ├─ description, suggests_next (JSON list of codes)
  └─ 보호된 4종: pre_meeting, submit_to_client, interview_round, confirm_hire
     (is_protected=True, on_delete=PROTECT — 참조하는 ActionItem 있으면 삭제 불가)

Application (순수 매칭 객체, 상태는 가지지 않음)
  ├─ project (FK), candidate (FK), notes
  ├─ hired_at, dropped_at, drop_reason (unfit/candidate_declined/client_rejected/other), drop_note
  ├─ created_by (FK User)
  ├─ UniqueConstraint(project, candidate)                   ← 한 조합은 하나만
  ├─ UniqueConstraint(project) WHERE hired_at IS NOT NULL    ← 프로젝트당 성사 1명
  ├─ @property is_active: dropped_at is None and hired_at is None
  ├─ @property current_state: 최신 완료 ActionItem.code → state 매핑 or matched/dropped/hired
  ├─ @property pending_actions: prefetch-aware
  └─ ApplicationQuerySet: active() / submitted() / for_project()

ActionItem (1급 업무 단위)
  ├─ application (FK CASCADE), action_type (FK PROTECT)
  ├─ title, channel (in_person/video/phone/kakao/sms/email/linkedin/other)
  ├─ scheduled_at, due_at, completed_at
  ├─ status: pending / done / skipped / cancelled
  ├─ result(text), note(text)
  ├─ assigned_to (FK User, SET_NULL), created_by (FK User, SET_NULL)
  ├─ parent_action (self FK, SET_NULL)  ← 자동 체인 추적
  ├─ ordering = [due_at, created_at]
  ├─ indexes: (application,status) / (assigned_to,status,due_at) / (action_type,status)
  └─ ActionItemQuerySet: pending() / done() / overdue() / due_soon(days) / for_user()

# Submission 계열 (추천 서류)
Submission              action_item (1:1 OneToOne via action_item FK)
                        consultant (FK User), template, document_file
                        submitted_at (ActionItem.completed_at과 동기화)
                        client_feedback, feedback_received_at
                        status 필드는 없음 — action_item에서 파생

SubmissionDraft         submission (1:1), status (6단계)
                        auto_draft_json, consultation_input, final_content_json
                        masking_config, output_format (word/pdf/hwp), output_language (ko/en)

Interview               action_item (1:1 OneToOne), round, type, result, scheduled_at, notes, feedback
                        UniqueConstraint: (action_item via application, round)

MeetingRecord           action_item (1:1 OneToOne)
                        audio_file, transcript, analysis_json, edited_json
                        status (uploaded/transcribing/analyzing/ready/applied/failed)
                        applied_at, applied_by

# 독립 모델 (재설계 영향 없음)
ProjectApproval         project, conflict_type, conflict_project, status(pending/approved/joined/rejected)
                        message, admin_response, approver
ProjectContext          project, consultant, last_step, pending_action, draft_data(JSON)
Notification            user, kind, payload(JSON), read_at
PostingSite             project, site_choice(잡코리아/사람인/인크루트/LinkedIn/원티드/캐치), posted_at, url, applicants_count, is_active
AutoAction              project, trigger_event, action_template, data, status(pending/applied/dismissed)
ResumeUpload            project(FK), file, source(upload/email/drive/chrome), status(pending/extracting/extracted/linked/duplicate/failed), candidate(FK, nullable)

# 뉴스피드
NewsSource              name, source_type(rss/blog/youtube), category(recruitment/hr/industry), url, is_active
NewsArticle             source(FK), title, url(unique), summary, tags, category, summary_status, pinned_until
NewsArticleRelevance    user(FK), article(FK), score(0~1), is_read
```

### 5.5 삭제된 모델 (재설계)

| 모델 | 처리 |
|---|---|
| `Contact` | **완전 삭제** — 연락 로그는 ActionItem이 흡수 (`channel` 필드로 이관) |
| `Offer` | **완전 삭제** — 현실에서 안 쓰임, confirm_hire ActionItem으로 충분 |
| `ProjectEvent` | 생성 안 함 — 히스토리는 ActionItem 타임라인이 대체 |

### 5.6 data_extraction

```
GeminiBatchJob
  ├─ display_name, source ("drive_resume_import")
  ├─ model_name (gemini-3.1-flash-lite-preview 등)
  ├─ status: preparing → prepared → submitted → running → succeeded/failed → ingested
  ├─ category_filter, parent_folder_id
  ├─ request_file_path, result_file_path
  ├─ gemini_file_name, gemini_batch_name
  ├─ total/successful/failed_requests
  └─ metadata(JSON), error_message

GeminiBatchItem
  ├─ job (FK), request_key, drive_file_id, file_name, category_name
  ├─ status: failed / prepared / submitted / succeeded / ingested
  ├─ raw_text_path, primary_file(JSON), other_files(JSON), filename_meta(JSON)
  ├─ response_json (파싱 결과)
  ├─ candidate (FK, SET_NULL) ← 추출 결과와 생성된 Candidate 연결
  ├─ error_message, metadata
  └─ unique_together(job, request_key)
```

---

## 6. 자동 파생과 시스템 규칙 (Signal 로직)

5장의 정적 모델 정의와 별개로, synco의 핵심은 **자동 파생**이다. 사용자가 액션을 하나 완료할 때마다 여러 signal이 자동으로 상태를 재계산한다.

### 6.1 Project.phase 자동 파생

```python
def compute_project_phase(project: Project) -> str:
    """
    - closed 프로젝트는 마지막 phase 유지
    - 활성 Application 중 submit_to_client 완료된 ActionItem이 있으면 screening
    - 없으면 searching
    """
    if project.closed_at is not None:
        return project.phase  # 종료된 프로젝트는 변경 안 함

    has_submitted_active = ActionItem.objects.filter(
        application__project=project,
        application__dropped_at__isnull=True,
        application__hired_at__isnull=True,
        action_type__code="submit_to_client",
        status=ActionItemStatus.DONE,
    ).exists()

    return ProjectPhase.SCREENING if has_submitted_active else ProjectPhase.SEARCHING
```

**재계산 트리거**:

```python
@receiver([post_save, post_delete], sender=ActionItem)
def recompute_phase_on_action(sender, instance, **kwargs):
    project = instance.application.project
    new_phase = compute_project_phase(project)
    if project.phase != new_phase:
        project.phase = new_phase
        project.save(update_fields=["phase"])

@receiver([post_save, post_delete], sender=Application)
def recompute_phase_on_application(sender, instance, **kwargs):
    project = instance.project
    new_phase = compute_project_phase(project)
    if project.phase != new_phase:
        project.phase = new_phase
        project.save(update_fields=["phase"])
```

### 6.2 Hire Signal — 자동 프로젝트 종료

```python
@receiver(post_save, sender=Application)
def on_application_hired(sender, instance, **kwargs):
    if instance.hired_at is None:
        return
    project = instance.project
    if project.closed_at is not None:
        return  # 이미 종료됨

    # 1. 프로젝트 종료
    project.closed_at = timezone.now()
    project.status = ProjectStatus.CLOSED
    project.result = ProjectResult.SUCCESS
    project.note = (project.note + f"\n[자동] {instance.candidate} 입사 확정으로 종료").strip()
    project.save(update_fields=["closed_at", "status", "result", "note"])

    # 2. 나머지 활성 Application 전원 드롭
    others = project.applications.active().exclude(id=instance.id)
    now = timezone.now()
    for other in others:
        other.dropped_at = now
        other.drop_reason = DropReason.OTHER
        other.drop_note = f"입사자({instance.candidate}) 확정으로 포지션 마감"
        other.save(update_fields=["dropped_at", "drop_reason", "drop_note"])
```

**엣지 케이스**: 이론상 한 후보자가 여러 프로젝트에서 `hired_at`이 찍힐 수 있다. v1에서는 차단 없이 `logger.warning("duplicate hire detected")` 로그만 남긴다. Application 유니크 제약(`(project, candidate)` + `(project WHERE hired_at IS NOT NULL)`)은 프로젝트당 성사 1명을 보장한다.

### 6.3 Project 상태 동기화

```python
def sync_project_status(project):
    if project.closed_at and project.status != ProjectStatus.CLOSED:
        project.status = ProjectStatus.CLOSED
    elif not project.closed_at and project.status != ProjectStatus.OPEN:
        project.status = ProjectStatus.OPEN
        project.result = ""  # open으로 되돌아가면 result 초기화
```

### 6.4 다음 액션 제안 (자동 생성 아님)

```python
def propose_next_actions(action_item: ActionItem) -> list[ActionType]:
    """
    완료된 ActionItem의 action_type.suggests_next를 읽어서
    제안할 다음 ActionType 목록 반환. UI에서 컨설턴트가 선택해 생성.
    """
    if action_item.status != ActionItemStatus.DONE:
        return []
    next_codes = action_item.action_type.suggests_next or []
    return list(ActionType.objects.filter(code__in=next_codes, is_active=True))
```

**초기 `suggests_next` 데이터**:

| 완료된 action_type | 제안 |
|---|---|
| `reach_out` | `await_reply`, `schedule_pre_meet` |
| `await_reply` | `re_reach_out`, `schedule_pre_meet` |
| `schedule_pre_meet` | `pre_meeting` |
| `pre_meeting` | `prepare_submission`, `follow_up` |
| `prepare_submission` | `submit_to_client` |
| `submit_to_client` | `await_doc_review` |
| `await_doc_review` | `receive_doc_feedback` |
| `receive_doc_feedback` | `schedule_interview`, `follow_up` |
| `schedule_interview` | `interview_round` |
| `interview_round` | `await_interview_result`, `interview_round` (2차) |
| `await_interview_result` | `confirm_hire`, `follow_up` |
| `confirm_hire` | `await_onboarding` |

### 6.5 ActionType 23종 시드

**data migration으로 주입**. Owner만 관리자 페이지에서 추가·비활성화 가능. 보호 4종은 삭제 불가.

**서칭 국면 (13)**: `search_db`, `search_external`, `reach_out`, `re_reach_out`, `await_reply`, `share_jd`, `receive_resume`, `convert_resume`, `schedule_pre_meet`, **`pre_meeting`** ⚑, `prepare_submission`, `submit_to_pm`, **`submit_to_client`** ⚑

**심사 국면 (7)**: `await_doc_review`, `receive_doc_feedback`, `schedule_interview`, **`interview_round`** ⚑, `await_interview_result`, **`confirm_hire`** ⚑, `await_onboarding`

**범용 (3)**: `follow_up`, `escalate_to_boss`, `note`

⚑ = `is_protected=True` (삭제 불가). `pre_meeting`은 MeetingRecord 출력, `submit_to_client`는 Submission 출력 및 phase 전환 트리거, `interview_round`는 Interview 출력, `confirm_hire`는 Hire signal 트리거.

---

## 7. URL 맵

### 7.1 최상위 (`main/urls.py`)

```python
path("admin/", admin.site.urls)
path("", home)                                       # 멤버십 상태에 따른 라우팅
path("dashboard/", dashboard)
path("dashboard/todo/",    dashboard_todo_partial)    # HTMX
path("dashboard/actions/", dashboard_actions)         # HTMX
path("dashboard/team/",    dashboard_team)            # HTMX
path("",             include("accounts.urls"))        # /accounts/* login/settings/invite/pending/rejected/email
path("candidates/",  include("candidates.urls"))
path("clients/",     include("clients.urls"))
path("reference/",   include("clients.urls_reference"))
path("voice/",       include("projects.urls_voice"))  # Whisper + 의도 파싱 (메인 네비 미연결, 레거시)
path("projects/",    include("projects.urls"))
path("telegram/",    include("projects.urls_telegram"))
path("org/",         include("accounts.urls_org"))
path("superadmin/",  include("accounts.urls_superadmin"))
path("news/",        include("projects.urls_news"))
```

### 7.2 사용자-대면 주요 경로

**accounts**
```
/accounts/login/                      Kakao OAuth 진입
/accounts/kakao/callback/             OAuth 콜백
/accounts/settings/                   설정 (프로필/이메일/텔레그램/알림 탭)
/accounts/invite/                     초대코드 입력
/accounts/pending/                    승인 대기
/accounts/rejected/                   거절됨
/accounts/email/connect|callback|settings|disconnect/
/org/                                 팀 관리 (Owner) — /org/members|invites|info/
/superadmin/                          수퍼 관리자
```

**candidates**
```
/candidates/                          리스트 + 자연어 검색
/candidates/<pk>/                     상세
/candidates/review/                   검수 대기열
/candidates/review/<pk>/              검수 상세 (confirm/reject)
/candidates/<pk>/comment/             댓글 (HTMX)
/candidates/search/chat/              자연어 검색 세션
```

**projects**
```
/projects/                                     리스트 (칸반/보드/테이블)
/projects/new/                                 생성
/projects/<pk>/                                상세 (탭 구조)
/projects/<pk>/edit|delete|close|reopen/
/projects/<pk>/tab/overview|search|submissions|interviews/   HTMX 탭
/projects/<pk>/analyze-jd|jd-results|drive-picker|matching/
/projects/<pk>/submissions/new/                Submission 생성
/projects/<pk>/submissions/<sub_pk>/
/projects/<pk>/submissions/<sub_pk>/(update|delete|submit|feedback|download|draft)/
/projects/<pk>/submissions/<sub_pk>/draft/(generate|consultation|consultation-audio|finalize|review|convert|preview)/
/projects/<pk>/interviews/...                  CRUD
/projects/<pk>/posting/(generate|edit|download|sites|site_add|site_update|site_delete)/
/projects/<pk>/context/(save|resume|discard)/
/projects/<pk>/auto-actions/(apply|dismiss)/
/projects/<pk>/resumes/(upload|status|process|link|discard|retry|assign)/
/projects/<pk>/candidates/add/                 Application 생성
/projects/<pk>/applications/(partial|drop|restore|hire)/
/projects/<pk>/actions/(partial|new|complete|skip|reschedule|propose-next)/
/projects/approvals/                           승인 큐 (Owner)
/projects/approvals/<pk>/(decide|cancel)/
```

**clients / reference**
```
/clients/, /clients/new/, /clients/<pk>/(edit|delete)/
/clients/<pk>/contracts/(new|update|delete)/
/reference/                           참고 마스터 인덱스 (Owner)
/reference/(universities|companies|certs)/
```

**voice (레거시, 메인 네비 미연결)**
```
/voice/transcribe|intent|preview|confirm|context|history|reset/
/voice/meeting/(upload|status|apply)/
```

**news / telegram**
```
/news/                                뉴스피드
/news/feed|mark-read/
/telegram/webhook/                    봇 웹훅
```

### 7.3 HTMX vs 일반 페이지

- **페이지 전환**: `hx-get` + `hx-target="main"` + `hx-push-url="true"`
- **폼 제출**: `hx-post` + specific target
- 대부분의 엔드포인트는 전체 페이지 래퍼 또는 partial을 선택적으로 반환 (요청 헤더 `HX-Request` 로 구분)

---

## 8. 뷰 카탈로그

### 8.1 projects/views.py (~2,960줄)

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

### 8.2 projects/views_voice.py (레거시)

Whisper + Claude 의도 파싱 10개 뷰. 메인 네비에서 제거됨. `/voice/*` 라우트는 살아있으나 사이드바에서 진입 불가 — 코드만 남은 레거시.

### 8.3 candidates/views.py

| 그룹 | 주요 뷰 |
|---|---|
| 리스트·상세 | `candidate_list`, `candidate_detail`, `comment_create` |
| 검수 | `review_list`, `review_detail`, `review_confirm`, `review_reject` |
| 검색 | `search_chat`, `chat_history`, `voice_transcribe` |

### 8.4 accounts/views.py

| 그룹 | 주요 뷰 |
|---|---|
| 진입 | `home`, `landing_page`, `kakao_login`, `kakao_callback` |
| 온보딩 | `invite_code_page`, `pending_approval_page`, `rejected_page` |
| 설정 | `settings_page`, `settings_profile`, `settings_email`, `settings_telegram`, `settings_notify` |
| Gmail | `email_connect`, `email_oauth_callback`, `email_settings`, `email_disconnect` |
| 조직 관리 | (urls_org) `org_info`, `org_members`, `org_invites`, `invite_create`, `member_approve`, `member_reject` |

### 8.5 clients/views.py

`client_list`, `client_create`, `client_detail`, `client_update`, `client_delete`, `contract_*`, 참고 마스터 뷰 (`reference_index`, `reference_universities`, `reference_companies`, `reference_certs`).

---

## 9. 템플릿 구조

```
templates/
├── common/
│   ├── base.html              메인 레이아웃 (사이드바 + 메인)
│   ├── nav_sidebar.html       9개 메뉴 (HTMX)
│   ├── nav_bottom.html        모바일 하단
│   └── components/            토스트, 빈 상태

candidates/templates/candidates/
├── candidate_list.html · detail.html · search.html
├── review_list.html · review_detail.html
└── partials/                  candidate_card_v2, comment_*, search_bar_fixed, search_content

projects/templates/projects/
├── project_list.html · project_detail.html · project_form.html
└── partials/ (50+)            kanban/board/table · 8개 탭 · Draft 6단계 · 액션 모달 · 대시보드 dash_full/actions/activity · 승인 카드 · JD picker

accounts/templates/accounts/
├── settings.html · invite_code.html · pending_approval.html · rejected_page.html · landing.html
└── partials/                  settings_profile/email/telegram/notify · org_info/members/invites

clients/templates/clients/
├── client_list.html · client_detail.html · client_form.html
├── reference_index.html
└── partials/                  contract, ref import
```

HTMX partial 렌더링이 많아 각 앱의 `templates/**/partials/`에 대부분의 UI 상태가 들어있다. `base.html`은 사이드바와 메인 컨테이너만 제공하고, 탭 전환·상세 상태는 partial 스왑으로 바뀐다.

---

## 10. 데이터 파이프라인 (구현 기준)

### 10.1 이력서 추출 (data_extraction)

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

관리 커맨드: `uv run python manage.py extract`

### 10.2 후보자 임베딩

```
Candidate 생성/수정 signal
  → 텍스트 합성(프로필+경력+학력+스킬)
  → Gemini/Claude 임베딩 호출
  → CandidateEmbedding.embedding(pgvector) 업서트
```

관리 커맨드: `generate_embeddings` (재인덱싱)

### 10.3 JD 분석 + 매칭

```
analyze_jd 뷰
  → Claude API (jd_text / jd_raw_text 입력)
  → structured JSON 출력:
     {position, level, birth_year_from/to, gender,
      min/max_experience_years, education.fields,
      certifications.preferred, keywords, industry,
      role_summary, responsibilities}
  → Project.jd_analysis, Project.requirements 저장

매칭
  → JD 임베딩 ↔ CandidateEmbedding 코사인 유사도
  → + 구조 필터 (경력연수, 학력 tier, 자격증, 지역)
  → 제외: 기존 Application, 다른 프로젝트에서 컨택 잠금된 후보자
  → 적합도 3단계 스코어링 (높음/보통/낮음)
  → Top N (기본 30) 반환
```

### 10.4 Submission Draft (6단계)

```
generate → consultation(text/audio) → finalize → masking
         → convert(Word/PDF/HWP) → preview → download
          ↓
    SubmissionDraft.status 단계별 전환
    (generated → consultation_added → finalized → masked → converted → downloaded)
```

각 단계는 HTMX 뷰로 분리되어 중간 중단·재개 가능. 완료 시 `Submission.submitted_at`과 연결된 `submit_to_client` ActionItem의 `status=done`이 세팅되어 Project.phase가 `screening`으로 전환된다.

### 10.5 Gmail 이력서 자동 수집

```
check_email_resumes 커맨드 (cron)
  → EmailMonitorConfig.get_credentials()
  → Gmail API: history_id 이후의 INBOX 메시지
  → 첨부 중 doc/docx/pdf/hwp 필터
  → ResumeUpload 생성 (status=pending, source=email)
  → 제목에 [REF-<project_id>] 또는 키워드가 있으면 프로젝트 자동 매칭
  → Gemini Batch 큐에 추가
```

### 10.6 이력서 Discrepancy 스캔

```
scan_discrepancies 커맨드
  → email/phone 기준 동일 후보자 그룹 탐지
  → 버전 간 차이 (학력·경력·자격증) diff
  → 시간 모순 (학력-나이, 경력 겹침)
  → DiscrepancyReport 생성 (RED/YELLOW/BLUE)
```

### 10.7 뉴스 피드

```
fetch_news 커맨드 (매일)
  → NewsSource 각각 RSS 파싱 (feedparser)
  → NewsArticle 생성 (url unique)
  → Gemini 요약 (summary_status)
  → 관련성 점수 계산 (NewsArticleRelevance)
     - 회사명 직접 매칭: 0.9
     - 업종 일치: 0.6
     - 키워드 교집합: 0.5~0.8
  → score ≥ 0.7 이면 사용자에게 알림
```

### 10.8 알림 파이프라인

```
이벤트 발생 (액션 완료, 피드백, 승인 요청, 뉴스 업데이트, due 임박)
  ↓
NotificationPreference 조회
  ↓
채널별 분기
 ├─ web:      Notification 모델 저장 → 대시보드/헤더 벨 아이콘
 └─ telegram: TelegramBinding 통해 봇 메시지 전송
```

---

## 11. 서비스 레이어 함수 (참조 시그니처)

`projects/services/` 및 관련 모듈의 핵심 함수들. 자동 파생과 매칭·충돌 감지의 진입점.

```python
# phase / status 파생
compute_project_phase(project: Project) -> str
sync_project_status(project: Project) -> None
propose_next_actions(action_item: ActionItem) -> list[ActionType]

# ActionItem 긴급도 & 대시보드
get_today_actions(user: User) -> list[ActionItem]              # 긴급도 스코어링
get_weekly_schedule(user: User) -> list[Interview|ActionItem]
get_pipeline_summary(user: User) -> dict                        # funnel 카운트
get_recent_activities(user: User, limit: int = 10) -> list
get_team_summary(organization: Organization) -> dict            # Owner용
get_pending_approvals(organization: Organization) -> list       # Owner용

# 후보자 매칭
calculate_candidate_fit_score(candidate: Candidate, requirements: dict) -> tuple[float, str]
                                                                # (score, level: 'high'|'medium'|'low')
build_matching_queryset(project: Project) -> QuerySet[Candidate]
extract_jd_requirements(jd_text: str, jd_file: FieldFile | None) -> dict

# 문서 생성
generate_submission_draft(project: Project, candidate: Candidate, template: str) -> SubmissionDraft
generate_posting_announcement(project: Project) -> str

# 충돌 방지
check_project_conflict(project: Project) -> tuple[str, list[Project]]
                                                                # ('high'|'medium'|'none', conflicts)
check_contact_conflict(project: Project, candidate: Candidate, consultant: User) -> tuple[bool, str, dict | None]
                                                                # (is_blocked, reason, lock_details)
auto_release_contact_lock(contact_lock) -> bool

# 이력서 파이프라인
parse_resume_file(path: Path) -> dict
parse_email_resume(email_message, attachment) -> tuple[Project | None, dict, float]
                                                                # (matched_project, candidate_data, confidence)
```

이 함수들은 views에서 호출되며, 직접 뷰 내부 로직으로 존재하기도 한다. 리팩터링 시 services 레이어로 추출이 권장된다.

---

## 12. 관리 커맨드

| 앱 | 커맨드 | 목적 |
|---|---|---|
| accounts | `seed_dev_roles` | 개발용 역할 시드 |
| candidates | `generate_embeddings` | 벡터 재인덱싱 |
| candidates | `scan_discrepancies` | 이력서 불일치 스캔 |
| candidates | `backfill_candidate_details` | 레거시 필드 채우기 |
| candidates | `backfill_reason_left` | 퇴직 이유 채우기 |
| clients | `load_reference_data` | 참고 마스터(대학·기업·자격증) 로드 |
| data_extraction | `extract` | Drive 일괄 추출 |
| projects | `seed_dummy_data` | 더미 시드 (개발) |
| projects | `check_email_resumes` | Gmail 이력서 폴링 |
| projects | `check_due_actions` | 마감 임박 액션 알림 |
| projects | `cleanup_failed_uploads` | 실패 업로드 정리 |
| projects | `send_reminders` | pending 액션 리마인더 |
| projects | `setup_telegram_webhook` | 텔레그램 웹훅 |
| projects | `fetch_news` | 뉴스 수집·요약 |
| projects | `process_meetings` | 사전미팅 녹음 분석 |

---

## 13. 개발/배포 워크플로우

### 13.1 로컬 개발

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

### 13.2 마이그레이션 규칙
- **migration 파일 = 단일 진실 소스**. 개발에서 `makemigrations` → git commit → 운영에서 `migrate`만 실행.
- 운영 DB에서 직접 ALTER 금지, `makemigrations` 금지.
- migration 파일은 반드시 git 포함. `.gitignore`에 `*/migrations/` 추가 금지.
- `RunPython`에는 반드시 `reverse_func`.
- 위험한 변경은 2단계 분리 (새 컬럼 추가 → 이전 컬럼 제거).
- `makemigrations`와 `migrate`는 하나의 작업 단위로 묶어서.

미생성 migration 확인:
```bash
uv run python manage.py makemigrations --check --dry-run
```

운영 미적용 확인:
```bash
ssh chaconne@49.247.46.171 \
  "docker exec \$(docker ps -qf name=synco_web) python manage.py showmigrations | grep '\[ \]'"
```

### 13.3 배포 (`deploy.sh`)

Docker Swarm 기반. 원클릭 파이프라인:

```
1. check_migrations   makemigrations --check --dry-run   (미생성 차단)
2. test               uv run pytest -q --create-db       (기본)
3. save               소스/템플릿/런타임 secret → /home/docker/
4. backup_db          운영 DB pg_dump 백업
5. build              앱 이미지 + nginx 이미지 빌드
6. validate           릴리스 이미지로 check --deploy, migrate
7. deploy             docker stack deploy → rolling update
```

실행:
```bash
./deploy.sh
```

### 13.4 배포 자산 배치

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

## 14. 현재 완성도 & 잔재

### 14.1 완성 (네비게이션에 노출, 메인 플로우 작동)
- Kakao 로그인 · 조직/Membership · 초대코드 · 승인 플로우
- 후보자 DB + 이력서 파싱(Gemini Batch) + 검수 + 자연어 검색 + 벡터 임베딩
- 프로젝트 CRUD + 칸반/보드/테이블 뷰 + 충돌 승인 큐
- JD 분석(Claude/Gemini) + 매칭
- Application + ActionItem + 자동 phase 파생 + 자동 체인 제안
- Submission + SubmissionDraft 6단계 파이프라인 + 면접/사전미팅
- 대시보드 + HTMX partials
- 클라이언트 CRUD + 계약 이력
- References(대학·기업·자격증)
- Newsfeed 수집·요약
- Django Admin
- 배포 파이프라인

### 14.2 부분 구현 (모델·URL은 있으나 UI/연결 미완성)
- **텔레그램**: 바인딩/인증 모델 + `urls_telegram.py` + 웹훅 수신 가능. 알림 발송 쪽 코드와 설정 탭 UX 60% 수준.
- **Gmail 모니터링**: OAuth 연결 + credentials 암호화 + `check_email_resumes` 구현됨. 필터 세부 설정 UX 60% 수준.
- **음성 에이전트**: `projects/views_voice.py` + `/voice/*` 라우트에 Whisper STT + 의도 파싱 + 사전미팅 녹음 분석이 10개 뷰로 살아 있음. **사이드바 네비게이션에서는 제거**되어 접근 경로 없음. 코드만 남은 레거시.

### 14.3 미구현 (아직 코드 없음)
- 대시보드 "🚨 오늘의 액션" 블록 (5개 쿼리 유니온 + 긴급도 스코어링; 현재 `dashboard_actions`가 유사 기능 수행하지만 5개 전체 커버 아님)
- 내 파이프라인 Funnel (6단계 세분화 시각화)
- `Notification` 모델은 있으나 drawer UI 미완
- Reports/Performance & Revenue 페이지 (ProjectFee, OrgTarget 모델 미정의)
- DB 공유 네트워크 (로드맵)
- Chrome Extension 후보자 소싱 (`synco-extension/` 폴더만 존재, 워크플로우 미연결)
- 컨택 잠금 필드(`locked_until`) — 현재 ActionItem에 `scheduled_at`만 있음

### 14.4 UI 재정리 진행 중
- `assets/ui-sample/*.html` 이 디자인 단일 진실 소스
- 모델·기능은 완성, UX/정보 구조 재정렬 단계
- 재정리 방향: 목업 먼저 완성 → 해당 화면에 필요한 데이터/뷰를 모델과 다시 매핑 → 템플릿 교체
- 디자인 토큰 규격은 `docs/design-system.md`

---

## 15. Phase 의존성 (구현 로드맵)

현재 코드는 P01~P13 + P14 부분 + P17 + P18 일부가 구현되어 있다. 미구현 확장은 아래 순서를 따른다.

```
P01 (모델 기반) ───── 모든 P의 선행
├─ P02 (Client CRUD)
├─ P03 (Project CRUD) ─── P03a (JD 분석)
│   ├─ P04 (Multi-view: 칸반/리스트/시트/캘린더)
│   └─ P05 (상세 8탭 구조)
│       ├─ P06 (컨택 관리 → ActionItem + 잠금)
│       ├─ P07 (Submission CRUD) ── P08 (AI Draft 6단계)
│       └─ P09 (Interview + Hire 자동 종료)
├─ P10 (공지 생성 + PostingSite)
├─ P11 (충돌 감지 + ProjectApproval)
├─ P12 (Reference 마스터 3개 + CSV)
├─ P13 (대시보드 진입점 + 긴급도 9단계 스코어링)
│
├─ P14 (보이스 에이전트 11 의도 + 사전미팅 녹음 분석)  [부분 구현]
├─ P15 (텔레그램 Inline Keyboard + 리마인더)          [부분 구현]
├─ P16 (업무 연속성: ProjectContext + AutoAction)
├─ P17 (뉴스피드: NewsSource/Article/Relevance)       [부분 구현]
├─ P18 (이메일·Chrome 이력서 소싱)                    [부분 구현]
└─ P19 (Chrome Extension Manifest V3)                 [미구현]
```

**Phase 요지**:

- **P01**: 전체 모델 + Organization 멀티테넌시 + Admin 등록
- **P02**: Client CRUD + HTMX 패턴 정립
- **P03**: Project CRUD + 라이프사이클 10 상태 초안 (이후 2-phase로 단순화)
- **P03a**: JD → AI 구조화 → requirements JSON → 검색 필터 자동 세팅
- **P04**: 4가지 뷰 (칸반/액션 리스트/스프레드시트/캘린더) + 긴급도 자동 분류
- **P05**: 프로젝트 상세 8탭 구조 + JD 기반 검색 필터 자동 세팅
- **P06**: 컨택 관리 (→ 재설계 후 ActionItem이 흡수) + 중복 방지 + 잠금
- **P07**: Submission CRUD + 양식 선택 + 상태 전환
- **P08**: AI 문서 6단계 파이프라인 (Generate → Consultation → Finalize → Masking → Convert → Download)
- **P09**: Interview / Offer → 재설계 후 interview_round + confirm_hire ActionItem으로 대체
- **P10**: 공지 AI 자동 생성 + PostingSite 추적
- **P11**: 같은 Client/유사 포지션 충돌 감지 → ProjectApproval 큐
- **P12**: University/Company/Cert 3개 마스터 + CSV 가져오기/내보내기 + 웹검색 자동채움
- **P13**: 대시보드를 진입점으로, 컨설턴트/Owner 분기, 긴급도 9단계 스코어링
- **P14**: 플로팅 마이크 버튼 + 11개 의도 파싱 + 멀티턴 + 컨텍스트 인식 + 사전미팅 녹음 분석
- **P15**: 텔레그램 Bot + Inline Keyboard 다단계 + 자동 리마인더
- **P16**: 업무 중단 시 자동 보존 + 재개 + Event Trigger 기반 AutoAction
- **P17**: RSS 수집 → AI 요약 → 관련성 매칭 → 대시보드 피드 + 텔레그램 발송
- **P18**: 2채널 이력서 수집 (수동 업로드 / Gmail OAuth + history 폴링)
- **P19**: Chrome Extension Manifest V3 + LinkedIn/잡코리아/사람인 DOM 파싱 + 원클릭 저장

---

## 16. 컨벤션 요약

- **Python**: ruff (format + lint) + 타입 힌트
- **UI 텍스트**: 한국어 존대말 ("등록되었습니다")
- **코드/커밋**: 영어
- **HTMX 네비**: `hx-get` + `hx-target="main"` + `hx-push-url="true"`
- **HTMX Form**: `hx-post` + specific target
- **DB**: UUID PK, `BaseModel`(TimestampMixin)
- **동일인 판정**: email/phone만 자동 병합, name 기반 병합 **금지** (동명이인 리스크)
- **빌드 일관성**: 개발과 배포는 동일 레포 소스 + 동일 Dockerfile
- **임시방편 금지**: 인라인 스타일·하드코딩은 증상 치료. 원인을 고친다.
- **uv.lock 커밋 필수**

---

## 17. 이 문서의 위치

- **사업·전략**: [01-business-plan.md](01-business-plan.md)
- **업무 프로세스**: [02-work-process.md](02-work-process.md)
- **코드·모델·배포(이 문서)**: 03-engineering-spec.md

이 세 문서는 **자립적**이다. `docs/archive/` 폴더는 과거 기록을 보존할 뿐이며, 언제든 삭제해도 마스터 3종과 현재 코드만으로 synco의 사업·업무·구현을 완전히 파악할 수 있다.

디자인 소스:
- UI 목업 (단일 진실): `assets/ui-sample/*.html`
- 디자인 토큰: `docs/design-system.md`

AI 코딩 규칙: `CLAUDE.md`
