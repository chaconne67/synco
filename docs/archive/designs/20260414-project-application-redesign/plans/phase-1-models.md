# Phase 1 — 모델 재정의 + 마이그레이션 클린 재생성

**전제**: [FINAL-SPEC.md](../FINAL-SPEC.md)를 단일 진실 소스로 삼음.
**목표**: 새 스키마를 코드로 정의하고 로컬에서 `migrate` 성공까지 완료.
**예상 시간**: 0.5-1일
**리스크**: 낮음 (데이터 0건, 마이그레이션 클린 재생성)

---

## 1. 목표 상태 (이 Phase 종료 시점)

- `projects/models.py`가 FINAL-SPEC의 섹션 2 정의 그대로 재작성되어 있음
- 기존 `projects/migrations/0001_initial.py ~ 0014_*.py`는 전부 삭제됨
- 새 단일 `0001_initial.py`가 `makemigrations`로 생성됨
- ActionType 초기 seed 데이터가 data migration `0002_seed_action_types.py`로 주입됨
- `uv run python manage.py migrate --run-syncdb`가 클린 로컬 DB에서 에러 없이 완료됨
- `python manage.py check`가 경고 없음
- **뷰·서비스·템플릿 에러는 이 Phase에서 무시**. 모델 정의가 우선.

## 2. 사전 조건

- FINAL-SPEC.md가 최종 확정됨 ✓
- 현재 브랜치: `feat/project-application-redesign` (새로 생성, `feat/rbac-onboarding`에서 분기)
- 로컬 DB는 삭제 후 재생성해도 무방 (테스트 데이터 0건)

## 3. 영향 범위

### 3.1 수정 파일
- `projects/models.py` (849줄 → 전면 재작성)
- `projects/admin.py` (ActionType 등록 추가)
- `projects/migrations/` (전체 삭제 후 재생성)

### 3.2 참조만 (수정 없음, Phase 2 이후)
- `projects/signals.py` — Phase 2에서 재작성
- `projects/services/*.py` — Phase 2에서 재작성
- `projects/views.py`, `forms.py`, `urls.py` — Phase 3에서 재작성
- `projects/templates/projects/*.html` — Phase 4에서 재작성

## 4. 태스크 분할

### T1.1 — Project 모델 재정의
**파일**: `projects/models.py`
**작업**:
- 기존 `ProjectStatus` enum 제거
- 새 enum 추가: `ProjectPhase(SEARCHING, SCREENING)`, `ProjectStatus(OPEN, CLOSED)`, `ProjectResult(SUCCESS, FAIL)`
- `Project.status` 필드 제거 (기존 ProjectStatus enum 참조)
- 신규 필드 추가:
  - `phase = CharField(20, choices=ProjectPhase.choices, default=SEARCHING, db_index=True)`
  - `status = CharField(20, choices=ProjectStatus.choices, default=OPEN, db_index=True)`
  - `deadline = DateField(null=True, blank=True)`
  - `closed_at = DateTimeField(null=True, blank=True)`
  - `result = CharField(20, choices=ProjectResult.choices, blank=True, default="")`
  - `note = TextField(blank=True)`
- 기존 필드 유지: `client`, `organization`, `title`, `jd_*`, `assigned_consultants`, `requirements`, `posting_*`, `created_by`
- `Meta` 클래스에 인덱스 추가:
  ```python
  indexes = [
      models.Index(fields=["phase", "status"]),
      models.Index(fields=["deadline"]),
      models.Index(fields=["organization", "status"]),
  ]
  ```
- 파생 property: `is_closed`, `days_elapsed` (기존 유지)

**검증**: `python -c "from projects.models import Project; print(Project._meta.get_fields())"` 실행 시 새 필드들이 포함되어야 함.

---

