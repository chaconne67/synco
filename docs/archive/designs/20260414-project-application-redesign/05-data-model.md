# 05. 데이터 모델 — 스키마 정의

새 모델의 Django 정의. 기존 모델의 변경 사항과 유지 사항도 함께 정리.

---

## 1. 전체 관계도

```
┌──────────────────────────────────────────────────────────┐
│ Project                                                  │
│   ├── phase          (cached, auto-derived)              │
│   ├── closed_at                                          │
│   └── close_reason   (success | no_hire)                 │
└──────────────────────────────────────────────────────────┘
        │
        │ 1 : N
        ▼
┌──────────────────────────────────────────────────────────┐
│ Application  (project, candidate UNIQUE)                 │
│   ├── stage                                              │
│   ├── drop_reason    (nullable)                          │
│   ├── consultant     (FK User — 담당)                    │
│   └── sourced_at / screened_at / pre_met_at /            │
│       recommended_at / interviewing_at / hired_at /       │
│       dropped_at                                         │
└──────────────────────────────────────────────────────────┘
        │
        ├── Contact          (이벤트: 커뮤니케이션 로그)
        ├── MeetingRecord    (이벤트: 사전미팅 녹음/정리)
        ├── Submission       (산출물: 제출 서류 패키지)
        │     └── SubmissionDraft  (AI 초안 파이프라인)
        └── Interview        (이벤트: 클라이언트 면접 회차별)

┌──────────────────────────────────────────────────────────┐
│ ProjectEvent  (프로젝트 히스토리 타임라인)                │
│   ├── project (FK)                                       │
│   ├── event_type                                         │
│   ├── actor (FK User)                                    │
│   └── metadata (JSONField)                               │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Project — 수정

### 제거되는 것
- `status` 필드
- `ProjectStatus` enum 클래스 전체

### 추가되는 것
- `phase` (cached)
- `closed_at`
- `close_reason`

```python
class ProjectPhase(models.TextChoices):
    SEARCHING    = "searching",    "서칭"
    PRE_MEETING  = "pre_meeting",  "사전미팅"
    SUBMITTED    = "submitted",    "제출/검토"
    INTERVIEWING = "interviewing", "면접"
    CLOSED       = "closed",       "종료"


class CloseReason(models.TextChoices):
    SUCCESS = "success", "성공(입사)"
    NO_HIRE = "no_hire", "실패(입사자 없음)"


class Project(BaseModel):
    client = models.ForeignKey("clients.Client", on_delete=CASCADE, related_name="projects")
    organization = models.ForeignKey("accounts.Organization", on_delete=CASCADE, related_name="projects")
    title = models.CharField(max_length=300)

    # JD 관련 (기존 유지)
    jd_text = models.TextField(blank=True)
    jd_file = models.FileField(upload_to="projects/jd/", blank=True)
    jd_source = models.CharField(max_length=20, choices=JDSource.choices, blank=True)
    jd_drive_file_id = models.CharField(max_length=255, blank=True)
    jd_raw_text = models.TextField(blank=True)
    jd_analysis = models.JSONField(default=dict, blank=True)

    # 🔴 상태 필드 재설계
    phase = models.CharField(
        max_length=20,
        choices=ProjectPhase.choices,
        default=ProjectPhase.SEARCHING,
        db_index=True,
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.CharField(
        max_length=20,
        choices=CloseReason.choices,
        blank=True,
        default="",
    )

    # 기존 유지
    assigned_consultants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="assigned_projects"
    )
    requirements = models.JSONField(default=dict, blank=True)
    posting_text = models.TextField(blank=True)
    posting_file_name = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=SET_NULL, null=True, related_name="created_projects"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["phase", "closed_at"]),
        ]

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None

    @property
    def days_elapsed(self) -> int:
        return (timezone.now().date() - self.created_at.date()).days
```

---

## 3. Application — 신규

가장 핵심적인 새 모델. (Project, Candidate) 엣지의 상태와 이력을 담는다.

```python
class ApplicationStage(models.TextChoices):
    SOURCED             = "sourced",             "발굴"
    SCREENED            = "screened",            "검토"
    PRE_MEETING         = "pre_meeting",         "사전미팅"
    RECOMMENDED         = "recommended",         "추천"
    CLIENT_INTERVIEWING = "client_interviewing", "면접"
    HIRED               = "hired",               "입사"
    DROPPED             = "dropped",             "드롭"


