# P18: Email & Resume Processing

> **Phase:** 18
> **선행조건:** P01 (모델 기반), P03 (프로젝트), P05 (서칭 탭), data_extraction (기존 파이프라인)
> **산출물:** 수동 이력서 업로드 + Gmail API 자동 모니터링 + 파싱→DB 등록→프로젝트 연결

---

## 목표

2단계로 이력서 수집 채널을 구축한다. 1단계는 프로젝트 서칭 탭에서 드래그앤드롭
이력서 업로드, 2단계는 Gmail API 연동으로 이메일 첨부파일 자동 수집.
기존 data_extraction 파이프라인을 재사용하여 파싱 후 후보자 DB에 자동 등록한다.

---

## URL 설계

### 1단계: 수동 업로드

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/projects/<pk>/resumes/upload/` | POST | `resume_upload` | 이력서 파일 업로드 (복수) |
| `/projects/<pk>/resumes/status/` | GET | `resume_upload_status` | 업로드 처리 상태 (HTMX polling) |
| `/projects/<pk>/resumes/<resume_pk>/link/` | POST | `resume_link_candidate` | 파싱 결과 → 후보자 연결 |
| `/projects/<pk>/resumes/<resume_pk>/discard/` | POST | `resume_discard` | 파싱 결과 폐기 |

### 2단계: Gmail 연동

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/email/connect/` | GET | `email_connect` | Gmail OAuth 연결 시작 |
| `/email/callback/` | GET | `email_oauth_callback` | OAuth 콜백 |
| `/email/settings/` | GET/POST | `email_settings` | 모니터링 설정 |
| `/email/disconnect/` | POST | `email_disconnect` | Gmail 연결 해제 |

---

## 모델 (projects 앱)

### ResumeUpload

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `project` | FK → Project null | 연결된 프로젝트 (없으면 독립 업로드) |
| `file` | FileField | 업로드된 파일 |
| `file_name` | CharField | 원본 파일명 |
| `file_type` | CharField | pdf / docx / hwp |
| `source` | CharField choices | manual / email |
| `status` | CharField choices | 처리 상태 |
| `candidate` | FK → Candidate null | 파싱 후 연결된 후보자 |
| `extraction_result` | JSONField null | data_extraction 파싱 결과 |
| `email_subject` | CharField blank | 이메일 제목 (email 소스) |
| `email_from` | EmailField blank | 발신자 (email 소스) |
| `email_message_id` | CharField blank | Gmail 메시지 ID (중복 방지) |
| `created_by` | FK → User null | 업로드한 사용자 |
| `created_at` / `updated_at` | DateTimeField | 타임스탬프 |

```python
class UploadStatus(models.TextChoices):
    PENDING = "pending", "대기"
    EXTRACTING = "extracting", "추출중"
    EXTRACTED = "extracted", "추출완료"
    LINKED = "linked", "후보자 연결됨"
    DUPLICATE = "duplicate", "중복"
    FAILED = "failed", "실패"
    DISCARDED = "discarded", "폐기"
```

### EmailMonitorConfig (accounts 앱)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `user` | OneToOne → User | 사용자 |
| `gmail_credentials` | JSONField | OAuth2 토큰 (암호화 저장) |
| `is_active` | BooleanField | 모니터링 활성 여부 |
| `filter_labels` | JSONField default=list | 모니터링 대상 라벨 |
| `filter_from` | JSONField default=list | 모니터링 대상 발신자 |
| `last_checked_at` | DateTimeField null | 마지막 체크 시각 |
| `last_history_id` | CharField blank | Gmail 히스토리 ID (증분 폴링) |

---

## 1단계: 수동 업로드

### 서칭 탭 업로드 UI

```
┌─ 서칭 탭 ─ Rayence 품질기획 ─────────────────────────┐
│  [후보자 DB 검색]  [이력서 업로드]                      │
│  ┌─ 이력서 업로드 ──────────────────────────────────┐ │
│  │  📎 이력서 파일을 여기에 끌어다 놓으세요            │ │
│  │  또는 [파일 선택] — PDF, Word, HWP (복수 가능)    │ │
│  │                                                  │ │
│  │  업로드 현황:                                     │ │
│  │  ✅ 홍길동_이력서.pdf — 추출 완료 → [연결] [폐기]  │ │
│  │  ⏳ 김영희_resume.docx — 추출중...                 │ │
│  │  ❌ 박철수.hwp — 추출 실패 [재시도]                │ │
│  │  ⚠️ 이순신_이력서.pdf — 중복 (기존 후보자 존재)    │ │
│  └──────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────┘
```

### 처리 파이프라인

1. 파일 업로드 → ResumeUpload 생성 (status=pending)
2. data_extraction 파이프라인 호출 (기존 services/pipeline.py 재사용) → text 추출 → Gemini 구조화 → integrity 검증
3. 추출 완료 (status=extracted, extraction_result 저장)
4. 동일인 체크 (email/phone 기준) → 신규면 Candidate 생성, 중복이면 사용자 확인 요청
5. status=linked, candidate FK 설정

