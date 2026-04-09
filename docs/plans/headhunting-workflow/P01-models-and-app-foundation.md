# P01: Models and App Foundation

> **Phase:** 1 / 6
> **선행조건:** 없음 (첫 번째 페이즈)
> **산출물:** `clients`, `projects` Django 앱 + `accounts` 확장(Organization, Membership) + 전체 모델 + migration + Admin

---

## 목표

헤드헌팅 워크플로우의 데이터 기반을 구축한다. `clients`, `projects` 두 앱을 생성하고
`accounts` 앱에 Organization/Membership 모델을 추가하여 서치펌 단위 멀티테넌시와 역할 분리를 구현한다.
설계 문서의 전체 모델을 정의하여 migration을 완료한다.

---

## 앱 생성

```bash
uv run python manage.py startapp clients
uv run python manage.py startapp projects
```

`settings.py` INSTALLED_APPS에 `clients`, `projects` 추가.

---

## 모델 정의

모든 모델은 `common.mixins.BaseModel` (UUID PK + TimestampMixin) 상속.

### clients 앱

| 모델 | 필드 | 비고 |
|------|------|------|
| **Client** | `name` CharField, `industry` CharField, `size` CharField(choices: 대기업/중견/중소/외국계/스타트업), `region` CharField, `contacts` JSONField(default=list), `notes` TextField(blank), `organization` FK(Organization) | 고객사 기본 정보. organization으로 소속 서치펌 추적 |
| **Contract** | `client` FK(Client), `start_date` DateField, `end_date` DateField(null), `terms` TextField, `status` CharField(choices: 협의중/체결/만료/해지) | 계약 이력 |
| **UniversityTier** | `name` CharField, `name_en` CharField(blank), `country` CharField(default="KR"), `tier` CharField(choices: S/A/B/C/D/E/F/해외최상위/해외상위/해외우수), `ranking` IntegerField(null) | 대학 랭킹 분류 |
| **CompanyProfile** | `name` CharField, `industry` CharField(blank), `size_category` CharField(blank), `revenue_range` CharField(blank), `preference_tier` CharField(blank), `notes` TextField(blank) | 기업 분류 DB |
| **PreferredCert** | `name` CharField(unique), `category` CharField(choices: 회계/법률/기술/어학/기타), `description` TextField(blank) | 선호 자격증 마스터 |

### projects 앱

| 모델 | 필드 | 비고 |
|------|------|------|
| **Project** | `client` FK(Client), `organization` FK(Organization), `title` CharField, `jd_text` TextField(blank), `jd_file` FileField(blank), `status` CharField(choices: 아래 참조), `assigned_consultants` M2M(User), `requirements` JSONField(default=dict), `posting_text` TextField(blank), `created_by` FK(User) | 의뢰 건 — 시스템 중심 엔티티. organization으로 소속 서치펌 추적 |
| **Contact** | `project` FK(Project), `candidate` FK(Candidate), `consultant` FK(User), `channel` CharField(choices: 전화/문자/카톡/이메일/LinkedIn), `contacted_at` DateTimeField, `result` CharField(choices: 응답/미응답/거절/관심/보류), `notes` TextField(blank), `locked_until` DateTimeField(null) | 컨택 이력 + 잠금 |
| **Submission** | `project` FK(Project), `candidate` FK(Candidate), `consultant` FK(User), `status` CharField(choices: 작성중/제출/통과/탈락), `document_file` FileField(blank), `submitted_at` DateTimeField(null), `client_feedback` TextField(blank) | 고객사 제출 서류 |
| **Interview** | `submission` FK(Submission), `round` PositiveSmallIntegerField, `scheduled_at` DateTimeField, `type` CharField(choices: 대면/화상/전화), `result` CharField(choices: 대기/합격/보류/탈락, default=대기), `feedback` TextField(blank) | 면접 단계 |
| **Offer** | `submission` FK(Submission, unique), `salary` CharField(blank), `position_title` CharField(blank), `start_date` DateField(null), `status` CharField(choices: 협상중/수락/거절), `terms` JSONField(default=dict) | 오퍼 조율 |
| **ProjectApproval** | `project` FK(Project), `requested_by` FK(User), `conflict_project` FK(Project, null), `status` CharField(choices: 대기/승인/합류/반려), `message` TextField(blank), `admin_response` TextField(blank), `decided_by` FK(User, null), `decided_at` DateTimeField(null) | 충돌 감지 승인 |
| **ProjectContext** | `project` FK(Project), `consultant` FK(User), `last_step` CharField(blank), `pending_action` CharField(blank), `draft_data` JSONField(default=dict) | 업무 연속성 컨텍스트 |
| **SubmissionDraft** | `submission` FK(Submission, unique), `template` CharField, `auto_draft_json` JSONField(default=dict), `consultation_input` TextField(blank), `consultation_audio` FileField(blank), `final_content_json` JSONField(default=dict), `masking_config` JSONField(default=dict), `output_format` CharField(choices: word/pdf), `output_language` CharField(choices: ko/en/ko_en), `output_file` FileField(blank), `status` CharField(choices: 초안생성/상담입력/AI정리완료/검토완료/변환완료) | 제출 서류 생성 파이프라인 |

