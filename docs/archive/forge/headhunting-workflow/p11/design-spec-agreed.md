# P11: Project Collision & Approval (확정 설계서)

> **Phase:** 11
> **선행조건:** P03 (프로젝트 CRUD), P02 (고객사 관리)
> **산출물:** 유사 프로젝트 충돌 감지 + 승인 플로우 + 관리자 승인 큐

---

## 목표

프로젝트 등록 시 같은 고객사의 유사 프로젝트를 자동 감지하고, 높은 유사도(>= 0.7)의 충돌 시
관리자(OWNER) 승인을 거쳐야 등록되도록 한다.

---

## 역할 매핑

| Role | 권한 |
|------|------|
| **OWNER** | 승인 큐 열람, 판단(승인/합류/메시지/반려) |
| **CONSULTANT** | 프로젝트 등록, 충돌 시 승인 요청(자동), 취소 |
| **VIEWER** | 열람만 (생성/승인 불가) |

---

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/projects/new/check-collision/` | POST | `project_check_collision` | 충돌 감지 (HTMX partial) |
| `/projects/<pk>/approval/cancel/` | POST | `approval_cancel` | 승인 요청 취소 (요청자) |
| `/projects/approvals/` | GET | `approval_queue` | 관리자 승인 요청 큐 |
| `/projects/approvals/<appr_pk>/decide/` | POST | `approval_decide` | 관리자 판단 |

**변경사항:** `/admin/approvals/`를 `/projects/approvals/`로 이동 (Django admin URL 충돌 방지). `/projects/<pk>/approval/request/`는 삭제 (project_create에서 원자적 생성).

---

## 모델

### ProjectApproval (기존 스켈레톤 확장)

기존 `projects/models.py`의 `ProjectApproval` 스켈레톤에 `conflict_score`, `conflict_type` 필드를 추가한다.

```python
class ConflictType(models.TextChoices):
    HIGH = "높은중복", "높은 중복 가능성"     # 같은 고객사 + 제목 유사도 >= 0.7
    MEDIUM = "참고정보", "참고 정보"          # 같은 고객사 + 유사도 < 0.7

# ProjectApproval.Status는 기존 한국어 저장값 유지:
# "대기", "승인", "합류", "반려"
```

추가 필드:
- `conflict_score` (FloatField, default=0.0) — 유사도 점수 0.0~1.0
- `conflict_type` (CharField, choices=ConflictType.choices, blank=True) — 충돌 유형

### Project 모델

`ProjectStatus.PENDING_APPROVAL`은 이미 존재 (`"pending_approval"`, `"승인대기"`).

**상태 보호:**
- `pending_approval` 상태의 프로젝트는 읽기 전용. 컨택/제출/면접/오퍼 생성 차단.
- `pending_approval` -> `new` 전환은 승인 서비스만 수행. 폼/PATCH API에서 직접 전환 불가.

---

## 충돌 감지 로직

### 감지 시점

프로젝트 등록 폼에서 고객사와 제목 **양쪽 필드 변경** 시 HTMX 충돌 체크:

```
client 또는 title 변경/blur
  → JS: client_id와 title 둘 다 존재하는지 확인
  → 둘 다 있으면: hx-post="/projects/new/check-collision/"
  → body: {client_id, title}
  → 서버: 충돌 감지 결과 HTML partial 반환
```

### 매칭 기준

| 조건 | 판정 | conflict_type | 차단 여부 |
|------|------|---------------|----------|
| 같은 고객사 + 제목 유사도 >= 0.7 | 높은 중복 가능성 | `높은중복` | **차단** (승인 필요) |
| 같은 고객사 + 제목 유사도 < 0.7 | 참고 정보 | `참고정보` | 비차단 (경고만) |
| 다른 고객사 | 감지 없음 | — | — |

**포지션 유사도 판정:** `projects/services/collision.py`

```python
def detect_collisions(client_id: UUID, title: str, org) -> list[dict]:
    """
    유사 프로젝트 목록 반환 (최대 5건, 유사도 내림차순).
    각 dict: {project, score, conflict_type, consultant_name, status_display}
    진행 중(closed 아닌) 프로젝트만 대상.
    """