class DropReason(models.TextChoices):
    # 후보자 측
    CAND_NOT_INTERESTED = "cand_not_interested", "후보자_이직의사없음"
    CAND_WITHDREW       = "cand_withdrew",       "후보자_철회포기"
    CAND_NO_REPLY       = "cand_no_reply",       "후보자_연락두절"
    CAND_LOCATION       = "cand_location",       "후보자_근무지조건"
    CAND_SALARY         = "cand_salary",         "후보자_처우조건"
    CAND_GOT_OTHER_JOB  = "cand_got_other_job",  "후보자_타사입사"
    CAND_DECLINED_OFFER = "cand_declined_offer", "후보자_입사포기"

    # 컨설턴트 판정
    UNFIT_CAREER    = "unfit_career",    "부적합_경력"
    UNFIT_INDUSTRY  = "unfit_industry",  "부적합_산업"
    UNFIT_EDUCATION = "unfit_education", "부적합_학력"
    UNFIT_JOB_FIT   = "unfit_job_fit",   "부적합_직무"
    UNFIT_OTHER     = "unfit_other",     "부적합_기타"

    # 클라이언트 측
    CLIENT_REJECT_DOC       = "client_reject_doc",       "클라이언트_서류탈락"
    CLIENT_REJECT_INTERVIEW = "client_reject_interview", "클라이언트_면접탈락"
    CLIENT_CLOSED_POSITION  = "client_closed_position",  "클라이언트_포지션마감"
    CLIENT_CANCELLED        = "client_cancelled",        "클라이언트_진행취소"

    # 중복/행정
    DUPLICATE_OTHER_FIRM = "duplicate_other_firm", "타서치펌_중복지원"


class Application(BaseModel):
    project = models.ForeignKey(
        Project, on_delete=CASCADE, related_name="applications"
    )
    candidate = models.ForeignKey(
        "candidates.Candidate", on_delete=CASCADE, related_name="applications"
    )
    consultant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=SET_NULL,
        null=True,
        related_name="applications",
    )

    stage = models.CharField(
        max_length=30,
        choices=ApplicationStage.choices,
        default=ApplicationStage.SOURCED,
        db_index=True,
    )
    drop_reason = models.CharField(
        max_length=30,
        choices=DropReason.choices,
        blank=True,
        default="",
    )
    drop_note = models.TextField(blank=True)  # 자유 메모

    # 단계 진입 타임스탬프 (감사/분석)
    sourced_at = models.DateTimeField(auto_now_add=True)
    screened_at = models.DateTimeField(null=True, blank=True)
    pre_met_at = models.DateTimeField(null=True, blank=True)
    recommended_at = models.DateTimeField(null=True, blank=True)
    interviewing_at = models.DateTimeField(null=True, blank=True)
    hired_at = models.DateTimeField(null=True, blank=True)
    dropped_at = models.DateTimeField(null=True, blank=True)

    # 자유 노트
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-sourced_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "candidate"],
                name="unique_application_per_project_candidate",
            )
        ]
        indexes = [
            models.Index(fields=["project", "stage"]),
            models.Index(fields=["candidate", "stage"]),
        ]

    def __str__(self) -> str:
        return f"{self.project} × {self.candidate} ({self.get_stage_display()})"

    @property
    def is_active(self) -> bool:
        return self.stage not in (ApplicationStage.HIRED, ApplicationStage.DROPPED)
```

### Promote / Drop 메서드 (service layer에 배치 권장)

```python
# projects/services/application_lifecycle.py

STAGE_ORDER = [
    ApplicationStage.SOURCED,
    ApplicationStage.SCREENED,
    ApplicationStage.PRE_MEETING,
    ApplicationStage.RECOMMENDED,
    ApplicationStage.CLIENT_INTERVIEWING,
    ApplicationStage.HIRED,
]

