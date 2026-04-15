# FINAL SPEC — Project/Application 재설계 최종 확정본

**최종 확정일**: 2026-04-14
**상태**: 구현 준비 완료
**우선순위**: 이 문서가 최종 확정본이며, 01~07 문서는 논의 과정의 히스토리입니다. 구현 시 이 문서를 단일 진실 소스로 삼습니다.

---

## 0. 이 재설계의 한 줄 요지

**synco는 상태 추적 도구가 아니라 할 일 관리 도구이다.** 헤드헌터의 업무는 "어느 단계냐"가 아니라 "오늘 뭘 해야 하느냐"로 관리되어야 한다. 따라서 Project는 마감을 가지고, Application은 매칭 사실만 담고, 실제 업무는 **ActionItem**이라는 1급 개념이 담당한다.

---

## 1. 최종 결정사항 요약

| 항목 | 결정 |
|---|---|
| Project Phase | **2개** — `searching` / `screening` |
| Project Status | **2개** — `open` / `closed` |
| Project 결과 | **2개** — `success` / `fail` |
| Project 마감 | **`deadline` 필드 추가** (클라이언트 요구 마감) |
| Application 본질 | **순수 매칭 객체** — 프로젝트와 후보자의 연결 사실만 담음 |
| Application 상태 필드 | **`hired_at`, `dropped_at`만** (종료 플래그). 진행 단계는 ActionItem에서 파생 |
| ActionItem | **신규 1급 개념** — 헤드헌터의 할 일 단위, 마감·결과·후속 액션을 가짐 |
| ActionType | **DB 테이블** — 관리자 페이지에서 추가/삭제/비활성화 가능 |
| 액션 자동 체인 | **제안만** — 컨설턴트가 확인 버튼을 눌러 다음 액션 생성 |
| 드롭 사유 | **4개 enum** — unfit / candidate_declined / client_rejected / other |
| Phase 자동 파생 | **OR 규칙** — `submit_to_client` 완료된 활성 Application이 하나라도 있으면 `screening` |
| HIRED 처리 | 자동 전원 드롭 + 프로젝트 종료 |
| Auto-close | **v1은 수동만**, 시간 기반 자동 종료 미도입 |
| Contact 모델 | **완전 삭제** — 연락 로그는 ActionItem이 흡수 |
| Offer 모델 | **완전 삭제** — 현실에서 안 쓰임 |
| ProjectEvent 모델 | **생성 안 함** — 히스토리는 ActionItem 타임라인으로 대체 |
| Submission 모델 | 유지, `status` 제거, ActionItem에 1:1 연결로 관계 변경 |
| Interview 모델 | 유지, ActionItem에 1:1 연결로 관계 변경 |
| MeetingRecord 모델 | 유지, ActionItem에 1:1 연결로 관계 변경 |
| 기존 데이터 마이그레이션 | **불필요** — 로컬/운영 DB 모두 projects 앱 데이터 0건 |

---

## 2. 데이터 모델 — 테이블별 정의

### 2.1 Project

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | UUID | 기존 BaseModel |
| `client` | FK → Client | 고객사 |
| `organization` | FK → Organization | 내 소속 조직 |
| `title` | CharField(300) | 포지션 제목 |
| `jd_text` | TextField | 기존 유지 |
| `jd_file` | FileField | 기존 유지 |
| `jd_source` | CharField | 기존 유지 |
| `jd_drive_file_id` | CharField | 기존 유지 |
| `jd_raw_text` | TextField | 기존 유지 |
| `jd_analysis` | JSONField | 기존 유지 |
| `requirements` | JSONField | 기존 유지 |
| `posting_text` | TextField | 기존 유지 |
| `posting_file_name` | CharField | 기존 유지 |
| `assigned_consultants` | M2M → User | 기존 유지 |
| `created_by` | FK → User | 기존 유지 |
| **`phase`** | CharField(20), choices | **자동 파생**. `searching` / `screening` |
| **`status`** | CharField(20), choices | **자동 파생**. `open` / `closed` |
| **`deadline`** | DateField, nullable | 클라이언트가 요구한 전체 마감일 |
| **`closed_at`** | DateTimeField, nullable | 종료 시각 |
| **`result`** | CharField(20), choices, blank | `success` / `fail` / "" |
| **`note`** | TextField, blank | 성공·실패 사유 및 자유 메모 |
| `created_at`, `updated_at` | BaseModel | 생성·수정 시각 |

**enum 정의**
```python
class ProjectPhase(TextChoices):
    SEARCHING = "searching", "서칭"
    SCREENING = "screening", "심사"

class ProjectStatus(TextChoices):
    OPEN = "open", "진행중"
    CLOSED = "closed", "종료"

class ProjectResult(TextChoices):
    SUCCESS = "success", "성공"
    FAIL = "fail", "실패"
```

**자동 동기화 규칙**
- `closed_at`이 세팅되면 `status = closed`, NULL로 돌아가면 `status = open`
- `result`는 `closed` 상태에서만 값이 있음 (open이면 빈 문자열)
- `phase`는 Application 및 ActionItem 변경 signal에서 재계산되어 캐시됨

**인덱스**
```python
class Meta:
    indexes = [
        models.Index(fields=["phase", "status"]),
        models.Index(fields=["deadline"]),
        models.Index(fields=["organization", "status"]),
    ]
```

---

### 2.2 Application