### T1.2 — ActionType 모델 신규 추가
**파일**: `projects/models.py`
**작업**:
- `ActionChannel(TextChoices)` enum 추가: `in_person, video, phone, kakao, sms, email, linkedin, other`
- `ActionOutputKind(TextChoices)` enum 추가: `""`, `submission`, `interview`, `meeting`
- `ActionType(BaseModel)` 클래스 추가:
  - `code = CharField(40, unique=True)`
  - `label_ko = CharField(100)`
  - `phase = CharField(20, blank=True)` (any일 때 "")
  - `default_channel = CharField(20, choices=ActionChannel.choices, blank=True)`
  - `output_kind = CharField(20, choices=ActionOutputKind.choices, blank=True)`
  - `sort_order = PositiveIntegerField(default=0)`
  - `is_active = BooleanField(default=True)`
  - `is_protected = BooleanField(default=False)`
  - `description = TextField(blank=True)`
  - `suggests_next = JSONField(default=list, blank=True)` — 다음 action_type code 목록
  - `Meta.ordering = ["sort_order", "code"]`

**검증**: `ActionType._meta.get_field("code").unique == True`

---

### T1.3 — Application 모델 신규 추가
**파일**: `projects/models.py`
**작업**:
- `DropReason(TextChoices)` enum 추가: `unfit, candidate_declined, client_rejected, other`
- `Application(BaseModel)` 클래스 추가:
  - `project = FK(Project, CASCADE, related_name="applications")`
  - `candidate = FK("candidates.Candidate", CASCADE, related_name="applications")`
  - `notes = TextField(blank=True)`
  - `hired_at = DateTimeField(null=True, blank=True)`
  - `dropped_at = DateTimeField(null=True, blank=True)`
  - `drop_reason = CharField(30, choices=DropReason.choices, blank=True, default="")`
  - `drop_note = TextField(blank=True)`
  - `created_by = FK(settings.AUTH_USER_MODEL, SET_NULL, null=True, related_name="created_applications")`
- Manager: `ApplicationQuerySet` with `active()`, `submitted()`, `for_project()`
- property: `is_active`, `current_state`
- `Meta`:
  ```python
  constraints = [
      models.UniqueConstraint(
          fields=["project", "candidate"],
          name="unique_application_per_project_candidate",
      ),
  ]
  indexes = [
      models.Index(fields=["project", "dropped_at", "hired_at"]),
      models.Index(fields=["candidate"]),
  ]
  ordering = ["-created_at"]
  ```
- `current_state`는 ActionItem 쿼리를 참조하므로 ActionItem 정의 이후에 구현 (같은 파일 내 순서 주의)

**검증**: `Application.objects.active()` 쿼리가 ORM 레벨에서 valid함.

---

### T1.4 — ActionItem 모델 신규 추가
**파일**: `projects/models.py`
**작업**:
- `ActionItemStatus(TextChoices)` enum: `pending, done, skipped, cancelled`
- `ActionItem(BaseModel)` 클래스:
  - `application = FK(Application, CASCADE, related_name="action_items")`
  - `action_type = FK(ActionType, PROTECT, related_name="items")`
  - `title = CharField(300)`
  - `channel = CharField(20, choices=ActionChannel.choices, blank=True)`
  - `scheduled_at = DateTimeField(null=True, blank=True)`
  - `due_at = DateTimeField(null=True, blank=True)`
  - `completed_at = DateTimeField(null=True, blank=True)`
  - `status = CharField(20, choices=ActionItemStatus.choices, default=PENDING, db_index=True)`
  - `result = TextField(blank=True)`
  - `note = TextField(blank=True)`
  - `assigned_to = FK(User, SET_NULL, null=True, related_name="assigned_action_items")`
  - `created_by = FK(User, SET_NULL, null=True, related_name="created_action_items")`
  - `parent_action = FK("self", SET_NULL, null=True, blank=True, related_name="children")`
