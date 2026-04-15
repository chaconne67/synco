# P16: Work Continuity — 확정 설계서

> **Phase:** 16
> **선행조건:** P01 (ProjectContext 모델), P03 (프로젝트 CRUD), P06 (컨택), P14 (보이스 에이전트)
> **산출물:** 업무 상태 자동 보존 + 재개 시스템 + 이벤트 트리거 자동 생성

---

## 목표

업무 프로세스가 중단되었을 때 상태를 자동 보존하고, 재개 시 이어서 진행할 수 있게 한다.
이벤트 기반 자동 생성 시스템으로 선제적 문서/작업 생성 후 사용자 승인을 요청한다.

---

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/projects/<pk>/context/` | GET | `project_context` | 중단된 작업 상태 조회 |
| `/projects/<pk>/context/save/` | POST | `project_context_save` | 작업 상태 저장 (autosave) |
| `/projects/<pk>/context/resume/` | POST | `project_context_resume` | 중단된 작업 재개 |
| `/projects/<pk>/context/discard/` | POST | `project_context_discard` | 중단된 작업 취소 |
| `/projects/<pk>/auto-actions/` | GET | `project_auto_actions` | 자동 생성물 목록 (기본: pending만) |
| `/projects/<pk>/auto-actions/<action_pk>/apply/` | POST | `auto_action_apply` | 자동 생성물 적용 |
| `/projects/<pk>/auto-actions/<action_pk>/dismiss/` | POST | `auto_action_dismiss` | 자동 생성물 무시 |

### 권한 규칙

- 모든 뷰: `@login_required`
- Context 뷰: `project.organization == request.user.organization` AND `context.consultant == request.user`
- AutoAction 뷰: `project.organization == request.user.organization` AND `action.project_id == project.pk`
- Context save: 본인 컨텍스트만 생성/수정 가능

---

## 모델

### ProjectContext (P01 정의 완료, 제약 추가)

| 필드 | 타입 | 설명 |
|------|------|------|
| `project` | FK → Project | 대상 프로젝트 |
| `consultant` | FK → User | 컨설턴트 |
| `last_step` | CharField | 마지막 작업 단계 |
| `pending_action` | CharField | 대기 중인 액션 설명 |
| `draft_data` | JSONField | 작성 중이던 폼/대화 상태 |
| (inherited) | `created_at`, `updated_at` | BaseModel 상속 |

**추가 제약:**
```python
class Meta:
    ordering = ["-updated_at"]
    constraints = [
        models.UniqueConstraint(
            fields=["project", "consultant"],
            name="unique_context_per_project_consultant",
        )
    ]
```

**정책:** 프로젝트+컨설턴트당 하나의 활성 컨텍스트. `update_or_create`로 저장. 새 autosave는 기존 컨텍스트를 덮어쓴다 (최신 작업이 우선).

### AutoAction (신규, projects 앱)

`BaseModel`을 상속하여 UUID PK + `created_at` + `updated_at` 자동 제공.

| 필드 | 타입 | 설명 |
|------|------|------|
| (inherited) | `id` (UUID), `created_at`, `updated_at` | BaseModel |
| `project` | FK → Project | 대상 프로젝트 |
| `trigger_event` | CharField(100) | 트리거 이벤트명 |
| `action_type` | CharField choices | 자동 생성물 유형 |
| `title` | CharField(300) | 표시 제목 |
| `data` | JSONField | 생성된 데이터 (초안 내용 등) |
| `status` | CharField choices | pending / applied / dismissed |
| `due_at` | DateTimeField(null, blank) | 예약 실행 시각 (리마인더용) |
| `created_by` | FK → User(null) | 생성자 (null=시스템 생성) |
| `applied_by` | FK → User(null) | 적용한 사용자 |
| `dismissed_by` | FK → User(null) | 무시한 사용자 |

```python
class ActionType(models.TextChoices):
    POSTING_DRAFT = "posting_draft", "공지 초안"
    CANDIDATE_SEARCH = "candidate_search", "후보자 자동 서칭"
    SUBMISSION_DRAFT = "submission_draft", "제출 서류 초안"
    OFFER_TEMPLATE = "offer_template", "오퍼 템플릿"
    FOLLOWUP_REMINDER = "followup_reminder", "팔로업 리마인더"
    RECONTACT_REMINDER = "recontact_reminder", "재컨택 리마인더"

class ActionStatus(models.TextChoices):
    PENDING = "pending", "대기"
    APPLIED = "applied", "적용됨"
    DISMISSED = "dismissed", "무시됨"