프로젝트와 후보자의 **매칭 사실만** 담는 순수 연결 객체. 진행 단계 정보는 일절 없음.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | UUID | |
| `project` | FK → Project, on_delete=CASCADE | |
| `candidate` | FK → Candidate, on_delete=CASCADE | |
| `created_at` | DateTimeField | = 이력서를 프로젝트에 매칭한 시각 (BaseModel) |
| `updated_at` | DateTimeField | BaseModel |
| `notes` | TextField, blank | 이 지원 건에 대한 자유 메모 |
| **`hired_at`** | DateTimeField, nullable | 입사 확정 시각 (Application 생명 종료 플래그 1) |
| **`dropped_at`** | DateTimeField, nullable | 드롭 시각 (Application 생명 종료 플래그 2) |
| **`drop_reason`** | CharField(30), choices, blank | 드롭 사유 (4개 enum) |
| **`drop_note`** | TextField, blank | 드롭 자유 메모 |
| `created_by` | FK → User, SET_NULL | 누가 매칭했는지 |

**Unique constraint**: `(project, candidate)` — 한 조합은 반드시 하나만.

**enum 정의**
```python
class DropReason(TextChoices):
    UNFIT = "unfit", "부적합"
    CANDIDATE_DECLINED = "candidate_declined", "후보자 거절/포기"
    CLIENT_REJECTED = "client_rejected", "클라이언트 탈락"
    OTHER = "other", "기타"
```

**파생 property**
```python
@property
def is_active(self) -> bool:
    return self.dropped_at is None and self.hired_at is None

@property
def current_state(self) -> str:
    """UI 표시용. DB에 저장하지 않고 최신 완료 ActionItem으로 파생."""
    if self.dropped_at: return "dropped"
    if self.hired_at:   return "hired"

    latest_done = self.action_items.filter(
        status=ActionItemStatus.DONE
    ).order_by("-completed_at").first()

    if not latest_done: return "matched"
    return STATE_FROM_ACTION_TYPE.get(latest_done.action_type.code, "in_progress")
```

`STATE_FROM_ACTION_TYPE`은 코드 상수 매핑 (예: `submit_to_client → "submitted"`, `pre_meeting → "pre_met"`, `interview_round → "interviewing"`).

**Manager 헬퍼**
```python
class ApplicationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(dropped_at__isnull=True, hired_at__isnull=True)

    def submitted(self):
        return self.active().filter(
            action_items__action_type__code="submit_to_client",
            action_items__status="done",
        ).distinct()

    def for_project(self, project):
        return self.filter(project=project)
```

**인덱스**
```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=["project", "candidate"],
            name="unique_application_per_project_candidate",
        )
    ]
    indexes = [
        models.Index(fields=["project", "dropped_at", "hired_at"]),
        models.Index(fields=["candidate"]),
    ]
```

---

### 2.3 ActionType (신규, DB 테이블)

action_type을 관리자 페이지에서 추가·비활성화할 수 있는 테이블.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | UUID | |
| `code` | CharField(40), unique | 코드 식별자 (예: `reach_out`) |
| `label_ko` | CharField(100) | 한국어 표시명 (예: "후보자 연락") |
| `phase` | CharField(20), blank | `searching` / `screening` / "" (any) |
| `default_channel` | CharField(20), blank | 기본 채널 (예: `kakao`, `email`) |
| `output_kind` | CharField(20), blank | `""` / `submission` / `interview` / `meeting` |
| `sort_order` | PositiveIntegerField | UI 정렬 순서 |
| `is_active` | BooleanField, default=True | 새 ActionItem 생성 시 선택 가능한지 |
| `is_protected` | BooleanField, default=False | 시스템 핵심 타입 (삭제 금지) |
| `description` | TextField, blank | 관리자 설명 |
| `suggests_next` | JSONField, default=list | 완료 시 제안할 다음 action_type 코드 목록 |

**enum 정의 (선택 필드용)**
```python
class ActionChannel(TextChoices):
    IN_PERSON = "in_person", "대면"
    VIDEO = "video", "화상"
    PHONE = "phone", "전화"
    KAKAO = "kakao", "카톡"
    SMS = "sms", "문자"
    EMAIL = "email", "이메일"
    LINKEDIN = "linkedin", "LinkedIn"
    OTHER = "other", "기타"

class ActionOutputKind(TextChoices):
    NONE = "", "없음"
    SUBMISSION = "submission", "서류 패키지"
    INTERVIEW = "interview", "면접"
    MEETING = "meeting", "사전미팅"
```

**초기 seed 데이터 (data migration으로 주입)**

서칭 국면:
| code | label_ko | phase | output_kind | is_protected |
|---|---|---|---|---|
| `search_db` | DB 후보자 검색 | searching | — | — |
| `search_external` | 외부 소스 탐색 | searching | — | — |
| `reach_out` | 후보자 연락 | searching | — | — |
| `re_reach_out` | 재연락 | searching | — | — |
| `await_reply` | 답장 대기 | searching | — | — |
| `share_jd` | JD 공유 | searching | — | — |
| `receive_resume` | 이력서 수령 | searching | — | — |
| `convert_resume` | 내부 양식 변환 | searching | — | — |
| `schedule_pre_meet` | 사전미팅 일정 조율 | searching | — | — |
| **`pre_meeting`** | **사전미팅 실시** | **searching** | **meeting** | **✓** |
| `prepare_submission` | 제출 이력서 작성 | searching | — | — |
| `submit_to_pm` | 내부 PM 1차 검토 | searching | — | — |
| **`submit_to_client`** | **클라이언트 제출** | **searching** | **submission** | **✓** |