HTMX polling: `/projects/<pk>/resumes/status/`를 2초 간격으로 폴링하여 상태 갱신.

### 파일 포맷 지원

| 포맷 | 텍스트 추출 | 비고 |
|------|-----------|------|
| PDF | 기존 data_extraction/services/text.py | pdfplumber |
| Word (.docx) | python-docx | 신규 추가 |
| HWP | pyhwp 또는 olefile | 신규 추가 |

Word/HWP 추출: `data_extraction/services/text.py`에 포맷별 추출 함수 추가.

---

## 2단계: Gmail API 연동

### OAuth 연결

기존 synco의 Google OAuth 인프라 활용 (`.secrets/` 디렉토리):

```
Gmail 설정 페이지 → [Gmail 연결] 클릭
  → Google OAuth 동의 화면 (gmail.readonly 스코프)
  → 콜백 → EmailMonitorConfig 생성 + 토큰 저장
```

### 모니터링 설정 UI

Gmail 연결 상태 표시, 모니터링 대상 라벨/발신자 필터 설정, 자동 처리 옵션(첨부파일 추출, 프로젝트 매칭, 텔레그램 알림) 체크박스.

### 자동 수집 파이프라인

management command + cron (`uv run python manage.py check_email_resumes`, 매 30분):

1. Gmail API 새 메시지 폴링 (history_id 기반 증분)
2. 첨부파일 필터 (PDF/DOCX/HWP) → 다운로드 → ResumeUpload 생성 (source=email)
3. 프로젝트 매칭: 제목에 `[REF-{id}]` → 직접 매칭, 키워드 → 프로젝트 비교, 미매칭 → 수동 연결
4. data_extraction 파이프라인 (1단계와 동일)
5. 완료 시 텔레그램 알림 (P15 연동)

---

## 서비스 구조

| 파일 | 역할 |
|------|------|
| `projects/services/resume/uploader.py` | 파일 업로드 처리 + 파이프라인 호출 |
| `projects/services/resume/linker.py` | 추출 결과 → 후보자 연결 (동일인 체크) |
| `projects/services/email/gmail_client.py` | Gmail API 래퍼 (인증, 메시지 조회, 첨부파일 다운로드) |
| `projects/services/email/monitor.py` | 이메일 모니터링 + 첨부파일 추출 |
| `projects/services/email/matcher.py` | 이메일 → 프로젝트 매칭 |
| `data_extraction/services/text.py` | Word/HWP 텍스트 추출 추가 |
| `projects/management/commands/check_email_resumes.py` | 이메일 체크 커맨드 |

---

## 프론트엔드

| 파일 | 역할 |
|------|------|
| `static/js/resume-upload.js` | Drag & drop + 복수 파일 업로드 + 진행률 |
| `projects/templates/projects/partials/resume_upload.html` | 업로드 영역 |
| `projects/templates/projects/partials/resume_status.html` | 처리 상태 목록 (HTMX polling) |
| `accounts/templates/accounts/email_settings.html` | Gmail 연동 설정 |

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| PDF 업로드 | 파일 업로드 → 추출 → 후보자 생성 |
| Word 업로드 | .docx 파일 → 텍스트 추출 → 파싱 |
| HWP 업로드 | .hwp 파일 → 텍스트 추출 → 파싱 |
| 복수 파일 | 3개 파일 동시 업로드 → 각각 처리 |
| 중복 감지 | 기존 후보자와 email/phone 일치 시 경고 |
| 프로젝트 연결 | 파싱된 후보자 → 프로젝트 서칭 목록에 추가 |
| 처리 상태 | pending → extracting → extracted → linked 전환 |
| Gmail 연결 | OAuth → 토큰 저장 → 메시지 조회 가능 |
| 자동 수집 | check_email_resumes → 첨부파일 추출 + ResumeUpload 생성 |
| 프로젝트 매칭 | 이메일 제목 키워드 → 프로젝트 매칭 |
| 텔레그램 알림 | 자동 수집 완료 시 알림 발송 |
| 실패 처리 | 파싱 실패 시 status=failed + 재시도 가능 |

---

## 산출물

- `projects/models.py` — ResumeUpload 모델
- `accounts/models.py` — EmailMonitorConfig 모델
- `projects/views.py` — 업로드 + 상태 + 연결 뷰
- `projects/urls.py` — `/projects/<pk>/resumes/`, `/email/` URL
- `projects/services/resume/uploader.py` — 업로드 처리
- `projects/services/resume/linker.py` — 후보자 연결
- `projects/services/email/gmail_client.py` — Gmail API 래퍼
- `projects/services/email/monitor.py` — 이메일 모니터링
- `projects/services/email/matcher.py` — 프로젝트 매칭
- `data_extraction/services/text.py` — Word/HWP 추출 추가
- `projects/management/commands/check_email_resumes.py` — 이메일 체크 커맨드
- `static/js/resume-upload.js` — 드래그앤드롭 업로드
- `projects/templates/projects/partials/resume_upload.html` — 업로드 UI
- `projects/templates/projects/partials/resume_status.html` — 처리 상태
- `accounts/templates/accounts/email_settings.html` — Gmail 설정
- 테스트 파일