```

---

## 업무 상태 자동 보존

### 보존 시점 및 방법

| 시점 | 저장 방법 |
|------|----------|
| 폼 입력 중 (주기적) | JS `setInterval` 30초 debounce → `fetch()` POST to `/context/save/` |
| 폼 입력 중 페이지 이탈 | `navigator.sendBeacon()` on `beforeunload` (fallback) |
| HTMX 내부 네비게이션 | `htmx:beforeHistorySave` 이벤트에서 `fetch()` POST |
| 보이스 대화 중단 | 대화 세션 종료 시 자동 저장 (P14 연동) |
| 명시적 "나중에" | 사용자가 "나중에" 클릭 → 컨텍스트 저장 |

### Context Save 엔드포인트

```
POST /projects/<pk>/context/save/
Content-Type: application/json

{
  "last_step": "contact_create",
  "pending_action": "홍길동 컨택 결과 입력",
  "draft_data": { ... }
}

Response: 204 No Content (성공)
Response: 400 Bad Request (잘못된 데이터)
Response: 403 Forbidden (권한 없음)
```

`sendBeacon`은 `Content-Type: application/x-www-form-urlencoded`로 전송되므로 서버는 두 형식 모두 수용한다.

### draft_data 구조 예시

```json
{
  "form": "contact_create",
  "fields": {
    "candidate_id": "uuid",
    "channel": "phone",
    "result": null,
    "notes": "현 연봉 8500..."
  },
  "completed_fields": ["candidate_id", "channel"],
  "missing_fields": ["result"]
}
```

### 폼 복원 메커니즘 (FORM_REGISTRY)

`services/context.py`에 폼 이름을 URL/템플릿으로 매핑하는 레지스트리:

```python
FORM_REGISTRY = {
    "contact_create": {
        "url_name": "projects:contact_create",
        "url_kwargs": lambda ctx: {"pk": str(ctx.project_id)},
    },
    "contact_update": {
        "url_name": "projects:contact_update",
        "url_kwargs": lambda ctx: {
            "pk": str(ctx.project_id),
            "contact_pk": ctx.draft_data.get("contact_id", ""),
        },
    },
    "submission_create": {
        "url_name": "projects:submission_create",
        "url_kwargs": lambda ctx: {"pk": str(ctx.project_id)},
    },
    # ... 각 resumable 폼 등록
}
```

**재개 흐름:**
1. 사용자가 "이어서 하기" 클릭 → `POST /projects/<pk>/context/resume/`
2. 서버가 `FORM_REGISTRY`에서 `last_step`으로 대상 URL 결정
3. `HX-Redirect` 헤더로 `{target_url}?resume={context_id}` 응답
4. 대상 뷰에서 `resume` 쿼리 파라미터 감지 → ProjectContext 로드 → `draft_data.fields`를 폼 initial에 주입

### 재개 UI

프로젝트 진입 시 미완료 컨텍스트가 있으면 자동 표시:

```
┌─ Rayence 품질기획 ──────────────────────────────────────┐
│  중단된 작업                                             │
│  홍길동 컨택 결과 입력 (3시간 전 중단)                      │
│  채널(전화) 선택됨 — 결과만 입력하면 완료                    │
│  [이어서 하기]  [새로 시작]  [취소]                        │
└──────────────────────────────────────────────────────────┘
```

보이스 에이전트 재개 (P14 통합 지점):
```
🎙️ "아까 하던 거 이어서 하자"
🤖 마지막 작업: Rayence 품질기획
   홍길동 컨택 결과 입력 중이었습니다.
   결과만 남았어요. 이어서 할까요?
```

---

## 이벤트 트리거 자동 생성

### 트리거 매핑

| 트리거 이벤트 | 자동 생성물 | 실행 방식 | 알림 |
|-------------|-----------|----------|------|
| 프로젝트 등록 | 공지 초안 + 후보자 자동 서칭 | post_save signal | "공지/후보자 준비됨" |
| 컨택 결과 = 관심 | 제출 서류 AI 초안 | post_save signal | "서류 초안 검토 요청" |
| 서류 제출 완료 | 팔로업 리마인더 (3일 후) | post_save signal → due_at | "팔로업 알림 예정" |
| 면접 합격 | 오퍼 템플릿 | post_save signal | "오퍼 초안 준비됨" |
| 잠금 만료 임박 (1일 전) | 재컨택 리마인더 | management command (cron) | "컨택 잠금 내일 만료" |

### 구현: Django Signals

**핵심 원칙:** Signal 핸들러는 가벼운 `AutoAction(status="pending")` 레코드만 생성한다. AI 생성은 signal에서 수행하지 않는다.

`projects/signals.py`:

```python
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import (
    AutoAction, ActionType, ActionStatus,
    Contact, Interview, Project, ProjectStatus, Submission,
)


