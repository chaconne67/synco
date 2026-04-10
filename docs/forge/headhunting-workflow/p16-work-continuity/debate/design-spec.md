# P16: Work Continuity

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
| `/projects/<pk>/context/resume/` | POST | `project_context_resume` | 중단된 작업 재개 |
| `/projects/<pk>/context/discard/` | POST | `project_context_discard` | 중단된 작업 취소 |
| `/projects/<pk>/auto-actions/` | GET | `project_auto_actions` | 자동 생성물 목록 |
| `/projects/<pk>/auto-actions/<action_pk>/apply/` | POST | `auto_action_apply` | 자동 생성물 적용 |
| `/projects/<pk>/auto-actions/<action_pk>/dismiss/` | POST | `auto_action_dismiss` | 자동 생성물 무시 |

---

## 모델

### ProjectContext (P01 정의 완료)

| 필드 | 타입 | 설명 |
|------|------|------|
| `project` | FK → Project | 대상 프로젝트 |
| `consultant` | FK → User | 컨설턴트 |
| `last_step` | CharField | 마지막 작업 단계 |
| `pending_action` | CharField | 대기 중인 액션 설명 |
| `draft_data` | JSONField | 작성 중이던 폼/대화 상태 |
| `updated_at` | DateTimeField | 마지막 업데이트 |

### AutoAction (신규, projects 앱)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `project` | FK → Project | 대상 프로젝트 |
| `trigger_event` | CharField | 트리거 이벤트명 |
| `action_type` | CharField choices | 자동 생성물 유형 |
| `title` | CharField | 표시 제목 |
| `data` | JSONField | 생성된 데이터 (초안 내용 등) |
| `status` | CharField choices | pending / applied / dismissed |
| `created_at` | DateTimeField | 생성 시각 |

```python
class ActionType(models.TextChoices):
    POSTING_DRAFT = "posting_draft", "공지 초안"
    CANDIDATE_SEARCH = "candidate_search", "후보자 자동 서칭"
    SUBMISSION_DRAFT = "submission_draft", "제출 서류 초안"
    OFFER_TEMPLATE = "offer_template", "오퍼 템플릿"
    FOLLOWUP_REMINDER = "followup_reminder", "팔로업 리마인더"
    RECONTACT_REMINDER = "recontact_reminder", "재컨택 리마인더"
```

---

## 업무 상태 자동 보존

### 보존 시점

폼 입력 중 페이지 이탈, 대화 세션 중단 시 자동 저장:

| 시점 | 저장 방법 |
|------|----------|
| 폼 입력 중 페이지 이탈 | JS `beforeunload` → HTMX POST로 draft_data 저장 |
| 보이스 대화 중단 | 대화 세션 종료 시 자동 저장 (P14 연동) |
| 명시적 "나중에" | 사용자가 "나중에" 클릭 → 컨텍스트 저장 |

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

### 재개 UI

프로젝트 진입 시 미완료 컨텍스트가 있으면 자동 표시:

```
┌─ Rayence 품질기획 ──────────────────────────────────────┐
│  ⏸️ 중단된 작업                                          │
│  홍길동 컨택 결과 입력 (3시간 전 중단)                      │
│  채널(전화) 선택됨 — 결과만 입력하면 완료                    │
│  [이어서 하기]  [새로 시작]  [취소]                        │
└──────────────────────────────────────────────────────────┘
```

보이스 에이전트 재개:
```
🎙️ "아까 하던 거 이어서 하자"
🤖 마지막 작업: Rayence 품질기획
   홍길동 컨택 결과 입력 중이었습니다.
   결과만 남았어요. 이어서 할까요?
```

---

## 이벤트 트리거 자동 생성

### 트리거 매핑