- Manager: `ActionItemQuerySet` with `pending()`, `done()`, `overdue()`, `due_soon(days=3)`, `for_user(user)`
- property: `is_overdue`
- `Meta`:
  ```python
  ordering = ["due_at", "created_at"]
  indexes = [
      models.Index(fields=["application", "status"]),
      models.Index(fields=["assigned_to", "status", "due_at"]),
      models.Index(fields=["action_type", "status"]),
  ]
  ```

**검증**: `ActionItem.objects.pending().overdue()` 체이닝이 ORM 레벨에서 valid함.

---

### T1.5 — Submission 모델 수정
**파일**: `projects/models.py`
**작업**:
- 기존 `Submission.Status` inner enum **제거**
- 기존 `project` FK **제거**
- 기존 `candidate` FK **제거**
- 기존 `status` 필드 **제거**
- 신규 필드: `action_item = OneToOneField(ActionItem, CASCADE, related_name="submission")`
- 유지: `consultant`, `template`, `document_file`, `submitted_at`, `client_feedback`, `client_feedback_at`, `notes`
- 기존 Unique constraint `unique_submission_per_project_candidate` 제거

**검증**: Submission의 모든 접근이 action_item 경유로 가능해야 함.

---

### T1.6 — Interview 모델 수정
**파일**: `projects/models.py`
**작업**:
- 기존 `submission` FK **제거**
- 신규 필드: `action_item = OneToOneField(ActionItem, CASCADE, related_name="interview")`
- 유지: `round`, `scheduled_at`, `type`, `location`, `result`, `feedback`, `notes`, `Type` enum, `Result` enum
- Unique constraint 변경: `unique_interview_per_submission_round` → `unique_interview_per_action_round` (action_item + round 조합)

---

### T1.7 — MeetingRecord 모델 수정
**파일**: `projects/models.py`
**작업**:
- 기존 `project` FK **제거**
- 기존 `candidate` FK **제거**
- 신규 필드: `action_item = OneToOneField(ActionItem, CASCADE, related_name="meeting_record")`
- 유지: `audio_file`, `transcript`, `analysis_json`, `edited_json`, `status`, `error_message`, `applied_at`, `applied_by`, `created_by`, `Status` enum

---

### T1.8 — Contact 모델 완전 삭제
**파일**: `projects/models.py`
**작업**:
- `Contact` 클래스 전체 제거 (Channel, Result inner enum 포함)
- 향후 `ActionItem.channel`이 Channel 역할을 대체

**주의**: 다른 파일(services/dashboard.py, views.py 등)에서 Contact 참조가 남아있을 수 있음. Phase 1에서는 `projects/models.py`만 수정하고 나머지 참조는 임시 컴파일 에러로 둠. Phase 2~3에서 제거.

---

### T1.9 — Offer 모델 완전 삭제
**파일**: `projects/models.py`
**작업**:
- `Offer` 클래스 전체 제거 (Status inner enum 포함)

**주의**: T1.8과 동일. Offer 관련 참조는 Phase 3/6에서 정리.

---

### T1.10 — 기존 migrations 전체 삭제
**파일**: `projects/migrations/`
**작업**:
```bash
rm projects/migrations/0001_initial.py
rm projects/migrations/0002_add_jd_analysis_fields.py
rm projects/migrations/0003_p06_contact_reserved_nullable.py
rm projects/migrations/0004_p07_submission_template_feedback_notes.py
rm projects/migrations/0005_p08_submission_draft.py
rm projects/migrations/0006_p09_interview_offer_fields.py
rm projects/migrations/0007_p10_posting_site.py
rm projects/migrations/0008_p11_approval_collision_fields.py
rm projects/migrations/0009_p13_contact_next_contact_date.py
rm projects/migrations/0010_meetingrecord.py
rm projects/migrations/0011_notification_telegram_chat_id.py
rm projects/migrations/0012_autoaction_and_more.py
rm projects/migrations/0013_newssource_newsarticle_newsarticlerelevance.py
rm projects/migrations/0014_resumeupload.py
rm -rf projects/migrations/__pycache__
```

