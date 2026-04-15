# P01: Models and App Foundation — 확정 구현계획서

> **Phase:** 1
> **선행조건:** 없음 (첫 번째 Phase)
> **산출물:** `clients`, `projects` Django 앱 + `accounts` 확장(Organization, Membership) + 전체 모델 + migration + Admin

---

## 목표

헤드헌팅 워크플로우의 데이터 기반을 구축한다. `clients`, `projects` 두 앱을 생성하고
`accounts` 앱에 Organization/Membership 모델을 추가하여 서치펌 단위 멀티테넌시를 준비한다.
전체 핵심 모델을 정의하여 migration을 완료한다.

---

## 사전 작업

### settings.py 변경

```python
# INSTALLED_APPS에 추가
"clients",
"projects",

# MEDIA 설정 추가 (FileField 사용 모델 존재)
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"
```

### urls.py MEDIA 서빙 (개발)

```python
# main/urls.py — DEBUG일 때만
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### .gitignore에 media/ 추가

---

## 앱 생성

```bash
uv run python manage.py startapp clients
uv run python manage.py startapp projects
```

---

## 모델 정의

모든 모델은 `common.mixins.BaseModel` (UUID PK + TimestampMixin) 상속.

### clients 앱

| 모델 | 필드 | 비고 |
|------|------|------|
| **Client** | `name` CharField, `industry` CharField, `size` CharField(choices: 대기업/중견/중소/외국계/스타트업), `region` CharField, `contact_persons` JSONField(default=list), `notes` TextField(blank), `organization` FK(Organization) | ~~contacts~~ → `contact_persons`으로 변경 (projects.Contact 모델과 혼동 방지) |
| **Contract** | `client` FK(Client), `start_date` DateField, `end_date` DateField(null), `terms` TextField, `status` CharField(choices: 협의중/체결/만료/해지) | 계약 이력 |
| **UniversityTier** | `name` CharField, `name_en` CharField(blank), `country` CharField(default="KR"), `tier` CharField(choices: S/A/B/C/D/E/F/해외최상위/해외상위/해외우수), `ranking` IntegerField(null) | 대학 랭킹. P12에서 초기 데이터 투입 |
| **CompanyProfile** | `name` CharField, `industry` CharField(blank), `size_category` CharField(blank), `revenue_range` CharField(blank), `preference_tier` CharField(blank), `notes` TextField(blank) | 기업 분류 DB |
| **PreferredCert** | `name` CharField(unique), `category` CharField(choices: 회계/법률/기술/어학/기타), `description` TextField(blank) | 선호 자격증 마스터 |

### projects 앱

| 모델 | 필드 | 비고 |
|------|------|------|
| **Project** | `client` FK(Client), `organization` FK(Organization), `title` CharField, `jd_text` TextField(blank), `jd_file` FileField(blank), `status` CharField(choices: 아래 참조), `assigned_consultants` M2M(User), `requirements` JSONField(default=dict), `posting_text` TextField(blank), `created_by` FK(User) | 의뢰 건 |
| **Contact** | `project` FK(Project), `candidate` FK(Candidate), `consultant` FK(User), `channel` CharField(choices: 전화/문자/카톡/이메일/LinkedIn), `contacted_at` DateTimeField, `result` CharField(choices: 응답/미응답/거절/관심/보류), `notes` TextField(blank), `locked_until` DateTimeField(null) | 컨택 이력 + 잠금 |
| **Submission** | `project` FK(Project), `candidate` FK(Candidate), `consultant` FK(User), `status` CharField(choices: 작성중/제출/통과/탈락), `document_file` FileField(blank), `submitted_at` DateTimeField(null), `client_feedback` TextField(blank) | 고객사 제출 서류 |
| **Interview** | `submission` FK(Submission), `round` PositiveSmallIntegerField, `scheduled_at` DateTimeField, `type` CharField(choices: 대면/화상/전화), `result` CharField(choices: 대기/합격/보류/탈락, default=대기), `feedback` TextField(blank) | 면접 단계 |
| **Offer** | `submission` FK(Submission, unique), `salary` CharField(blank), `position_title` CharField(blank), `start_date` DateField(null), `status` CharField(choices: 협상중/수락/거절), `terms` JSONField(default=dict) | 오퍼 조율 |
| **ProjectApproval** | `project` FK(Project), `requested_by` FK(User), `conflict_project` FK(Project, null), `status` CharField(choices: 대기/승인/합류/반려), `message` TextField(blank), `admin_response` TextField(blank), `decided_by` FK(User, null), `decided_at` DateTimeField(null) | 충돌 감지 승인 |
| **ProjectContext** | `project` FK(Project), `consultant` FK(User), `last_step` CharField(blank), `pending_action` CharField(blank), `draft_data` JSONField(default=dict) | 업무 연속성 컨텍스트 |
| **Notification** | `recipient` FK(User), `type` CharField(choices: approval_request/auto_generated/reminder/news), `title` CharField, `body` TextField, `action_url` URLField(blank), `telegram_message_id` CharField(blank), `status` CharField(choices: pending/sent/read/acted, default=pending), `callback_data` JSONField(default=dict) | 알림 시스템 |

> **SubmissionDraft는 P08로 이동.** 파이프라인 상세 설계 시 모델 확정.

> **Notification 배치:** 우선 projects 앱에 배치. 향후 알림 기능 확장 시 별도 앱 분리 검토.

### accounts 앱 확장

| 모델 | 필드 | 비고 |
|------|------|------|
| **Organization** | `name` CharField, `plan` CharField(choices: basic/standard/premium/partner), `db_share_enabled` BooleanField(default=False), `logo` **FileField**(blank) | ~~ImageField~~ → FileField (Pillow 의존성 제거) |
| **Membership** | `user` **OneToOneField**(User), `organization` FK(Organization), `role` CharField(choices: owner/consultant/viewer) | ~~FK(unique)~~ → OneToOneField |
| **TelegramBinding** | `user` OneToOneField(User), `chat_id` CharField, `is_active` BooleanField(default=True) | 텔레그램 바인딩 |

> **기존 User.company_name, industry, region, revenue_range, employee_count 필드:**
> Organization 도입 후 이 필드들은 역할이 중복됨. P01에서는 삭제하지 않고 유지.
> 데이터 마이그레이션(기존 값 → Organization)은 Organization에 실제 데이터가 쌓인 후 별도 Phase에서 처리.

### candidates 앱 확장

| 모델 | 필드 | 비고 |
|------|------|------|
| **Candidate** (기존 모델 변경) | `owned_by` FK(Organization, null=True) 추가 | DB 공유 네트워크에서 원본 소유 서치펌 추적 |

> **주의:** 기존 Candidate.projects (JSONField)와 새 projects 앱 이름이 동일.
> Python namespace 충돌은 없으나 의미 혼동 가능. 후속 Phase에서 Candidate → Project FK 관계 추가 시
> `related_name`을 명확히 지정할 것. Candidate.projects rename은 기존 코드 영향이 커서 P01 범위 밖.

### Project status choices

```python
class ProjectStatus(models.TextChoices):
    NEW = "new", "신규"
    SEARCHING = "searching", "서칭중"
    RECOMMENDING = "recommending", "추천진행"
    INTERVIEWING = "interviewing", "면접진행"
    NEGOTIATING = "negotiating", "오퍼협상"
    CLOSED_SUCCESS = "closed_success", "클로즈(성공)"
    CLOSED_FAIL = "closed_fail", "클로즈(실패)"
    CLOSED_CANCEL = "closed_cancel", "클로즈(취소)"
    ON_HOLD = "on_hold", "보류"
    PENDING_APPROVAL = "pending_approval", "승인대기"