```

1. 같은 고객사 + 같은 조직(`organization=org`)의 진행 중 프로젝트 필터
2. 핵심 키워드 추출 (직급/부서/직무 분리)
3. 키워드 매칭 점수 계산 (예: "품질기획팀장" vs "품질기획파트장" -> 0.9)
4. 유사도 내림차순 정렬, 최대 5건 반환

### 가시성 정책

충돌 감지 시 제한적 정보만 공개:
- 담당자명 (first_name), 프로젝트 상태
- JD, 후보자 목록, 상세 정보는 비공개

---

## 프로젝트 등록 수정 (P03 확장)

`project_create` 뷰에 충돌 감지 분기 추가:

1. **충돌 없음** (high 유사도 0건) -> 기존대로 `status=new`로 즉시 등록
2. **높은 충돌 감지** (high 유사도 1건 이상) -> `transaction.atomic()` 내에서:
   - `Project(status=pending_approval)` 생성
   - `ProjectApproval(project=project, requested_by=user, conflict_project=최고유사도프로젝트, conflict_score=score, conflict_type=type, status="대기")` 생성
   - 요청자에게 "승인 대기 중" 안내 페이지로 리다이렉트

**ProjectForm 수정:** `status` 필드를 폼에서 제거. 상태는 뷰 로직에서만 설정.

---

## 프리랜서 화면

**충돌 감지 시 (등록 폼):** 경고 패널 표시
- 유사 프로젝트 정보 (담당자명, 상태), 유사도
- medium은 참고 정보 패널만 (등록 가능)
- high는 경고 + 메시지 입력란 + 폼 제출 시 자동으로 승인 요청

**대기 상태 (프로젝트 목록):**
- "승인 대기중" 뱃지 표시 + 요청일
- [요청 취소] 버튼 -> 프로젝트 + 승인요청 삭제

---

## 관리자 승인 큐

### 승인 큐 화면 (`/projects/approvals/`)

OWNER 역할만 접근 가능. `ProjectApproval.objects.filter(project__organization=org, status="대기")`.

각 승인 요청 카드:
- 요청자, 고객사, 프로젝트명
- 충돌 프로젝트 정보 (담당자, 상태)
- 유사도 (높음/중간 + 점수)
- 요청자 메시지
- 요청일

### 관리자 판단 옵션

| 옵션 | 동작 |
|------|------|
| **승인** | ProjectApproval.status=승인, Project.status=new |
| **합류** | 관리자가 합류 대상 프로젝트를 드롭다운에서 선택 (디폴트: conflict_project). ProjectApproval.status=합류, 대상 프로젝트의 assigned_consultants에 요청자 추가, 요청 Project 삭제. |
| **메시지** | admin_response 저장 + Notification 생성. status 대기 유지. |
| **반려** | ProjectApproval.status=반려 + admin_response 저장 + Project 삭제 + Notification(반려 사유). |

**합류 시 삭제 안전성:** pending_approval 프로젝트는 하위 데이터(컨택/제출 등) 생성이 차단되므로 삭제가 안전. 방어적으로 하위 데이터 존재 시 `InvalidTransition` 예외.

### 취소

요청자가 취소 시: ProjectApproval 삭제 + Project 삭제. 재등록은 새 프로젝트로.

---

## 승인 상태 전이 서비스

`projects/services/approval.py`:

```python
APPROVAL_TRANSITIONS = {
    "대기": {"승인", "합류", "반려"},
    # "메시지"는 status 변경 없음 — 전이 맵에 포함하지 않음
}
# Terminal 상태(승인, 합류, 반려)에서 재처리 불가 -> InvalidTransition

def decide_approval(approval_id, decision, admin_user, org, merge_target=None, response_text=""):
    """
    transaction.atomic() + select_for_update()
    decision: "승인" | "합류" | "메시지" | "반려"
    merge_target: 합류 시 대상 프로젝트 (없으면 conflict_project 디폴트)
    """
