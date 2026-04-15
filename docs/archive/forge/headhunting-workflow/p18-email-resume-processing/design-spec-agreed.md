# P18: Email & Resume Processing — Confirmed Design

> **Phase:** 18
> **선행조건:** P01 (모델 기반), P03 (프로젝트), P05 (서칭 탭), data_extraction (기존 파이프라인)
> **산출물:** 수동 이력서 업로드 + Gmail API 자동 모니터링 + 파싱→DB 등록→프로젝트 연결

---

## 목표

2단계로 이력서 수집 채널을 구축한다.

- **1단계:** 프로젝트 서칭 탭에서 드래그앤드롭 이력서 업로드 → 파싱 → 후보자 DB 등록 → 프로젝트 연결
- **2단계:** Gmail API 연동으로 이메일 첨부파일 자동 수집 → 동일 파싱 파이프라인 → 프로젝트 매칭

기존 `data_extraction` 파이프라인(`run_extraction_with_retry` with `use_integrity_pipeline=True`)을 재사용한다.

---

## URL 설계

### 1단계: 수동 업로드

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/projects/<pk>/resumes/upload/` | POST | `resume_upload` | 이력서 파일 업로드 (복수). ResumeUpload(status=pending) 생성만 수행, 즉시 반환 |
| `/projects/<pk>/resumes/process/` | POST | `resume_process_pending` | pending 레코드 처리 트리거 (동기 실행, 파일 수만큼 순차) |
| `/projects/<pk>/resumes/status/` | GET | `resume_upload_status` | 업로드 처리 상태 (HTMX polling, 현재 유저 + 프로젝트 스코프) |
| `/projects/<pk>/resumes/<resume_pk>/link/` | POST | `resume_link_candidate` | 파싱 결과 → 후보자 연결 + Contact 생성 |
| `/projects/<pk>/resumes/<resume_pk>/discard/` | POST | `resume_discard` | 파싱 결과 폐기 + 물리 파일 삭제 |
| `/projects/<pk>/resumes/<resume_pk>/retry/` | POST | `resume_retry` | 실패한 추출 재시도 (retry_count <= 3) |

### 2단계: Gmail 연동

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/email/connect/` | GET | `email_connect` | Gmail OAuth 연결 시작 (access_type=offline, prompt=consent) |
| `/email/callback/` | GET | `email_oauth_callback` | OAuth 콜백 → EmailMonitorConfig 생성 + 암호화 토큰 저장 |
| `/email/settings/` | GET/POST | `email_settings` | 모니터링 설정 (라벨/발신자 필터) |
| `/email/disconnect/` | POST | `email_disconnect` | Gmail 연결 해제 (토큰 폐기, 모니터링 중지, 기존 임포트 보존) |

### URL 인가 규칙

모든 `/projects/<pk>/` 하위 뷰:
- `request.user` → `membership.organization` == `project.organization` 검증
- `resume_pk`가 해당 project에 속하는지 검증
- 미인가 시 403 반환

모든 `/email/` 뷰:
- `@login_required`
- `request.user` 기준 EmailMonitorConfig 접근

---

## 모델

### ResumeUpload (projects 앱, BaseModel 상속)

```python
class ResumeUpload(BaseModel):
    """이력서 업로드 및 추출 추적."""

    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        DOCX = "docx", "Word (DOCX)"
        DOC = "doc", "Word (DOC)"
        # HWP deferred to future phase

    class Source(models.TextChoices):
        MANUAL = "manual", "수동 업로드"
        EMAIL = "email", "이메일"

    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        EXTRACTING = "extracting", "추출중"
        EXTRACTED = "extracted", "추출완료"
        LINKED = "linked", "후보자 연결됨"
        DUPLICATE = "duplicate", "중복"
        FAILED = "failed", "실패"
        DISCARDED = "discarded", "폐기"

    organization = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="resume_uploads",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="resume_uploads",
    )
    file = models.FileField(upload_to="resumes/uploads/")
    file_name = models.CharField(max_length=500)
    file_type = models.CharField(max_length=10, choices=FileType.choices)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    candidate = models.ForeignKey(
        "candidates.Candidate",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="resume_uploads",
    )
    extraction_result = models.JSONField(null=True, blank=True)  # opaque pipeline output snapshot
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    last_attempted_at = models.DateTimeField(null=True, blank=True)

    # Email source fields
    email_subject = models.CharField(max_length=500, blank=True)
    email_from = models.EmailField(blank=True)
    email_message_id = models.CharField(max_length=255, blank=True)
    email_attachment_id = models.CharField(max_length=255, blank=True)

    # Upload batch tracking
    upload_batch = models.UUIDField(null=True, blank=True)  # groups files from same upload action

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="resume_uploads",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "email_message_id", "email_attachment_id"],
                condition=models.Q(source="email"),
                name="unique_email_attachment_per_org",
            ),
        ]
```