@receiver(post_save, sender=Project)
def on_project_created(sender, instance, created, **kwargs):
    if not created or instance.status != ProjectStatus.NEW:
        return
    transaction.on_commit(lambda: _create_project_actions(instance))


def _create_project_actions(project):
    """프로젝트 생성 시 공지 초안 + 후보자 서칭 AutoAction 생성 (멱등)."""
    for action_type, title in [
        (ActionType.POSTING_DRAFT, f"{project.title} 공지 초안"),
        (ActionType.CANDIDATE_SEARCH, f"{project.title} 후보자 자동 서칭"),
    ]:
        AutoAction.objects.get_or_create(
            project=project,
            action_type=action_type,
            status=ActionStatus.PENDING,
            defaults={
                "trigger_event": "project_created",
                "title": title,
                "data": {"project_id": str(project.pk)},
            },
        )


@receiver(post_save, sender=Contact)
def on_contact_result(sender, instance, **kwargs):
    if instance.result != Contact.Result.INTERESTED:
        return
    # 멱등: 이미 pending인 동일 타입이 있으면 스킵
    if AutoAction.objects.filter(
        project=instance.project,
        action_type=ActionType.SUBMISSION_DRAFT,
        status=ActionStatus.PENDING,
        data__candidate_id=str(instance.candidate_id),
    ).exists():
        return
    transaction.on_commit(lambda: AutoAction.objects.create(
        project=instance.project,
        trigger_event="contact_interested",
        action_type=ActionType.SUBMISSION_DRAFT,
        title=f"{instance.candidate.name} 제출 서류 초안",
        data={"candidate_id": str(instance.candidate_id)},
    ))


@receiver(post_save, sender=Submission)
def on_submission_submitted(sender, instance, **kwargs):
    if instance.status != Submission.Status.SUBMITTED:
        return
    if AutoAction.objects.filter(
        project=instance.project,
        action_type=ActionType.FOLLOWUP_REMINDER,
        status=ActionStatus.PENDING,
        data__submission_id=str(instance.pk),
    ).exists():
        return
    from django.utils import timezone
    from datetime import timedelta
    due = timezone.now() + timedelta(days=3)
    transaction.on_commit(lambda: AutoAction.objects.create(
        project=instance.project,
        trigger_event="submission_submitted",
        action_type=ActionType.FOLLOWUP_REMINDER,
        title=f"{instance.candidate.name} 팔로업 리마인더",
        data={"submission_id": str(instance.pk)},
        due_at=due,
    ))


@receiver(post_save, sender=Interview)
def on_interview_passed(sender, instance, **kwargs):
    if instance.result != Interview.Result.PASSED:
        return
    if AutoAction.objects.filter(
        project=instance.submission.project,
        action_type=ActionType.OFFER_TEMPLATE,
        status=ActionStatus.PENDING,
        data__submission_id=str(instance.submission_id),
    ).exists():
        return
    transaction.on_commit(lambda: AutoAction.objects.create(
        project=instance.submission.project,
        trigger_event="interview_passed",
        action_type=ActionType.OFFER_TEMPLATE,
        title=f"{instance.submission.candidate.name} 오퍼 템플릿",
        data={"submission_id": str(instance.submission_id)},
    ))
```

**AppConfig에 signals 등록:**
```python
class ProjectsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "projects"

    def ready(self):
        import projects.signals  # noqa: F401
```

### Management Command: check_due_actions

잠금 만료 임박 감지 + 예약된 리마인더 처리:

```python
# projects/management/commands/check_due_actions.py
# cron: 0 9 * * * (매일 오전 9시)