**유지**: `projects/migrations/__init__.py`

**검증**: `ls projects/migrations/` → `__init__.py`만 남아있어야 함.

---

### T1.11 — 새 0001_initial 생성
**작업**:
```bash
uv run python manage.py makemigrations projects
```

**예상 결과**: `projects/migrations/0001_initial.py` 하나 생성. 이 파일 안에 Project/Application/ActionType/ActionItem/Submission/Interview/MeetingRecord/SubmissionDraft/ProjectApproval/ProjectContext/Notification/PostingSite/AutoAction/NewsSource/NewsArticle/NewsArticleRelevance/ResumeUpload 전부 포함되어야 함.

**검증**:
```bash
uv run python manage.py makemigrations --check --dry-run
```
→ "No changes detected" 출력되어야 함.

---

### T1.12 — ActionType seed data migration 생성
**파일**: `projects/migrations/0002_seed_action_types.py`
**작업**:
- `RunPython` 마이그레이션 작성
- FINAL-SPEC 섹션 2.3의 초기 seed 23개 주입
- 핵심 4개(`pre_meeting`, `submit_to_client`, `interview_round`, `confirm_hire`)는 `is_protected=True`
- 각 항목에 `suggests_next` 배열 포함 (섹션 3.7 참조)
- reverse_func: `ActionType.objects.all().delete()`
- `dependencies = [("projects", "0001_initial")]`

**seed 데이터 구조 예시**:
```python
ACTION_TYPES = [
    {
        "code": "reach_out",
        "label_ko": "후보자 연락",
        "phase": "searching",
        "output_kind": "",
        "sort_order": 10,
        "is_protected": False,
        "description": "후보자에게 첫 연락을 시도한다.",
        "suggests_next": ["await_reply", "schedule_pre_meet"],
    },
    # ... 나머지 22개
]

def seed_forward(apps, schema_editor):
    ActionType = apps.get_model("projects", "ActionType")
    for data in ACTION_TYPES:
        ActionType.objects.update_or_create(code=data["code"], defaults=data)

def seed_reverse(apps, schema_editor):
    ActionType = apps.get_model("projects", "ActionType")
    codes = [d["code"] for d in ACTION_TYPES]
    ActionType.objects.filter(code__in=codes).delete()
```

**검증**: 마이그레이션 실행 후 `ActionType.objects.count() == 23`.

---

### T1.13 — 로컬 DB 클린 재생성 + migrate
**작업**:
```bash
# Docker dev postgres 초기화
docker compose down -v
docker compose up -d
sleep 3

# 마이그레이션
uv run python manage.py migrate
```

**예상 결과**:
- 모든 마이그레이션 에러 없이 완료
- `ActionType` 테이블에 23개 row 존재
- 다른 테이블은 비어있음

**검증**:
```bash
uv run python manage.py shell -c "from projects.models import ActionType; print(ActionType.objects.count())"
# → 23

uv run python manage.py shell -c "from projects.models import Project, Application, ActionItem; print(Project.objects.count(), Application.objects.count(), ActionItem.objects.count())"
# → 0 0 0
```

---

### T1.14 — admin.py에 ActionType 등록
**파일**: `projects/admin.py`
**작업**:
- `ActionType`을 `ModelAdmin`으로 등록
- `list_display = ["code", "label_ko", "phase", "output_kind", "is_active", "is_protected", "sort_order"]`
- `list_filter = ["phase", "output_kind", "is_active", "is_protected"]`
- `search_fields = ["code", "label_ko"]`
- `list_editable = ["is_active", "sort_order"]`
- `readonly_fields = ["is_protected"]` (관리자도 직접 수정 못 함)
- ActionType의 `delete_model` 오버라이드: `is_protected=True`면 ValidationError

**검증**: `/admin/projects/actiontype/` 접근 시 23개 행 표시.