심사 국면:
| code | label_ko | phase | output_kind | is_protected |
|---|---|---|---|---|
| `await_doc_review` | 서류 심사 대기 | screening | — | — |
| `receive_doc_feedback` | 서류 피드백 수령 | screening | — | — |
| `schedule_interview` | 면접 일정 조율 | screening | — | — |
| **`interview_round`** | **면접 실시** | **screening** | **interview** | **✓** |
| `await_interview_result` | 면접 결과 대기 | screening | — | — |
| **`confirm_hire`** | **입사 확정** | **screening** | — | **✓** |
| `await_onboarding` | 입사일 대기 | screening | — | — |

범용:
| code | label_ko | phase | output_kind | is_protected |
|---|---|---|---|---|
| `follow_up` | 팔로업 | (any) | — | — |
| `escalate_to_boss` | 사장님 에스컬레이션 | (any) | — | — |
| `note` | 단순 메모 | (any) | — | — |

**보호되는 핵심 4개**:
- `pre_meeting` — MeetingRecord 연결 로직이 참조
- `submit_to_client` — Phase 전환 트리거
- `interview_round` — Interview 연결 로직이 참조
- `confirm_hire` — 프로젝트 종료 자동화 트리거

이 4개는 `is_protected=True`로 마킹되어 관리자 페이지에서 삭제 불가. 나머지는 자유롭게 활성/비활성 가능.

**삭제 정책**
- `on_delete=PROTECT` — 실제 DB 삭제는 막힘 (참조하는 ActionItem 있으면 에러)
- 대신 `is_active=False`로 soft delete
- 기존 ActionItem 데이터는 그대로 유지, 새 생성 UI에서만 숨김

---

### 2.4 ActionItem (신규, 1급 개념)

헤드헌터 업무의 기본 단위. 각 Application에 여러 개 달림. 마감·예정·결과를 가짐.

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | UUID | |
| `application` | FK → Application, CASCADE | 어느 매칭 건의 할 일인가 |
| `action_type` | FK → ActionType, PROTECT | 어떤 종류의 액션인가 |
| `title` | CharField(300) | 자동 생성 가능한 한 줄 제목 (예: "김철수에게 LinkedIn 메시지") |
| `channel` | CharField(20), choices, blank | 연락 수단 (reach_out 계열에서만 의미) |
| `scheduled_at` | DateTimeField, nullable | 언제 할 예정인가 |
| `due_at` | DateTimeField, nullable | 언제까지 해야 하는가 |
| `completed_at` | DateTimeField, nullable | 실제 완료 시각 |
| `status` | CharField(20), choices | `pending` / `done` / `skipped` / `cancelled` |
| `result` | TextField, blank | 완료 시 결과 기록 |
| `note` | TextField, blank | 자유 메모 |
| `assigned_to` | FK → User, SET_NULL | 누구 담당인가 |
| `created_by` | FK → User, SET_NULL | 누가 등록했나 |
| `parent_action` | FK → self, SET_NULL | 어떤 액션의 후속으로 생성됐는지 (체인 추적) |
| `created_at`, `updated_at` | BaseModel | |

**enum 정의**
```python
class ActionItemStatus(TextChoices):
    PENDING = "pending", "대기"
    DONE = "done", "완료"
    SKIPPED = "skipped", "건너뜀"
    CANCELLED = "cancelled", "취소"
```

**파생 property**
```python
@property
def is_overdue(self) -> bool:
    if self.status != ActionItemStatus.PENDING: return False
    if self.due_at is None: return False
    return self.due_at < timezone.now()
```

`overdue`는 DB 상태가 아니라 파생 속성. `is_overdue`가 True인 것들을 쿼리로 찾으려면 manager 메서드 또는 annotate 사용.

**Manager 헬퍼**
```python
class ActionItemQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=ActionItemStatus.PENDING)

    def done(self):
        return self.filter(status=ActionItemStatus.DONE)

    def overdue(self):
        return self.pending().filter(due_at__lt=timezone.now())

    def due_soon(self, days=3):
        soon = timezone.now() + timedelta(days=days)
        return self.pending().filter(due_at__lte=soon, due_at__gte=timezone.now())

    def for_user(self, user):
        return self.filter(assigned_to=user)
```

**인덱스**
```python
class Meta:
    ordering = ["due_at", "created_at"]
    indexes = [
        models.Index(fields=["application", "status"]),
        models.Index(fields=["assigned_to", "status", "due_at"]),
        models.Index(fields=["action_type", "status"]),
    ]
```

---

### 2.5 Submission (수정)

`Application`이 아니라 **ActionItem에 1:1로 매달림**. `status` enum 제거.

| 필드 | 변경 사항 |
|---|---|
| `action_item` | **FK → ActionItem**, OneToOne, CASCADE. 기존 `project` + `candidate` FK 제거 |
| `status` | **완전 제거** (`status_choices`도 제거) |
| `template` | 기존 유지 (엑스다임 국문/국영문/영문/고객사 커스텀) |
| `document_file` | 기존 유지 |
| `submitted_at` | 기존 유지. **ActionItem.completed_at과 동기화** (save 오버라이드) |
| `client_feedback` | 기존 유지 |
| `client_feedback_at` | 기존 유지 |
| `notes` | 기존 유지 |
| `consultant` | 기존 유지 |

**관계 규칙**
- ActionItem의 action_type이 `submit_to_client`이고 완료될 때 Submission이 생성됨
- `SubmissionDraft`는 그대로 유지 (Submission에 OneToOne)

---

### 2.6 Interview (수정)

`Submission`이 아니라 **ActionItem에 1:1로 매달림**.