class Command(BaseCommand):
    def handle(self, **options):
        now = timezone.now()
        tomorrow = now + timedelta(days=1)

        # 1. 잠금 만료 임박 (내일 만료)
        expiring = Contact.objects.filter(
            result=Contact.Result.RESERVED,
            locked_until__lte=tomorrow,
            locked_until__gt=now,
        )
        for contact in expiring:
            AutoAction.objects.get_or_create(
                project=contact.project,
                action_type=ActionType.RECONTACT_REMINDER,
                status=ActionStatus.PENDING,
                data__contact_id=str(contact.pk),
                defaults={
                    "trigger_event": "lock_expiring",
                    "title": f"{contact.candidate.name} 컨택 잠금 내일 만료",
                    "data": {"contact_id": str(contact.pk)},
                },
            )

        # 2. due_at 도달한 pending actions → Notification 생성
        due_actions = AutoAction.objects.filter(
            status=ActionStatus.PENDING,
            due_at__lte=now,
        )
        for action in due_actions:
            # Notification 생성 로직 (notification service 연동)
            ...
```

### AutoAction 적용 의미론 (Apply Semantics)

| ActionType | data 스키마 | Apply 동작 | 대상 모델 | 충돌 처리 |
|-----------|------------|-----------|----------|----------|
| `posting_draft` | `{text: str}` | `project.posting_text = data["text"]` 저장 | Project | 기존 텍스트 덮어쓰기 (확인 프롬프트) |
| `candidate_search` | `{candidate_ids: [uuid]}` | UI에서 후보자 목록 표시 → 사용자 개별 선택 → Contact(result=예정) 생성 | Contact | 이미 컨택된 후보자 스킵 |
| `submission_draft` | `{candidate_id, draft_json}` | SubmissionDraft.auto_draft_json에 저장 | SubmissionDraft | 기존 draft 있으면 병합/확인 |
| `offer_template` | `{submission_id, salary, terms}` | Offer 모델 생성 with 템플릿 데이터 | Offer | 기존 Offer 있으면 에러 |
| `followup_reminder` | `{submission_id, message}` | Notification 생성 for 담당 컨설턴트 | Notification | 멱등 (동일 알림 스킵) |
| `recontact_reminder` | `{contact_id, message}` | Notification 생성 for 담당 컨설턴트 | Notification | 멱등 (동일 알림 스킵) |

**Apply 트랜잭션 안전:**
```python
def apply_action(action_id, user):
    with transaction.atomic():
        action = AutoAction.objects.select_for_update().get(pk=action_id)
        if action.status != ActionStatus.PENDING:
            raise ConflictError("이미 처리된 액션입니다.")
        # ... action_type별 apply 로직 ...
        action.status = ActionStatus.APPLIED
        action.applied_by = user
        action.save(update_fields=["status", "applied_by", "updated_at"])
```

### 자동 생성물 표시

프로젝트 개요 탭에 배너로 표시 (기본: pending만):

```
┌─ 자동 생성 (2건) ──────────────────────────────────────┐
│  공지 초안 생성 가능                    [생성하기] [무시]  │
│  후보자 8명을 찾았습니다.               [확인] [무시]     │
└────────────────────────────────────────────────────────┘
```

**AI 생성이 필요한 타입** (posting_draft, submission_draft, offer_template)은 Apply 시점에 lazy generation 실행. 배너에 "생성 가능" 표시 후 사용자가 클릭하면 생성.
**즉시 표시 가능한 타입** (candidate_search, reminders)은 data에 결과 포함.

---

## P14 보이스 에이전트 통합 지점

| 모듈 | 변경 | 설명 |
|------|------|------|
| `context_resolver.py` | `get_active_context(project, user)` 함수 추가 | ProjectContext 존재 여부 확인 |
| `intent_parser.py` | `resume_context` 인텐트 추가 | "아까 하던 거", "이어서" 등 인식 |
| `action_executor.py` | `resume_context` 핸들러 추가 | ProjectContext 읽어 컨텍스트 요약 반환 |

*실제 P14 코드 변경은 별도 트래킹. P16은 context 저장/조회 API만 제공.*

---

## 데이터 검증

### draft_data 검증 (Context Save 시)

```python
REQUIRED_KEYS = {"form"}  # form 키는 필수
MAX_DRAFT_SIZE = 50_000   # 50KB 제한