**허용 상태 전이:**
```
pending → extracting
extracting → extracted | failed
extracted → linked | discarded | duplicate
failed → pending (retry, retry_count <= 3)
linked → (terminal)
discarded → (terminal, file deleted)
duplicate → linked (user confirms merge) | discarded
```

### EmailMonitorConfig (accounts 앱, BaseModel 상속)

```python
class EmailMonitorConfig(BaseModel):
    """Gmail 모니터링 설정. Organization은 user.membership.organization으로 파생."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_monitor_config",
    )
    gmail_credentials = models.BinaryField()  # Fernet-encrypted JSON blob
    is_active = models.BooleanField(default=True)
    filter_labels = models.JSONField(default=list, blank=True)
    filter_from = models.JSONField(default=list, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_history_id = models.CharField(max_length=255, blank=True)

    def set_credentials(self, credentials_dict: dict) -> None:
        """Encrypt and store OAuth2 credentials."""
        ...  # Fernet encrypt with SECRET_KEY-derived key

    def get_credentials(self) -> dict:
        """Decrypt and return OAuth2 credentials."""
        ...  # Fernet decrypt
```

**암호화:** `cryptography.fernet.Fernet` 사용. `SECRET_KEY`에서 HKDF로 32-byte 키 파생. `gmail_credentials`는 `BinaryField`로 암호화된 바이트 저장.

---

## 1단계: 수동 업로드

### 처리 아키텍처 (No Celery)

```
브라우저                  Django                    data_extraction
  │                        │                            │
  ├─ POST /upload/ ───────►│ ResumeUpload(pending) ───► │
  │ ◄── 200 + batch_id ───│                            │
  │                        │                            │
  ├─ POST /process/ ──────►│ for each pending:          │
  │   (JS auto-trigger)    │  status=extracting         │
  │                        │  extract_text() ──────────►│
  │                        │  run_extraction_with_retry()│
  │                        │  status=extracted/failed    │
  │                        │                            │
  ├─ GET /status/ ────────►│ current user + project     │
  │   (HTMX 2s poll)      │ filter by upload_batch     │
  │ ◄── partial HTML ─────│                            │
  │                        │                            │
  ├─ POST /link/ ─────────►│ atomic: identity match     │
  │                        │  create/merge Candidate    │
  │                        │  create Contact            │
  │                        │  status=linked             │
```

1. **Upload:** POST creates ResumeUpload(status=pending) per file, returns batch_id
2. **Process:** JS immediately triggers POST `/process/` which runs extraction synchronously per file
3. **Poll:** HTMX polls `/status/` every 2s filtered by upload_batch
4. **Link:** User clicks [연결] → atomic candidate matching + Contact creation

### 파일 검증

| 항목 | 제한 |
|------|------|
| 최대 크기 | 20MB per file |
| 허용 확장자 | .pdf, .docx, .doc |
| MIME 검증 | application/pdf, application/vnd.openxmlformats-officedocument.wordprocessingml.document, application/msword |
| 파서 타임아웃 | 60초 |

**HWP는 Phase 1에서 제외.** 향후 추가 시 `uv add olefile` + pyproject.toml 등록 선행.

### 텍스트 추출

기존 `data_extraction/services/text.py`의 `extract_text()` 재사용:
- PDF → PyMuPDF (fitz)
- DOCX → python-docx + LibreOffice fallback
- DOC → antiword + LibreOffice fallback