| 필드 | 변경 사항 |
|---|---|
| `action_item` | **FK → ActionItem**, OneToOne, CASCADE. 기존 `submission` FK 제거 |
| `round` | 기존 유지 (PositiveSmallIntegerField, 1차/2차/3차) |
| `scheduled_at` | 기존 유지 |
| `type` | 기존 유지 (대면/화상/전화) |
| `location` | 기존 유지 |
| `result` | 기존 유지 (대기/합격/보류/탈락) |
| `feedback` | 기존 유지 |
| `notes` | 기존 유지 |

**Unique constraint**: `(application_id via action_item, round)` — 같은 Application에 동일 round 중복 금지.

---

### 2.7 MeetingRecord (수정)

`project` + `candidate` FK 대신 **ActionItem에 1:1로 매달림**.

| 필드 | 변경 사항 |
|---|---|
| `action_item` | **FK → ActionItem**, OneToOne, CASCADE. 기존 `project` + `candidate` FK 제거 |
| `audio_file` | 기존 유지 |
| `transcript` | 기존 유지 |
| `analysis_json` | 기존 유지 |
| `edited_json` | 기존 유지 |
| `status` | 기존 유지 (uploaded/transcribing/analyzing/ready/applied/failed) |
| `error_message` | 기존 유지 |
| `applied_at` | 기존 유지 |
| `applied_by` | 기존 유지 |
| `created_by` | 기존 유지 |

**의미**: `pre_meeting` ActionItem이 완료될 때, 녹음 파일이 있으면 MeetingRecord를 추가로 생성. 녹음 없이 메모만 남기면 MeetingRecord 없이 `ActionItem.result`에만 텍스트로 기록.

---

### 2.8 삭제되는 테이블

| 테이블 | 처리 |
|---|---|
| `Contact` | **삭제**. 스키마 드롭. 기존 Contact.result enum도 제거. Channel enum은 `ActionItem.channel`로 이관 |
| `Offer` | **삭제**. OfferForm, 오퍼 관련 뷰/템플릿 모두 제거 |
| `ProjectEvent` | **생성 안 함** (논의 단계에서 제거) |

---

### 2.9 변경 없는 테이블

다음 테이블은 이 재설계의 영향을 받지 않음:
- `ProjectApproval` (승인 워크플로, 독립적)
- `ProjectContext` (업무 연속성 컨텍스트)
- `Notification` (알림 시스템)
- `PostingSite`, `PostingSiteChoice`
- `AutoAction`
- `NewsSource`, `NewsArticle`, `NewsArticleRelevance`
- `ResumeUpload`
- `SubmissionDraft` (Submission에 매달림, 그대로)

---

## 3. 자동 동작 규칙

### 3.1 Project Phase 자동 파생

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

### 3.2 ActionItem 저장 시 Phase 재계산

```python
@receiver([post_save, post_delete], sender=ActionItem)
def recompute_project_phase(sender, instance, **kwargs):
    project = instance.application.project
    new_phase = compute_project_phase(project)
    if project.phase != new_phase:
        project.phase = new_phase
        project.save(update_fields=["phase"])
```

### 3.3 Application 저장 시 Phase 재계산

```python
@receiver([post_save, post_delete], sender=Application)
def recompute_project_phase_on_application(sender, instance, **kwargs):
    project = instance.project
    new_phase = compute_project_phase(project)
    if project.phase != new_phase:
        project.phase = new_phase
        project.save(update_fields=["phase"])
```

### 3.4 HIRED 발생 시 자동 종료

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

### 3.5 다중 HIRED 엣지케이스

이론상 한 후보자가 여러 프로젝트에서 `hired_at`이 찍힐 수 있음 (현실에선 불가). v1에서는:
- 차단하지 않음
- 두 번째 HIRED 발생 시 `logger.warning("duplicate hire detected")` 로그만 남김
- v2에서 필요하면 정책 추가

### 3.6 Project 종료 시 상태 동기화

```python
# Project.save 오버라이드 또는 signal
def sync_project_status(project):
    if project.closed_at and project.status != ProjectStatus.CLOSED:
        project.status = ProjectStatus.CLOSED
    elif not project.closed_at and project.status != ProjectStatus.OPEN:
        project.status = ProjectStatus.OPEN
        project.result = ""  # open으로 되돌아가면 result 초기화
```

### 3.7 ActionItem 완료 시 다음 액션 제안 (자동 생성 아님)

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

초기 `suggests_next` 데이터 예시:
```
reach_out         → [await_reply, schedule_pre_meet]
await_reply       → [re_reach_out, schedule_pre_meet]
schedule_pre_meet → [pre_meeting]
pre_meeting       → [prepare_submission, follow_up]
prepare_submission → [submit_to_client]
submit_to_client  → [await_doc_review]
await_doc_review  → [receive_doc_feedback]
receive_doc_feedback → [schedule_interview, follow_up]
schedule_interview → [interview_round]
interview_round   → [await_interview_result, interview_round]
await_interview_result → [confirm_hire, follow_up]
confirm_hire      → [await_onboarding]
```

---

## 4. 이력서 입력 경로 (5가지)

후보자를 Application으로 매칭하기 전에, 먼저 `Candidate`가 DB에 존재해야 함. Candidate 생성 경로는 5가지:

1. **기존 DB 검색·선택** ⭐ (가장 빈번) — 후보자 DB에서 조건 검색 후 선택
2. **파일 업로드** — 이력서 파일 업로드 → 파서가 Candidate 필드 채움
3. **Drive 폴더 스캔** — 공유폴더 드롭 → 스캔 job이 생성
4. **이메일 수신** — Gmail 첨부 감지 → 자동 생성
5. **음성 입력** — "홍길동을 삼성전자에 추가해줘" → 에이전트가 DB 검색 → 없으면 대화형 수집