```

---

## status_update 보호

`status_update` PATCH 뷰에서:
- `pending_approval` 상태 프로젝트의 직접 상태 변경 거부 (403)
- `pending_approval`로의 직접 전환도 거부

---

## 대시보드 통합

사이드바에 "승인 요청 (N건)" 뱃지 표시 (OWNER만).

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| 충돌 감지 | 같은 고객사 + 유사 제목 -> 경고 표시 |
| 충돌 없음 | 다른 고객사 -> 바로 등록 |
| medium 비차단 | 유사도 < 0.7 -> 경고만, 즉시 등록 가능 |
| high 차단 | 유사도 >= 0.7 -> pending_approval + ProjectApproval 생성 |
| 유사도 계산 | "품질기획팀장" vs "품질기획파트장" -> 높은 유사도 |
| 승인 -> 등록 | 관리자 승인 -> Project.status=new |
| 합류 처리 | 대상 프로젝트 선택 + 요청자 추가 + 요청 프로젝트 삭제 |
| 합류 대상 선택 | 관리자가 conflict_project 외 다른 프로젝트 선택 가능 |
| 반려 처리 | 요청자에게 사유 Notification + 프로젝트 삭제 |
| 취소 처리 | 요청자 취소 -> 프로젝트 + 승인요청 삭제 |
| 가시성 정책 | 충돌 시 담당자명/상태만 공개, JD 등 비공개 |
| pending_approval 보호 | 상태 직접 변경 불가, 하위 작업 생성 불가 |
| 역할 기반 접근 | OWNER만 승인 큐 접근 |
| 조직 격리 | 승인 큐, 충돌 검색 모두 organization 필터 |
| 대시보드 뱃지 | OWNER에게 미처리 건수 표시 |
| 상태 전이 | terminal 상태 재처리 불가 (InvalidTransition) |

---

## 산출물

- `projects/models.py` — ProjectApproval에 conflict_score, conflict_type 추가 + ConflictType choices
- `projects/views.py` — 충돌 감지 + 승인 큐 + 판단 + 취소 뷰
- `projects/forms.py` — ProjectForm에서 status 제거, ApprovalDecisionForm 추가
- `projects/urls.py` — 충돌/승인 관련 URL 추가
- `projects/services/collision.py` — 제목 유사도 판정 서비스
- `projects/services/approval.py` — 승인 처리 로직 (전이 맵 + InvalidTransition)
- `projects/admin.py` — ProjectApprovalAdmin에 conflict_score, conflict_type 표시
- `projects/templates/projects/partials/collision_warning.html` — 충돌 경고 패널
- `projects/templates/projects/approval_queue.html` — 관리자 승인 큐
- P03 프로젝트 등록 폼에 충돌 체크 HTMX + JS 추가
- 테스트 파일

## 프로젝트 컨텍스트 (확정 패턴)

1. **Organization 격리:** 모든 queryset에 `organization=org` 필터. `_get_org(request)` 헬퍼 사용.
2. **@login_required:** 모든 view에 적용.
3. **동적 extends:** `{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}`
4. **HTMX target:** `hx-target="#main-content"` (전체 네비), `hx-target="#tab-content"` (탭 전환).
5. **UI 텍스트:** 한국어 존대말.
6. **삭제 보호:** 관련 데이터 존재 시 삭제 차단.
7. **HTMX CRUD 패턴:** `{model}Changed` 이벤트 + `#{model}-form-area` + 204+HX-Trigger.
8. **DB 저장값:** 한국어 TextChoices 유지.
9. **상태 전이 서비스:** 허용 전이 맵 + `InvalidTransition` 예외.
10. **조직 격리 체이닝:** Project(organization=org) -> 하위 모델 체이닝.
11. **URL 라우팅:** projects/urls.py에 등록, main/urls.py에서 `projects/` include.
12. **admin.py 갱신:** 모델 필드 변경 시 반드시 admin 설정도 갱신.

<!-- forge:p11:설계담금질:complete:2026-04-08T23:20:00+09:00 -->