### 구조화 추출

`data_extraction/services/pipeline.py`의 `run_extraction_with_retry()` 호출:
```python
result = run_extraction_with_retry(
    raw_text=raw_text,
    file_path=file_path,
    category="upload",  # or dynamic
    filename_meta=parse_filename(file_name),
    use_integrity_pipeline=True,
    provider="gemini",
)
```

### 동일인 매칭

기존 `candidates/services/candidate_identity.py`의 `build_candidate_comparison_context()` 재사용:
- email/phone 기준 자동 매칭 (name 기반 매칭 금지)
- 매칭 시 status=duplicate, 사용자에게 확인 요청
- 미매칭 시 새 Candidate 생성

### 프로젝트 연결

후보자 연결(link) 시 `Contact` 레코드 생성:
```python
Contact.objects.create(
    project=resume_upload.project,
    candidate=candidate,
    consultant=request.user,
    result=Contact.Result.INTERESTED,  # or new value if needed
    notes=f"이력서 업로드로 추가 ({resume_upload.file_name})",
)
```

이후 후보자가 프로젝트 서칭 탭의 컨택 목록에 표시됨.

### 서칭 탭 업로드 UI

```
┌─ 서칭 탭 ─ Rayence 품질기획 ─────────────────────────┐
│  [후보자 DB 검색]  [이력서 업로드]                      │
│  ┌─ 이력서 업로드 ──────────────────────────────────┐ │
│  │  이력서 파일을 여기에 끌어다 놓으세요               │ │
│  │  또는 [파일 선택] — PDF, Word (복수 가능)          │ │
│  │                                                  │ │
│  │  업로드 현황:                                     │ │
│  │  [v] 홍길동_이력서.pdf — 추출 완료 → [연결] [폐기] │ │
│  │  [~] 김영희_resume.docx — 추출중...               │ │
│  │  [x] 박철수.doc — 추출 실패 [재시도]               │ │
│  │  [!] 이순신_이력서.pdf — 중복 (기존 후보자)        │ │
│  └──────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────┘
```

---

## 2단계: Gmail API 연동

### OAuth 연결

기존 synco의 Google OAuth 인프라 활용 (`.secrets/` 디렉토리):

```python
flow = InstalledAppFlow.from_client_secrets_file(
    SECRETS_FILE,
    scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    redirect_uri=CALLBACK_URL,
)
authorization_url, state = flow.authorization_url(
    access_type="offline",
    prompt="consent",
)
```

**토큰 관리:**
- `access_type='offline'` → refresh token 발급
- `prompt='consent'` → 재인증 시에도 refresh token 갱신
- gmail_client.py에서 access token 만료 시 자동 refresh
- refresh 실패 시: `is_active=False` 설정 + 사용자에게 재연결 알림

### 모니터링 설정 UI

Gmail 연결 상태, 모니터링 대상 라벨/발신자 필터 설정.
자동 처리 옵션: 첨부파일 추출, 프로젝트 매칭.
텔레그램 알림은 TelegramBinding 존재 시에만 표시.

### 자동 수집 파이프라인

management command + cron (`uv run python manage.py check_email_resumes`, 매 30분):

```python
# 동시 실행 방지
configs = EmailMonitorConfig.objects.filter(
    is_active=True
).select_for_update(skip_locked=True)

for config in configs:
    try:
        process_email_config(config)
    except Exception:
        logger.exception("Email check failed for user %s", config.user_id)
        continue  # never abort entire run
```

1. **Gmail API 폴링:** `history.list(startHistoryId=last_history_id)` 호출
   - history_id 만료 시: `messages.list(q=f'after:{last_checked_epoch}')` 폴백
2. **첨부파일 필터:** PDF/DOCX/DOC만 (20MB 이하)
3. **다운로드:** 첨부파일 → 임시 파일 → ResumeUpload 생성 (source=email)
   - 중복 방지: `(organization, email_message_id, email_attachment_id)` unique constraint
4. **프로젝트 매칭:**
   - 제목에 `[REF-{uuid}]` → 해당 프로젝트로 직접 매칭 (org 스코프 검증)
   - 키워드 매칭 → project=null로 저장, 사용자가 수동 연결 (자동 키워드 매칭 금지)
   - 미매칭 → project=null