**Application 생성은 항상 같은 행위**: 기존 Candidate를 특정 Project에 "붙이는" 한 번의 동작. 5가지 경로 중 1번은 기존 후보자를 재사용, 2~5번은 새 Candidate를 만들면서 같은 흐름의 UI에서 Application까지 생성.

---

## 5. UI 설계

### 5.1 3-레벨 네비게이션 + 대시보드

```
Dashboard (홈): 오늘의 할 일 — 컨설턴트 중심
   ↓
Level 1: 프로젝트 칸반 (2-phase) — 프로젝트 중심 전체 뷰
   ↓
Level 2: 프로젝트 상세 — Application 목록 + 각 Application의 ActionItem
   ↓
Level 3: 후보자 상세 — 이 후보자의 모든 Application 나열
```

### 5.2 Dashboard — 오늘의 할 일

**메인 화면**. 컨설턴트가 로그인하면 가장 먼저 보는 뷰.

```
┌────────────────────────────────────────────────────────┐
│ 박정일님, 안녕하세요. 오늘 할 일 7건이 있습니다.           │
├────────────────────────────────────────────────────────┤
│ ⚠ 마감 지남 (2건)                                        │
│   • 이영희 답장 확인 (4/6 마감, 2일 지남)                 │
│     [재연락] [포기] [상세]                                │
│   • 최지훈 사전미팅 준비 (4/7 마감, 1일 지남)              │
│     [완료] [건너뛰기] [상세]                              │
├────────────────────────────────────────────────────────┤
│ 📌 오늘 할 일 (3건)                                       │
│   • 김철수에게 LinkedIn 메시지 (reach_out)                │
│     [완료] [건너뛰기] [나중에]                            │
│   • 박민수 사전미팅 14:00 (in_person)                     │
│     [상세] [노트 작성]                                   │
│   • 신규 후보자 2명 서치 (prepare_submission 후속)         │
├────────────────────────────────────────────────────────┤
│ 📅 다가오는 일정 (3일 내) (2건)                           │
│   • 4/10 11:00 이민수 1차 면접                           │
│   • 4/11 마감 삼성전자 프로젝트 최종 제출                  │
└────────────────────────────────────────────────────────┘
```

**HTMX 엔드포인트**
- `GET /dashboard/` — 전체 대시보드
- `POST /actions/<id>/complete/` — 완료 처리
- `POST /actions/<id>/skip/` — 건너뛰기
- `POST /actions/<id>/reschedule/` — 나중에 하기 (due_at 연기)

### 5.3 Level 1 — 프로젝트 칸반 (2-phase)

```
┌────────────────────┬────────────────────┬──────────────┐
│ 🔍 서칭             │ 📋 심사            │ 종료 ▶       │
│                    │                    │              │
│ [삼성전자 AI]       │ [Vatech 보안]      │ [덕산 품질]  │
│ 매칭 10건           │ 매칭 3건 (제출 3)   │ ✅ 성공      │
│ ⏰ 4/30 마감 16일   │ ⏰ 4/25 마감 11일   │              │
│ 📝 할 일 5 (마감 1)  │ 📝 할 일 2          │              │
│                    │                    │              │
│ [OneStore 백엔드]   │ [한미약품 마케팅]   │ [ASICS]     │
│ 매칭 7건           │ 매칭 5건 (제출 2)   │ ❌ 실패      │
│ ⏰ 5/15 마감        │ ⏰ 4/28 마감 14일   │              │
│ 📝 할 일 3          │ 📝 할 일 7 (마감 2) │              │
└────────────────────┴────────────────────┴──────────────┘
```

**카드에 표시**
- 프로젝트 이름 (Client | Position)
- 활성 Application 수 + 서칭 국면이면 "(제출 N)"
- 마감일 + 남은 일수 (임박 시 빨간색)
- 할 일 건수 (마감 지남 수 괄호)
- 성공/실패 표시 (종료 컬럼에서만)

**인터랙션**
- 카드 클릭 → Level 2 이동
- 드래그 앤 드롭: **비활성화** (phase는 자동 파생)
- 필터 바: 담당자, 고객사, 기간, phase, 마감 임박

### 5.4 Level 2 — 프로젝트 상세

**상단 — 프로젝트 요약**
```
삼성전자 | AI Engineer (대리~과장)              [ 메뉴 ▾ ]
서칭 · 진행중 · 마감 4/30 (16일) · 매칭 10건
담당: 박정일 · JD 보기 · 종료 조건 편집
                                    [ + 후보자 추가 ]
```

**탭 구성**
1. **Application 목록** (기본)
2. **타임라인** (ActionItem 히스토리)
3. **JD / 메타**

**Application 목록 — 각 행**
```
┌───────────────────────────────────────────────────────┐
│ 김철수  1992년생·현대차·서울대 5년차   [Level 3 →]   │
│ 상태: 사전미팅 완료 · 매칭 12일째                       │
│                                                       │
│   진행 중 할 일 (2)                                    │
│   • prepare_submission  due 4/11 (3일 남음)            │
│     [완료] [건너뛰기]                                  │
│   • follow_up: 추천서 요청     due 4/13                │
│                                                       │
│   완료된 액션 (5)  ▼                                   │
├───────────────────────────────────────────────────────┤
│ 이영희  1985년생·삼성SDS·KAIST 12년차                   │
│ 상태: 제출됨 · 매칭 15일째                              │
│   진행 중 할 일 (1)                                    │
│   • await_doc_review  due 4/18                         │
│ ...                                                    │
├───────────────────────────────────────────────────────┤
│ 박민수  드롭됨 (후보자 거절/포기)                       │
│   드롭 사유: 이직 의사 없음                              │
│                                     [복구]              │
└───────────────────────────────────────────────────────┘
```