STAGE_TIMESTAMP_FIELD = {
    ApplicationStage.SOURCED:             "sourced_at",
    ApplicationStage.SCREENED:            "screened_at",
    ApplicationStage.PRE_MEETING:         "pre_met_at",
    ApplicationStage.RECOMMENDED:         "recommended_at",
    ApplicationStage.CLIENT_INTERVIEWING: "interviewing_at",
    ApplicationStage.HIRED:               "hired_at",
}


def promote(application: Application, actor: User) -> Application:
    """다음 stage로 전진."""
    current_idx = STAGE_ORDER.index(application.stage)
    if current_idx >= len(STAGE_ORDER) - 1:
        raise ValueError("이미 최종 단계입니다")
    next_stage = STAGE_ORDER[current_idx + 1]

    application.stage = next_stage
    ts_field = STAGE_TIMESTAMP_FIELD[next_stage]
    setattr(application, ts_field, timezone.now())
    application.save()

    ProjectEvent.objects.create(
        project=application.project,
        event_type="application_promoted",
        actor=actor,
        metadata={
            "application_id": str(application.id),
            "from_stage": STAGE_ORDER[current_idx],
            "to_stage": next_stage,
        },
    )
    return application


def drop(application: Application, reason: DropReason, actor: User, note: str = "") -> Application:
    """드롭. 사유 필수."""
    previous_stage = application.stage
    application.stage = ApplicationStage.DROPPED
    application.drop_reason = reason
    application.drop_note = note
    application.dropped_at = timezone.now()
    application.save()

    ProjectEvent.objects.create(
        project=application.project,
        event_type="application_dropped",
        actor=actor,
        metadata={
            "application_id": str(application.id),
            "from_stage": previous_stage,
            "reason": reason,
            "note": note,
        },
    )
    return application
```

---

## 4. ProjectEvent — 신규 (타임라인)

Round 필드 대신 프로젝트 히스토리를 시계열로 기록.

```python
class ProjectEventType(models.TextChoices):
    PROJECT_CREATED          = "project_created",          "프로젝트 생성"
    APPLICATION_ADDED        = "application_added",        "후보자 추가"
    APPLICATION_PROMOTED     = "application_promoted",     "후보자 전진"
    APPLICATION_DROPPED      = "application_dropped",      "후보자 드롭"
    PHASE_CHANGED            = "phase_changed",            "단계 변경"
    CLIENT_FEEDBACK_RECEIVED = "client_feedback_received", "클라이언트 피드백"
    PROJECT_CLOSED           = "project_closed",           "프로젝트 종료"
    PROJECT_REOPENED         = "project_reopened",         "프로젝트 재개"


class ProjectEvent(BaseModel):
    project = models.ForeignKey(
        Project, on_delete=CASCADE, related_name="events"
    )
    event_type = models.CharField(
        max_length=40, choices=ProjectEventType.choices
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=SET_NULL,
        null=True,
        related_name="project_events",
    )
    metadata = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "-created_at"]),
            models.Index(fields=["event_type"]),
        ]
```

---

## 5. Phase 재계산 signal

```python
# projects/signals.py

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from projects.models import Application, Project, ProjectPhase, ApplicationStage

STAGE_TO_PHASE_ORDER = [
    (ApplicationStage.SOURCED,             ProjectPhase.SEARCHING),
    (ApplicationStage.SCREENED,            ProjectPhase.PRE_MEETING),
    (ApplicationStage.PRE_MEETING,         ProjectPhase.PRE_MEETING),
    (ApplicationStage.RECOMMENDED,         ProjectPhase.SUBMITTED),
    (ApplicationStage.CLIENT_INTERVIEWING, ProjectPhase.INTERVIEWING),
]


def compute_project_phase(project: Project) -> str:
    if project.closed_at is not None:
        return ProjectPhase.CLOSED

    active_stages = set(
        project.applications
        .exclude(stage__in=[ApplicationStage.HIRED, ApplicationStage.DROPPED])
        .values_list("stage", flat=True)
    )

    for stage, phase in STAGE_TO_PHASE_ORDER:
        if stage in active_stages:
            return phase

    # 활성자 없음
    if project.applications.filter(stage=ApplicationStage.HIRED).exists():
        # 성공으로 자동 종료
        project.closed_at = project.closed_at or timezone.now()
        project.close_reason = "success"
        project.save(update_fields=["closed_at", "close_reason"])
        return ProjectPhase.CLOSED

    # 아무도 없는 빈 상태 → SEARCHING으로 유지
    return ProjectPhase.SEARCHING