5. **추출:** `run_extraction_with_retry` 호출 (1단계와 동일)
6. **알림:** 텔레그램 알림 (best-effort, non-blocking)
   - TelegramBinding 없으면 skip
   - 전송 실패 시 log + continue

### Gmail API 에러 처리

| 에러 | 대응 |
|------|------|
| 401 Unauthorized | refresh token으로 재인증 시도 → 실패 시 is_active=False |
| 404 historyId invalid | messages.list 폴백 |
| 429 Rate limit | exponential backoff (최대 5회) |
| 5xx Server error | skip config, 다음 실행에 재시도 |
| Attachment > 20MB | skip + 로그 기록 |
| Network timeout | httpx timeout 30s, skip + 로그 |

---

## 서비스 구조

| 파일 | 역할 |
|------|------|
| `projects/services/resume/uploader.py` | 파일 검증, ResumeUpload 생성, extract_text + run_extraction_with_retry 호출 |
| `projects/services/resume/linker.py` | 동일인 매칭 (candidate_identity 재사용) + Contact 생성, transaction.atomic |
| `projects/services/email/gmail_client.py` | Gmail API 래퍼 (인증, 토큰 refresh, 메시지 조회, 첨부파일 다운로드) |
| `projects/services/email/monitor.py` | 이메일 모니터링 루프 + 첨부파일 추출 + ResumeUpload 생성 |
| `projects/management/commands/check_email_resumes.py` | 이메일 체크 커맨드 (select_for_update + process loop) |
| `projects/management/commands/cleanup_failed_uploads.py` | 30일 경과 실패 업로드 정리 커맨드 |

### 상태 전이 관리

```python
ALLOWED_TRANSITIONS = {
    Status.PENDING: {Status.EXTRACTING},
    Status.EXTRACTING: {Status.EXTRACTED, Status.FAILED},
    Status.EXTRACTED: {Status.LINKED, Status.DISCARDED, Status.DUPLICATE},
    Status.FAILED: {Status.PENDING},  # retry
    Status.DUPLICATE: {Status.LINKED, Status.DISCARDED},
    Status.LINKED: set(),  # terminal
    Status.DISCARDED: set(),  # terminal
}

def transition_status(upload: ResumeUpload, new_status: str) -> None:
    """Enforce valid state transitions under transaction."""
    with transaction.atomic():
        upload = ResumeUpload.objects.select_for_update().get(pk=upload.pk)
        if new_status not in ALLOWED_TRANSITIONS.get(upload.status, set()):
            raise ValueError(f"Invalid transition: {upload.status} → {new_status}")
        upload.status = new_status
        upload.save(update_fields=["status", "updated_at"])
```

---

## 프론트엔드

| 파일 | 역할 |
|------|------|
| `static/js/resume-upload.js` | Drag & drop + 복수 파일 업로드 + process 트리거 + 진행률 |
| `projects/templates/projects/partials/resume_upload.html` | 업로드 영역 (드래그 존 + 파일 선택) |
| `projects/templates/projects/partials/resume_status.html` | 처리 상태 목록 (HTMX polling target) |
| `accounts/templates/accounts/email_settings.html` | Gmail 연동 설정 |

### resume-upload.js 흐름

```javascript
// 1. 파일 드래그 또는 선택
// 2. POST /upload/ → batch_id 반환
// 3. POST /process/ → extraction 시작 (응답 대기 불필요, fire-and-forget이면 안됨)
// 4. setInterval: GET /status/?batch=<batch_id> → HTMX swap 상태 목록
// 5. 모든 파일 처리 완료 시 polling 중단
```

---

## 파일 보존 정책

| 상황 | 물리 파일 | DB 레코드 |
|------|----------|----------|
| 정상 연결 (linked) | 보존 | 영구 보존 |
| 폐기 (discarded) | 즉시 삭제 | 영구 보존 (감사 추적) |
| 실패 (failed) | 보존 (재시도용) | 30일 후 자동 삭제 (커맨드) |
| Gmail disconnect | 보존 (이미 임포트) | 영구 보존 |