**각 Application 카드에서 가능한 액션**
- **`+ 액션 추가`**: 새 ActionItem 생성 모달 (action_type 선택 → 필드 입력 → 저장)
- **진행 중 액션의 `[완료]`**: 결과 입력 모달 → 저장 → 후속 액션 제안 팝업
- **진행 중 액션의 `[건너뛰기]`**: `status=skipped`, 간단한 사유 선택
- **`[드롭]`** (Application 레벨): drop_reason 모달
- **`[복구]`** (드롭된 것): dropped_at=null로 되돌림

**추가 액션**
- `+ 후보자 추가`: 5가지 입력 경로 (DB 검색 탭 / 파일 업로드 / Drive / 이메일 / 음성)
- `프로젝트 종료`: 수동 종료 버튼, result 선택 + note 입력
- `JD 편집`

### 5.5 Level 3 — 후보자 상세

```
김철수
1992년생 · 서울대 공대 · 5년차
현대차 → 네이버 → 카카오
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
이 후보자의 모든 Application (3건)

┌──────────────────────────────────────────────┐
│ [삼성전자 | AI Engineer]                     │
│ 사전미팅 완료 · 매칭 12일째                    │
│ 진행 중 할 일 2건 · 마감 4/30                 │
│                                 [보기 →]      │
├──────────────────────────────────────────────┤
│ [네이버 | ML Researcher]                     │
│ 제출됨 · 매칭 45일째                          │
│ 진행 중 할 일 1건 · 마감 4/20                 │
│                                 [보기 →]      │
├──────────────────────────────────────────────┤
│ [카카오 | 데이터 엔지니어] (드롭됨)             │
│ 사유: 이직 의사 없음                          │
│                                 [보기 →]      │
└──────────────────────────────────────────────┘
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
커리어 / 학력 / 기술 스택 (기존 candidate detail 재활용)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사전미팅 기록 (MeetingRecord 모음)
```

### 5.6 ActionItem 생성/완료 모달

**완료 모달**
```
┌─────────────────────────────────────┐
│ 김철수에게 LinkedIn 메시지 - 완료     │
├─────────────────────────────────────┤
│ 결과: [ 답장 옴, 관심 있음        ]  │
│ 메모: [ 이력서 보내달라고 함       ] │
│                                     │
│ ☑ 완료로 기록                        │
│                                     │
│ 제안 후속 액션:                      │
│  ☑ await_reply                      │
│  ☐ schedule_pre_meet                │
│                                     │
│           [취소]  [저장 + 후속 생성] │
└─────────────────────────────────────┘
```

### 5.7 필요한 HTMX 엔드포인트

```
# Dashboard
GET  /dashboard/                       # 오늘의 할 일
GET  /dashboard/partial/todo/          # 할 일 리스트 부분 갱신

# Project
GET  /projects/                        # 칸반 (2-phase)
GET  /projects/<id>/                   # 프로젝트 상세
GET  /projects/<id>/applications/      # Application 리스트 partial
GET  /projects/<id>/timeline/          # 타임라인 partial
POST /projects/<id>/close/             # 수동 종료
POST /projects/<id>/add_candidate/     # Application 생성

# Application
POST /applications/<id>/drop/          # 드롭 (reason, note)
POST /applications/<id>/restore/       # 드롭 복구
POST /applications/<id>/hire/          # 입사 확정 (자동 종료 트리거)

# ActionItem
GET  /applications/<id>/actions/       # Application의 ActionItem 목록
POST /applications/<id>/actions/new/   # 새 ActionItem 생성 (수동)
POST /actions/<id>/complete/           # 완료
POST /actions/<id>/skip/               # 건너뛰기
POST /actions/<id>/reschedule/         # 마감 연기
POST /actions/<id>/propose_next/       # 완료 후 후속 액션 생성 (제안 목록에서 선택)

# Candidate (Level 3)
GET  /candidates/<id>/                 # 기존 재활용 + 하단에 Application 리스트 추가
```

---

## 6. 사례 시나리오 검증

### 6.1 완전한 프로젝트 라이프사이클

**4/1 프로젝트 수주**
- 사장님이 삼성전자에서 AI Engineer 의뢰 받음
- `Project` 생성: `deadline=4/30`, `phase=searching`, `status=open`, `closed_at=NULL`, `result=""`
- 박정일에게 할당

**4/2 초기 서칭 — DB 검색 경로**
- 박정일이 후보자 DB에서 경력 5~10년 AI/ML 조건으로 검색 → 김철수, 이영희 선택
- "프로젝트에 추가" → 각각 `Application` 생성
- 각 Application에 자동으로 `reach_out` ActionItem 1개씩 생성 (시스템이 action_type.suggests_next 기반 제안, 박정일 확인)
- `due_at = 4/4` 자동 세팅

**4/3 파일 업로드 경로로 1명 추가**
- 박정일이 지인 소개로 박민수 이력서 파일 수신
- 파일 업로드 → 파서가 Candidate 생성 → 프로젝트 매칭 → Application + `reach_out` ActionItem 생성

**박정일 대시보드 (4/3 아침)**
```
오늘 할 일 3건
  • 김철수 reach_out (kakao) due 4/4
  • 이영희 reach_out (email) due 4/4
  • 박민수 reach_out (phone) due 4/4
```