@receiver([post_save, post_delete], sender=Application)
def update_project_phase(sender, instance, **kwargs):
    project = instance.project
    new_phase = compute_project_phase(project)
    if project.phase != new_phase:
        old_phase = project.phase
        project.phase = new_phase
        project.save(update_fields=["phase"])

        from projects.models import ProjectEvent
        ProjectEvent.objects.create(
            project=project,
            event_type="phase_changed",
            metadata={"from": old_phase, "to": new_phase},
        )
```

---

## 6. 기존 관련 모델의 재해석

### `Contact` — 유지, 역할 축소
- 여전히 존재하나, 더 이상 **상태를 보유하지 않음**
- 의미: "Application에 매달린 커뮤니케이션 이벤트 로그" (전화/이메일/카톡/LinkedIn 시도 기록)
- 스키마 변경 최소화 옵션:
  - **옵션 A**: 스키마 그대로. 의미만 "이벤트 로그"로 재정의
  - **옵션 B**: Application에 FK 추가 (`Contact.application`), Contact.result enum 제거
- 권장: **옵션 B** (Application과 명시적 연결)

### `Submission` — 유지, 역할 명확화
- 의미: "클라이언트에 제출되는 서류 패키지"
- Application이 RECOMMENDED 단계에 도달했을 때 Submission이 생성되는 것으로 해석
- 스키마 변경: `Submission.status` enum(작성중/제출/통과/탈락)은 제거 또는 Application stage와 동기화
- `SubmissionDraft` (AI 초안 파이프라인)는 그대로 유지. Application에 매달림

### `Interview` — 유지
- `Submission`에 매달려 있던 것을 `Application`에 매달리도록 변경
- round, scheduled_at, type, result 모두 유지
- 의미: "Application이 CLIENT_INTERVIEWING일 때의 각 회차 면접"

### `Offer` — **제거**
- 사장님 결정: "협상할 게 없다. 의미 없음"
- 필요한 필드(salary, start_date)는 Application에 직접 추가하거나 별도 `HireRecord` 모델로 분리

### `MeetingRecord` — 유지, 관계 변경
- 현재 `(project, candidate)` FK → `application` FK로 변경
- 의미: "PRE_MEETING 단계의 산출물"
- 나머지 스키마(audio_file, transcript, analysis_json)는 유지

### `ProjectApproval` — 유지
- 기존 그대로. Project.status에서 PENDING_APPROVAL이 제거되더라도 이 모델은 독립적으로 작동

### `ProjectContext`, `Notification`, `PostingSite`, `AutoAction`, `NewsSource`, `NewsArticle`, `ResumeUpload` — 변경 없음

---

## 7. 마이그레이션 전략 (데이터 없음)

### 7-1. 로컬 DB (sqlite 또는 dev postgres)
- 기존 projects 앱 마이그레이션 전체 삭제
- `uv run python manage.py makemigrations projects` → 새 초기 마이그레이션 하나 생성
- `uv run python manage.py migrate` → 클린 재생성

### 7-2. 운영 DB
- 운영 DB에 projects 앱 테이블이 **이미 존재하지 않음** (확인됨)
- 새 마이그레이션을 배포하면 처음부터 새 스키마로 생성됨
- 기존 `candidates`, `contacts`, `meetings` 등 다른 앱 테이블과는 무관

---

## 8. 개발 테스트용 seed 데이터 (구현 시 추가)

현실적인 테스트를 위해 엑셀 데이터 일부를 샘플로 임포트하는 management command를 고려:

```bash
uv run python manage.py seed_from_excel /tmp/project_sheet.xlsx --consultant=김현정 --limit=10
```

- 김현정 탭이 태그 체계가 가장 깔끔하므로 첫 파싱 대상으로 적합
- Result 텍스트를 regex로 파싱해서 drop_reason 자동 매핑
- Candidate도 자동 생성 (이름, 출생년도, 학력 등)

이건 필수는 아니지만 UI 개발·QA에 유용하다.