---

### T1.15 — Django check 실행
**작업**:
```bash
uv run python manage.py check
```

**예상 결과**: 에러·경고 없음. 단 `views.py`, `services/*.py`, `forms.py` 등에서 Contact/Offer/ProjectStatus 참조로 인한 ImportError는 이 Phase에서 무시(Phase 2~6에서 정리). 이 단계에서는 `check`가 **모델 정의** 관점에서 통과하는 것이 목표.

만약 `models.py` import 시점에 에러가 나면 수정. 다른 파일에서 Contact/Offer 참조로 인한 에러는 해당 파일을 임시 `# TODO Phase 2/3`로 주석 처리하거나 stub 처리.

---

## 5. 검증 체크리스트

Phase 1 완료 조건:

- [ ] `projects/models.py`에 FINAL-SPEC 섹션 2의 모든 모델이 정의됨
- [ ] `ProjectStatus` 기존 10-state enum이 완전히 제거됨
- [ ] `Contact`, `Offer` 클래스가 완전히 삭제됨
- [ ] `Submission`, `Interview`, `MeetingRecord`가 action_item FK로 매달림
- [ ] `projects/migrations/`에 `0001_initial.py` + `0002_seed_action_types.py`만 존재
- [ ] `makemigrations --check --dry-run`이 "No changes detected"
- [ ] `migrate` 성공
- [ ] `ActionType.objects.count() == 23`
- [ ] `ActionType.objects.filter(is_protected=True).count() == 4`
- [ ] 관리자 페이지에서 ActionType 리스트 표시됨
- [ ] `python manage.py check` (models 관점) 통과

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| 다른 파일(views.py 등)에서 ImportError | 해당 import 줄을 `# TODO: Phase 2/3`로 주석 처리. 모델 정의 우선 |
| 마이그레이션 생성 시 순환 import | `models.py` 내부 상호참조 순서 조정, 필요 시 문자열 FK 사용 (`"projects.ActionItem"`) |
| `current_state` property의 ActionItem 쿼리 에러 | Application 클래스 정의 내부에서 `ActionItem` 이름 참조는 문자열로 지연 로딩 |
| Submission/Interview/MeetingRecord 기존 데이터 없음 확인 | `Submission.objects.count() == 0` 먼저 확인 후 진행 (이미 clean slate 보장됨) |
| admin.py 기존 등록에 Contact/Offer 있음 | 해당 라인 제거 |

## 7. 커밋 포인트

```
feat(projects): redefine models per FINAL-SPEC

- Replace ProjectStatus 10-state enum with 2-phase + status/result
- Add Application, ActionType, ActionItem models (task-centric)
- Delete Contact, Offer models
- Rewire Submission/Interview/MeetingRecord to action_item FK
- Seed 23 initial ActionType rows (4 protected)
- Clean regenerate migrations (0001_initial + 0002_seed_action_types)

Refs: docs/designs/20260414-project-application-redesign/FINAL-SPEC.md
```

**브랜치**: `feat/project-application-redesign`
**이 커밋 이후**: Phase 2 진입

## 8. Phase 2로 넘기는 인터페이스

Phase 2(서비스 레이어)가 Phase 1 산출물을 기반으로 할 수 있도록 다음을 보장:

1. **ORM 레벨에서 모든 모델·Manager·property가 유효함** (뷰/서비스 미구현이어도)
2. **ActionType seed가 존재함** — Phase 2의 signal·service 코드가 `ActionType.objects.get(code="submit_to_client")` 같은 호출을 할 수 있어야 함
3. **`Application.current_state` property가 호출 가능** (ActionItem 쿼리 기반)
4. **기존 Contact/Offer 관련 참조는 Phase 2 진입 전 명확히 목록화** → Phase 2/3에서 일괄 정리

---

**다음 Phase**: [phase-2a-services-core.md](phase-2a-services-core.md)