**4/3 실제 연락**
- 김철수 카톡: 답장 즉시 옴, 관심 있음 → `reach_out` 완료 (`result="관심, 이력서 요청"`) → 후속 제안 popup에서 `schedule_pre_meet` 선택 → 새 ActionItem 생성
- 이영희 이메일: 답장 없음 → `reach_out` 완료 (`result="답장 대기"`) → `await_reply` 선택
- 박민수 전화: 이직 의사 없음 → `reach_out` 완료 (`result="거절"`) → **Application 드롭** (`drop_reason=candidate_declined`, `drop_note="이직 의사 없음"`)

**4/5 김철수 사전미팅 일정 확정**
- `schedule_pre_meet` 완료 (`result="4/8 14:00 강남역"`) → 후속 `pre_meeting` 생성 (`scheduled_at=4/8 14:00`, `channel=in_person`)

**4/6 이영희 답장 마감 지남**
- 박정일 대시보드에 "마감 지남 1건" 표시 (`is_overdue=True`)
- 박정일이 `re_reach_out` 선택 → 새 ActionItem 생성, 카톡으로 재연락

**4/8 김철수 사전미팅**
- 박정일이 김철수와 대면 미팅, 녹음
- `pre_meeting` ActionItem 완료 버튼 → 모달에서 "녹음 파일 업로드" 선택 → `MeetingRecord` 생성 (1:1 연결)
- AI 전사/분석 파이프라인 실행 → `MeetingRecord.transcript`, `analysis_json` 채워짐
- ActionItem `result = "전체적으로 괜찮음, 제출 추천"`, `status=done`
- 후속 `prepare_submission` 자동 제안 → 박정일이 확정

**4/10 김철수 제출**
- `prepare_submission` 완료 → 후속 `submit_to_client` 생성
- AI가 삼성전자 양식에 맞춰 이력서 초안 작성 (`SubmissionDraft` 파이프라인)
- 박정일이 검토·수정 후 클라이언트 이메일 전송
- `submit_to_client` 완료 버튼 → `Submission` 모델 생성 (1:1), 파일 첨부
- **Signal 발동** → `Project.phase = screening` (제출 완료된 활성 액션이 생김)
- 후속 `await_doc_review` 자동 생성 (`due_at = 4/15`)

**4/14 클라이언트 피드백 — "더 찾아주세요"**
- 클라이언트 이메일: "김철수 좋은데 다른 옵션도 볼게요"
- 박정일이 `await_doc_review` 완료 (`result="추가 후보자 요청"`) → 후속 `receive_doc_feedback` 대신 `follow_up: 추가 서치` 선택
- 새 후보자 2명 매칭 (신규1, 신규2)
- **Phase 그대로 `screening`** — 김철수 submit_to_client 완료 액션이 여전히 활성. OR 규칙으로 screening 유지.

**4/16 이영희 2차 재연락도 답장 없음 → 드롭**
- 박정일이 이영희 Application 드롭 (`drop_reason=candidate_declined`, `drop_note="2차 재연락도 무응답"`)

**4/18 김철수 1차 면접**
- `schedule_interview` ActionItem 생성·완료 → 후속 `interview_round` 생성
- `interview_round` ActionItem 완료 시 `Interview` 모델 생성 (1:1, round=1, scheduled_at=4/18, type=대면, location=삼성전자 강남)
- 면접 후 `Interview.result=합격`, `feedback="기술 탄탄, 2차 추천"`
- 후속 제안: `interview_round` (2차) 또는 `confirm_hire`

**4/20 2차 면접 합격 + 입사 확정**
- `interview_round` (2차) 완료 → 후속 `confirm_hire` 생성
- 박정일이 `confirm_hire` 완료 버튼 → "이 후보자를 HIRED 처리하시겠습니까?" 확인 모달
- 확정 → `Application.hired_at = now()`, `status=done`

**Signal 자동 발동** — HIRED 처리:
1. `Project.closed_at = 2026-04-20 15:00, status=closed, result=success, note += "김철수 입사 확정"`
2. 나머지 활성 Application(신규1, 신규2) 자동 드롭: `dropped_at=now, drop_reason=other, drop_note="입사자(김철수) 확정으로 포지션 마감"`
3. `compute_project_phase` → closed이므로 그대로 유지, UI는 종료 표시

**최종 상태**
```
Project:
  phase=screening (마지막 값, 종료된 프로젝트라 의미 없음)
  status=closed
  closed_at=2026-04-20
  result=success
  note="김철수 입사 확정"

Applications:
  김철수: hired_at=4/20             — 성공
  이영희: dropped_at=4/16, candidate_declined
  박민수: dropped_at=4/3, candidate_declined
  신규1:  dropped_at=4/20, other (입사자 확정으로 포지션 마감)
  신규2:  dropped_at=4/20, other (입사자 확정으로 포지션 마감)

ActionItems: 모두 done/skipped/cancelled 상태
  김철수: reach_out → schedule_pre_meet → pre_meeting (MeetingRecord) →
          prepare_submission → submit_to_client (Submission) →
          await_doc_review → schedule_interview → interview_round (Interview 1차) →
          interview_round (Interview 2차) → confirm_hire
```

### 6.2 Phase 재계산 엣지케이스

**케이스 A: 심사 국면 중 신규 후보자 추가**
- 상태: 3명 submit_to_client 완료 → phase=screening
- 신규 후보자 2명 매칭 (ActionItem 없이 Application만 생성된 시점)
- **Phase 그대로 screening** (기존 3명의 제출 완료 활성 액션 유지)
- 신규 2명에 대한 reach_out ActionItem 생성돼도 phase 변경 없음

**케이스 B: 제출된 후보자들 전원 드롭**
- 상태: 3명 submit_to_client 완료 → phase=screening
- 3명 모두 드롭 → `Application.dropped_at` 세팅
- `compute_project_phase` 재계산: 활성 Application의 submit_to_client 완료 액션 0건
- **Phase = searching**으로 자동 전환