| 트리거 이벤트 | 자동 생성물 | 알림 |
|-------------|-----------|------|
| 프로젝트 등록 | 공지 초안 + 후보자 자동 서칭 | "공지/후보자 준비됨" |
| 컨택 결과 = 관심 있음 | 제출 서류 AI 초안 | "서류 초안 검토 요청" |
| 서류 제출 완료 | 팔로업 리마인더 (3일 후) | "팔로업 알림 예정" |
| 면접 합격 | 오퍼 템플릿 | "오퍼 초안 준비됨" |
| 잠금 만료 임박 (1일 전) | 재컨택 리마인더 | "컨택 잠금 내일 만료" |

### 구현: Django Signals

`projects/signals.py`:

```python
@receiver(post_save, sender=Project)
def on_project_created(sender, instance, created, **kwargs):
    if created and instance.status == "new":
        generate_posting_draft.delay(instance.pk)
        auto_search_candidates.delay(instance.pk)

@receiver(post_save, sender=Contact)
def on_contact_result(sender, instance, **kwargs):
    if instance.result == "interested":
        generate_submission_draft.delay(instance.pk)

@receiver(post_save, sender=Interview)
def on_interview_result(sender, instance, **kwargs):
    if instance.result == "pass":
        generate_offer_template.delay(instance.submission.pk)
```

자동 생성 작업은 동기 실행 (Celery 미사용 시) 또는 management command로 배치 처리.

### 자동 생성물 표시

프로젝트 개요 탭에 배너로 표시:

```
┌─ 자동 생성 (2건) ──────────────────────────────────────┐
│  📄 공지 초안이 준비되었습니다.         [확인] [무시]     │
│  🔍 후보자 8명을 찾았습니다.           [확인] [무시]     │
└────────────────────────────────────────────────────────┘
```

---

## 서비스 구조

| 파일 | 역할 |
|------|------|
| `projects/services/context.py` | ProjectContext CRUD + 재개 로직 |
| `projects/services/auto_actions.py` | 자동 생성물 생성 + 적용/무시 |
| `projects/signals.py` | 이벤트 트리거 시그널 핸들러 |
| `projects/services/generators/posting.py` | 공지 초안 자동 생성 |
| `projects/services/generators/search.py` | 후보자 자동 서칭 |
| `projects/services/generators/offer.py` | 오퍼 템플릿 자동 생성 |

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| 상태 보존 | 폼 입력 중단 → ProjectContext 저장 확인 |
| 재개 표시 | 프로젝트 진입 시 중단 작업 배너 표시 |
| 재개 동작 | "이어서 하기" → 중단 시점의 폼 복원 |
| 취소 | "취소" → ProjectContext 삭제 |
| 프로젝트 등록 트리거 | 등록 → AutoAction(공지 초안 + 서칭) 생성 |
| 관심 결과 트리거 | 컨택 관심 → AutoAction(서류 초안) 생성 |
| 면접 합격 트리거 | 합격 → AutoAction(오퍼 템플릿) 생성 |
| 자동 생성물 적용 | 확인 → 실제 데이터에 반영 |
| 자동 생성물 무시 | 무시 → status=dismissed |
| 보이스 재개 | "아까 하던 거" → 컨텍스트 복원 + 대화 이어가기 |

---

## 산출물

- `projects/models.py` — AutoAction 모델 추가
- `projects/views.py` — context/auto-action 관련 뷰 6개
- `projects/urls.py` — `/projects/<pk>/context/`, `/projects/<pk>/auto-actions/` URL
- `projects/signals.py` — 이벤트 트리거 시그널
- `projects/services/context.py` — 업무 연속성 서비스
- `projects/services/auto_actions.py` — 자동 생성물 관리
- `projects/services/generators/posting.py` — 공지 초안 생성
- `projects/services/generators/search.py` — 후보자 자동 서칭
- `projects/services/generators/offer.py` — 오퍼 템플릿 생성
- `projects/templates/projects/partials/context_banner.html` — 중단 작업 배너
- `projects/templates/projects/partials/auto_actions.html` — 자동 생성물 목록
- `static/js/context-autosave.js` — 폼 이탈 시 자동 저장
- 테스트 파일