```

---

## 권한 정책 (모델 수준만 — P01 범위)

Organization 기반 멀티테넌시. P01에서는 모델과 role 정의만 수행.
실제 view-level 권한 enforcement (데코레이터/mixin)는 P02 이후 각 CRUD 구현 시 추가.

| 기능 | SuperAdmin | Owner | Consultant | Viewer |
|------|-----------|-------|------------|--------|
| Organization 관리 | O | X | X | X |
| 직원 초대/관리 | X | O | X | X |
| 프로젝트 등록/삭제 | X | O | X | X |
| 고객사 등록/편집 | X | O | X | X |
| 후보자 등록/편집 | X | O | O | X |
| 컨택/추천 작업 | X | O | O (배정 건만) | X |

---

## Admin 등록

모든 모델을 `admin.site.register()`로 등록. `list_display`, `list_filter`, `search_fields` 설정.

- **Client:** list_display=(`name`, `industry`, `size`, `region`)
- **Project:** list_display=(`title`, `client`, `status`, `created_by`, `created_at`), list_filter=(`status`,)
- **Contact:** list_display=(`project`, `candidate`, `consultant`, `channel`, `result`, `contacted_at`)
- **Organization:** list_display=(`name`, `plan`, `db_share_enabled`)
- **Membership:** list_display=(`user`, `organization`, `role`)
- 나머지 모델도 핵심 필드 기준으로 `list_display` 설정

---

## Migration

```bash
uv run python manage.py makemigrations accounts clients projects candidates
uv run python manage.py migrate
```

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| 앱 로드 | `uv run python manage.py check` 성공 |
| Migration 적용 | `uv run python manage.py migrate` 오류 없음 |
| 모델 CRUD | Client, Project, Contact 등 기본 생성/조회 테스트 |
| Organization/Membership | Organization 생성, Membership(user+org+role) 생성, OneToOne 제약 검증 |
| Candidate.owned_by | owned_by FK 설정/조회, null 허용 확인 |
| Admin 접근 | Admin 페이지에서 모든 모델 목록/등록 화면 확인 |
| FK 관계 | Project → Client, Project → Organization 등 관계 정합성 |
| UUID PK | 모든 모델 PK가 UUID 타입인지 확인 |

> **삭제:** "권한 정책 단위 테스트" → P02 이후로 이동

---

## 산출물

- `clients/` 앱 디렉토리 (models.py, admin.py, apps.py)
- `projects/` 앱 디렉토리 (models.py, admin.py, apps.py)
- `accounts/models.py` — Organization, Membership, TelegramBinding 추가
- `candidates/` migration — Candidate.owned_by FK 추가
- `main/settings.py` — INSTALLED_APPS, MEDIA_ROOT/MEDIA_URL 추가
- `main/urls.py` — MEDIA 서빙 (DEBUG)
- Migration 파일들 (accounts, clients, projects, candidates)
- 모델 기본 CRUD 테스트

<!-- forge:p01:구현담금질:complete:2026-04-08T12:00:00+09:00 -->