**케이스 C: 빈 프로젝트 (Application 0건)**
- `Project.closed_at = None` → phase = `searching` (기본값)

**케이스 D: 종료된 프로젝트에 Application 추가 시도**
- `project.closed_at != None`이면 UI 레벨에서 "프로젝트가 종료되었습니다. 재개하시겠습니까?" 확인 모달
- 재개 선택 시 `closed_at=None`, `result=""`, `status=open`으로 되돌리고 Application 추가

---

## 7. 영향 범위

### 7.1 수정되는 파일 (요약)

| 파일 | 영향 |
|---|---|
| `projects/models.py` (849줄) | 전면 재정의 — 새 모델 추가, 기존 수정, 일부 삭제 |
| `projects/signals.py` (116줄) | 재작성 — phase 재계산, HIRED 처리, overdue |
| `projects/views.py` (3,030줄) | 대규모 재작성 — 칸반/상세/대시보드/ActionItem CRUD |
| `projects/forms.py` (522줄) | 재작성 — 기존 status 폼 제거, 새 폼 추가 |
| `projects/urls.py` (341줄) | 확장 — 새 라우트 추가, 오퍼 라우트 제거 |
| `projects/admin.py` | ActionType 관리자 등록 |
| `projects/services/` 전체 | lifecycle.py, collision.py, dashboard.py, auto_actions.py, submission.py, urgency.py 모두 재작성 |
| `projects/services/action_lifecycle.py` | **신규** — ActionItem complete/skip/propose |
| `projects/services/application_lifecycle.py` | **신규** — drop/restore/hire |
| `projects/services/phase.py` | **신규** — compute_project_phase |
| `projects/migrations/` | **기존 전체 삭제 후 0001_initial 재생성** |
| `projects/management/commands/seed_action_types.py` | **신규** — data migration 또는 command |
| `projects/templates/projects/*.html` | 전면 재작성 — 칸반, 상세, 대시보드 |

### 7.2 변경되지 않는 파일

- `candidates/` 앱 전체 (Candidate 모델과 뷰)
- `clients/` 앱
- `accounts/` 앱
- `meetings/` 앱 (MeetingRecord는 projects 앱에 있음, 별도 meetings 앱 없음)
- `common/` 앱

---

## 8. 구현 단계 (Phase별 요약)

전체 6 phase로 진행. 각 phase는 별도 `plans/phase-N-*.md` 문서에 상세 태스크로 분할되어 있음.

| Phase | 주제 | 예상 시간 | 리스크 |
|---|---|---|---|
| **Phase 1** | 모델 재정의 + 마이그레이션 클린 재생성 | 0.5-1일 | 낮음 |
| **Phase 2** | 서비스 레이어 + signal + ActionType seed | 0.5-1일 | 중 |
| **Phase 3** | 뷰 재작성 (칸반 / 상세 / 대시보드 / ActionItem CRUD) | 1-2일 | 중 |
| **Phase 4** | 템플릿/UI 재작성 | 1.5-2일 | 중-높음 |
| **Phase 5** | 테스트 + seed 데이터 | 0.5-1일 | 낮음 |
| **Phase 6** | 레거시 제거 (Offer/Contact) + 린트 + E2E 확인 | 0.5일 | 낮음 |
| **합계** | | **4.5-7.5일** | |

**브랜치 정책**: 새 `feat/project-application-redesign` 브랜치에서 작업. 현재 `feat/rbac-onboarding`과 분리.

**운영 배포**: RBAC 작업 완료 후. 두 큰 변화를 동시에 배포하지 않음.

---

## 9. 디자인 원칙 (구현 시 반드시 지킬 것)

1. **컨설턴트는 ActionItem만 조작한다. Phase는 시스템이 파생.** UI에 phase 이동 버튼 없음.
2. **ActionItem은 "오늘 내가 뭘 해야 하는가"를 답해야 한다.** 데이터 정합성이 아니라 업무 가이드가 우선.
3. **자동 체인은 제안, 생성은 수동.** 확인 버튼 없이 자동 생성하지 않음.
4. **드롭 사유는 4개 enum**. 자유 텍스트(drop_note)는 필드로 따로. 과도한 분류 금지.
5. **ActionType은 DB 테이블**. 코드 수정 없이 추가·비활성화 가능. 핵심 4개만 보호.
6. **산출물은 전용 모델(Submission/Interview/MeetingRecord)에 저장**. ActionItem.result는 가벼운 텍스트만.
7. **M:N 관계를 숨기지 않는다.** 후보자 상세에서 모든 Application을 동시에 보여줌.
8. **마감 관리를 최우선 UX로**. 대시보드는 "할 일 + 마감"이 메인. phase/stage는 보조.

---

## 10. 열린 사안 (향후 결정)

- **Auto-close 정책**: v2에서 시간 기반 자동 종료 도입 여부
- **벌크 액션**: 여러 Application의 ActionItem을 동시에 완료/생성하는 기능
- **캘린더 연동**: Google Calendar와 scheduled_at 동기화
- **Slack/Telegram 알림**: 마감 임박·오버듀 자동 알림
- **다중 HIRED 정책**: 한 후보자가 여러 프로젝트 동시 HIRED 처리 규칙
- **리포트/분석**: 드롭 사유 패턴, 단계별 소요일, 컨설턴트 성과 집계

---

**이 문서가 최종 확정본입니다. 이 아래로 Phase별 구현계획서(`plans/phase-N-*.md`)가 이 문서를 참조합니다.**