---

## 의존성

### 기존 (이미 설치됨)
- `google-api-python-client` — Gmail API
- `google-auth-oauthlib` — OAuth2
- `python-docx` — DOCX 추출
- `pymupdf` — PDF 추출

### 신규 추가 필요
- `cryptography` — Fernet 암호화 (Gmail 토큰) — `uv add cryptography` + pyproject.toml

### 미포함 (향후)
- HWP 지원: `olefile` or 별도 라이브러리, Phase 1에서 제외

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| PDF 업로드 | POST upload → process → status=extracted → link → Candidate + Contact 생성 |
| DOCX 업로드 | .docx 파일 → text.py extract_text → 구조화 추출 성공 |
| DOC 업로드 | .doc 파일 → text.py extract_text (antiword/LibreOffice) → 추출 성공 |
| 복수 파일 | 3개 파일 업로드 → 각각 독립 ResumeUpload → 각각 처리 |
| 파일 검증 | 20MB 초과 → 400 거부, 잘못된 MIME → 400 거부 |
| 중복 감지 | 기존 후보자와 email/phone 일치 → status=duplicate → 사용자 확인 |
| 프로젝트 연결 | link 시 Contact 생성 → 서칭 탭 컨택 목록에 표시 |
| 상태 전이 | 잘못된 전이 시도 → ValueError 발생 |
| 재시도 | failed → retry → pending → extracting (retry_count 증가) |
| 재시도 제한 | retry_count >= 3 → retry 거부 |
| 폐기 | discard → 물리 파일 삭제 + status=discarded |
| 인가 | 타 조직 프로젝트 접근 → 403 |
| Gmail 연결 | OAuth → 암호화 토큰 저장 → 메시지 조회 가능 |
| Gmail 토큰 refresh | access token 만료 → 자동 refresh → API 호출 성공 |
| 자동 수집 | check_email_resumes → 첨부파일 추출 + ResumeUpload 생성 |
| 이메일 중복 방지 | 동일 message_id + attachment_id → unique constraint → skip |
| cron 동시 실행 | 두 번째 cron → skip_locked → 충돌 없음 |
| history_id 만료 | 404 → messages.list 폴백 → 정상 진행 |
| 알림 | TelegramBinding 존재 시 알림, 미존재 시 skip |
| 알림 실패 | Telegram API 에러 → log + continue (core 처리 unaffected) |
| 정리 | cleanup_failed_uploads → 30일 경과 failed 레코드 + 파일 삭제 |

---

## 산출물

### 모델
- `projects/models.py` — ResumeUpload
- `accounts/models.py` — EmailMonitorConfig

### 뷰/URL
- `projects/views.py` — resume_upload, resume_process_pending, resume_upload_status, resume_link_candidate, resume_discard, resume_retry
- `projects/urls.py` — `/projects/<pk>/resumes/` 하위 URL
- `accounts/views.py` — email_connect, email_oauth_callback, email_settings, email_disconnect
- `accounts/urls.py` — `/email/` 하위 URL

### 서비스
- `projects/services/resume/uploader.py` — 업로드 처리 + 파이프라인 호출
- `projects/services/resume/linker.py` — 후보자 연결 + Contact 생성
- `projects/services/email/gmail_client.py` — Gmail API 래퍼
- `projects/services/email/monitor.py` — 이메일 모니터링
- `projects/management/commands/check_email_resumes.py` — 이메일 체크
- `projects/management/commands/cleanup_failed_uploads.py` — 실패 업로드 정리

### 프론트엔드
- `static/js/resume-upload.js` — 드래그앤드롭 업로드
- `projects/templates/projects/partials/resume_upload.html` — 업로드 UI
- `projects/templates/projects/partials/resume_status.html` — 처리 상태
- `accounts/templates/accounts/email_settings.html` — Gmail 설정

### 테스트
- 뷰 테스트 (업로드, 처리, 연결, 폐기, 재시도, 인가)
- 서비스 테스트 (uploader, linker, gmail_client, monitor)
- management command 테스트

<!-- forge:p18-email-resume-processing:설계담금질:complete:2026-04-10T15:00:00Z -->