### accounts 앱 확장

| 모델 | 필드 | 비고 |
|------|------|------|
| **Organization** | `name` CharField, `plan` CharField(choices: basic/standard/premium/partner), `db_share_enabled` BooleanField(default=False), `logo` ImageField(blank) | 서치펌(헤드헌팅 업체). plan은 구독 플랜, db_share_enabled는 DB 공유 네트워크 참여 여부 |
| **Membership** | `user` FK(User, unique), `organization` FK(Organization), `role` CharField(choices: owner/consultant/viewer) | 1인 1조직. owner=회사 관리자(프로젝트 등록/삭제, 직원 초대, 정산), consultant=업무 담당자(배정 건 서칭/컨택/서류), viewer=읽기 전용 |
| **TelegramBinding** | `user` FK(User, unique), `chat_id` CharField, `is_active` BooleanField(default=True) | 텔레그램 바인딩 |

### candidates 앱 확장 (기존 앱 migration 추가)

| 모델 | 필드 | 비고 |
|------|------|------|
| **Candidate** (기존 모델 변경) | `owned_by` FK(Organization, null=True) 추가 | DB 공유 네트워크에서 원본 소유 서치펌 추적 |

### 공통 (projects 앱 배치)

| 모델 | 필드 | 비고 |
|------|------|------|
| **Notification** | `recipient` FK(User), `type` CharField(choices: approval_request/auto_generated/reminder/news), `title` CharField, `body` TextField, `action_url` URLField(blank), `telegram_message_id` CharField(blank), `status` CharField(choices: pending/sent/read/acted, default=pending), `callback_data` JSONField(default=dict) | 알림 시스템 |

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

## 권한 정책

Organization 기반 멀티테넌시 권한 매트릭스. SuperAdmin은 Django `is_superuser`, Owner/Consultant/Viewer는 Membership.role로 결정.

| 기능 | SuperAdmin (is_superuser) | Owner | Consultant | Viewer |
|------|--------------------------|-------|------------|--------|
| Organization 관리 | O | X | X | X |
| 직원 초대/관리 | X | O | X | X |
| 프로젝트 등록/삭제 | X | O | X | X |
| 고객사 등록/편집 | X | O | X | X |
| 후보자 등록/편집 | X | O | O | X |
| 컨택/추천 작업 | X | O | O (배정 건만) | X |
| 대시보드 전체 | O | O | X | X |
| DB 공유 설정 | X | O | X | X |
| 정산/수수료 | O | O | X | X |

---

## Admin 등록

모든 모델을 `admin.site.register()`로 등록. `list_display`, `list_filter`, `search_fields`를 설정하여 관리 편의성 확보.

- **Client:** list_display=(`name`, `industry`, `size`, `region`)
- **Project:** list_display=(`title`, `client`, `status`, `created_by`, `created_at`), list_filter=(`status`,)
- **Contact:** list_display=(`project`, `candidate`, `consultant`, `channel`, `result`, `contacted_at`)
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
| 모델 CRUD | `uv run pytest` — Client, Project, Contact 등 기본 생성/조회 테스트 |
| Organization/Membership | Organization 생성, Membership(user+org+role) 생성, 1인 1조직 unique 제약 검증 |
| Candidate.owned_by | Candidate에 owned_by FK 설정/조회 테스트, null 허용 확인 |
| Admin 접근 | Admin 페이지에서 모든 모델 목록/등록 화면 확인 |
| FK 관계 | Project → Client, Project → Organization, Client → Organization, Contact → Project/Candidate 등 관계 정합성 |
| UUID PK | 모든 모델 PK가 UUID 타입인지 확인 |
| 권한 정책 | Owner/Consultant/Viewer 역할별 접근 제어 단위 테스트 |

---

## 산출물

- `clients/` 앱 디렉토리 (models.py, admin.py, apps.py)
- `projects/` 앱 디렉토리 (models.py, admin.py, apps.py)
- `accounts/models.py` — Organization, Membership, TelegramBinding 추가
- `candidates/` migration — Candidate.owned_by FK 추가
- Migration 파일들 (accounts, clients, projects, candidates)
- 모델 기본 CRUD 테스트
- 권한 정책 단위 테스트