def validate_draft_data(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    if not REQUIRED_KEYS.issubset(data.keys()):
        return False
    if len(json.dumps(data)) > MAX_DRAFT_SIZE:
        return False
    return True
```

### AutoAction.data 검증 (Apply 시)

```python
ACTION_DATA_SCHEMA = {
    ActionType.POSTING_DRAFT: {"required": [], "optional": ["text"]},
    ActionType.CANDIDATE_SEARCH: {"required": [], "optional": ["candidate_ids"]},
    ActionType.SUBMISSION_DRAFT: {"required": ["candidate_id"], "optional": ["draft_json"]},
    ActionType.OFFER_TEMPLATE: {"required": ["submission_id"], "optional": ["salary", "terms"]},
    ActionType.FOLLOWUP_REMINDER: {"required": ["submission_id"], "optional": ["message"]},
    ActionType.RECONTACT_REMINDER: {"required": ["contact_id"], "optional": ["message"]},
}
```

---

## 서비스 구조

| 파일 | 역할 |
|------|------|
| `projects/services/context.py` | ProjectContext CRUD + FORM_REGISTRY + 재개/복원 |
| `projects/services/auto_actions.py` | AutoAction 생성(멱등) + apply/dismiss + 검증 |
| `projects/signals.py` | 이벤트 트리거 시그널 핸들러 (가벼운 AutoAction 생성만) |
| `projects/services/generators/posting.py` | 공지 초안 AI 생성 (lazy, apply 시점) |
| `projects/services/generators/search.py` | 후보자 자동 서칭 |
| `projects/services/generators/offer.py` | 오퍼 템플릿 AI 생성 (lazy, apply 시점) |
| `projects/management/commands/check_due_actions.py` | 잠금 만료 감지 + due_at 리마인더 처리 |

---

## 테스트 기준

### Happy Path

| 항목 | 검증 방법 |
|------|----------|
| 상태 보존 | 폼 입력 중단 → ProjectContext 저장 확인 |
| 재개 표시 | 프로젝트 진입 시 중단 작업 배너 표시 |
| 재개 동작 | "이어서 하기" → HX-Redirect + 폼 pre-fill |
| 취소 | "취소" → ProjectContext 삭제 |
| 프로젝트 등록 트리거 | 등록 → AutoAction(공지 초안 + 서칭) 2건 생성 |
| 컨택 관심 트리거 | 컨택 관심 → AutoAction(서류 초안) 생성 |
| 서류 제출 트리거 | 제출 → AutoAction(팔로업, due_at=+3일) 생성 |
| 면접 합격 트리거 | 합격 → AutoAction(오퍼 템플릿) 생성 |
| 잠금 만료 감지 | management command → 만료 임박 AutoAction 생성 |
| 자동 생성물 적용 | 확인 → 대상 모델에 반영 + status=applied |
| 자동 생성물 무시 | 무시 → status=dismissed |
| 보이스 재개 | "아까 하던 거" → 컨텍스트 복원 + 대화 이어가기 |

### Negative / Edge Cases

| 항목 | 검증 방법 |
|------|----------|
| 권한 | 비소속 사용자 → 403 |
| 중복 저장 | 반복 autosave → update_or_create (레코드 1개 유지) |
| 멱등 생성 | 동일 트리거 재발생 → 중복 AutoAction 미생성 |
| 동시 적용 | 두 요청 동시 apply → 하나 성공, 하나 409 |
| AI 실패 | 생성기 예외 → AutoAction pending 유지, 에러 로그 |
| 잘못된 데이터 | 유효하지 않은 draft_data → 400 |
| 이미 처리됨 | applied/dismissed 상태 재적용 → 409 |

---

## 산출물

- `projects/models.py` — AutoAction 모델 + ActionType/ActionStatus choices + ProjectContext UniqueConstraint
- `projects/views.py` — context/auto-action 관련 뷰 7개 (context, save, resume, discard, auto-actions, apply, dismiss)
- `projects/urls.py` — 7개 URL 패턴
- `projects/signals.py` — 이벤트 트리거 시그널 핸들러 (Project, Contact, Submission, Interview)
- `projects/apps.py` — `ready()`에서 signals import
- `projects/services/context.py` — FORM_REGISTRY + 업무 연속성 서비스
- `projects/services/auto_actions.py` — 자동 생성물 관리 + apply/dismiss + 검증
- `projects/services/generators/posting.py` — 공지 초안 생성
- `projects/services/generators/search.py` — 후보자 자동 서칭
- `projects/services/generators/offer.py` — 오퍼 템플릿 생성
- `projects/management/commands/check_due_actions.py` — 예약 액션 처리
- `projects/templates/projects/partials/context_banner.html` — 중단 작업 배너
- `projects/templates/projects/partials/auto_actions.html` — 자동 생성물 목록
- `static/js/context-autosave.js` — 3-tier autosave (periodic + sendBeacon + HTMX event)
- 테스트 파일

<!-- forge:p16-work-continuity:설계담금질:complete:2026-04-10T14:35:00Z -->
