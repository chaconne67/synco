# P11: Project Collision & Approval

> **Phase:** 11
> **선행조건:** P03 (프로젝트 CRUD — 등록 폼), P02 (고객사 관리 — Client 모델)
> **산출물:** 유사 프로젝트 충돌 감지 + 승인 플로우 + 관리자 대시보드 승인 큐

---

## 목표

프로젝트 등록 시 같은 고객사의 유사 프로젝트를 자동 감지하고, 충돌 시 관리자 승인을
거쳐야 등록되도록 한다. 가시성 정책, 승인 플로우, 관리자 대시보드 승인 요청 큐를 구현한다.

---

## URL 설계

| URL | Method | View | 설명 |
|-----|--------|------|------|
| `/projects/new/check-collision/` | POST | `project_check_collision` | 충돌 감지 (HTMX partial) |
| `/projects/<pk>/approval/request/` | POST | `approval_request` | 승인 요청 제출 |
| `/projects/<pk>/approval/cancel/` | POST | `approval_cancel` | 승인 요청 취소 |
| `/admin/approvals/` | GET | `approval_queue` | 관리자 승인 요청 큐 |
| `/admin/approvals/<appr_pk>/decide/` | POST | `approval_decide` | 관리자 판단 (승인/합류/메시지/반려) |

---

## 모델 추가

### ProjectApproval (projects 앱)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | UUID | PK |
| `project` | FK → Project | 승인 대기 상태로 생성된 프로젝트 |
| `requested_by` | FK → User | 요청자 (프리랜서 컨설턴트) |
| `conflict_project` | FK → Project null | 충돌 감지된 기존 프로젝트 |
| `conflict_score` | FloatField | 유사도 점수 (0.0 ~ 1.0) |
| `conflict_type` | CharField choices | 충돌 유형 |
| `status` | CharField choices | 승인 상태 |
| `message` | TextField blank | 요청자 설명 메시지 |
| `admin_response` | TextField blank | 관리자 응답 |
| `decided_by` | FK → User null | 판단한 관리자 |
| `decided_at` | DateTimeField null | 판단 일시 |
| `created_at` / `updated_at` | DateTimeField | 타임스탬프 |

```python
class ConflictType(models.TextChoices):
    HIGH = "high", "높은 중복 가능성"     # 같은 고객사 + 포지션명 유사
    MEDIUM = "medium", "참고 정보"       # 같은 고객사 + 포지션 다름

class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "대기중"
    APPROVED = "approved", "승인"
    MERGED = "merged", "합류"          # 기존 프로젝트에 합류
    REJECTED = "rejected", "반려"
```

### Project 모델 확장

- `status` choices에 `PENDING_APPROVAL = "pending_approval", "승인 대기"` 추가
- 충돌 감지 시 이 상태로 생성, 승인 후 `new`(신규)로 전환

---

## 충돌 감지 로직

### 감지 시점

프로젝트 등록 폼에서 고객사 선택 시 HTMX로 실시간 충돌 체크:

```
고객사 드롭다운 변경
  → hx-post="/projects/new/check-collision/"
  → body: {client_id, position_title}
  → 서버: 충돌 감지 결과 HTML partial 반환
```

### 매칭 기준

| 조건 | 판정 | conflict_type |
|------|------|---------------|
| 같은 고객사 + 포지션명 유사도 ≥ 0.7 | 높은 중복 가능성 | `high` |
| 같은 고객사 + 포지션명 유사도 < 0.7 | 참고 정보 | `medium` |
| 다른 고객사 | 감지 없음 | — |

**포지션 유사도 판정:** `projects/services/collision.py`
1. 핵심 키워드 추출 (직급/부서/직무 분리)
2. 키워드 매칭 점수 계산 (예: "품질기획팀장" vs "품질기획파트장" → 핵심 키워드 일치 → 0.9)
3. 진행 중(closed 아닌) 프로젝트만 대상

### 가시성 정책

평소에는 자기 프로젝트만 보임. 충돌 감지 시에만 제한적 정보 공개:
- "유사 프로젝트 존재" (담당자명, 프로젝트 상태)
- JD나 후보자 목록 등 상세 정보는 비공개

---

## 프리랜서 화면

**충돌 감지 시:** 등록 폼에 경고 패널 표시 — 충돌 프로젝트 정보(담당자, 상태), 유사도, 메시지 입력란, [승인 요청 보내기] 버튼.

**대기 상태:** 프로젝트 목록에 "승인 대기중" 표시 + 요청일 + [요청 취소] 버튼.

---

## 관리자 대시보드: 승인 요청 큐

```
+-- 승인 요청 (2건) -------------------------------------------+
|                                                              |
|  +----------------------------------------------------------+|
|  |  전병권 -> Rayence . 품질기획팀장                          ||
|  |  충돌: 김소연의 "Rayence . 품질기획파트장" (서칭중)         ||
|  |  유사도: 높음 (0.92)                                      ||
|  |  메시지: "인사팀 이부장으로부터 직접 의뢰..."                ||
|  |  요청일: 04/06                                            ||
|  |                                                           ||
|  |  [승인]  [합류]  [메시지]  [반려]                           ||
|  +----------------------------------------------------------+|
|                                                              |
|  +----------------------------------------------------------+|
|  |  박준혁 -> LG전자 . 경영기획                               ||
|  |  충돌: 전병권의 "LG전자 . 기획팀" (서칭중)                  ||
|  |  유사도: 중간 (0.55)                                      ||
|  |  [승인]  [합류]  [메시지]  [반려]                           ||
|  +----------------------------------------------------------+|
+--------------------------------------------------------------+
```

### 관리자 판단 옵션

| 옵션 | 동작 |
|------|------|
| **승인** | ProjectApproval.status = approved, Project.status = new |
| **합류** | ProjectApproval.status = merged, 요청 Project 삭제, conflict_project에 요청자를 assigned_consultants에 추가 |
| **메시지** | 관리자 -> 요청자 메시지 전달 (admin_response 저장), status 유지 |
| **반려** | ProjectApproval.status = rejected, Project.status 변경 없음 (삭제 또는 보관) |

---

## 승인 플로우 통합

### 프로젝트 등록 수정 (P03 확장)

`project_create` 뷰에 충돌 감지 분기 추가:
1. 충돌 없음 -> 기존대로 `status = new`로 즉시 등록
2. 충돌 감지 -> `status = pending_approval`로 생성 + ProjectApproval 생성

### 대시보드 통합 (후속)

관리자 대시보드에 "승인 요청 (N건)" 섹션 표시. 뱃지로 미처리 건수 사이드바에 노출.

---

## 테스트 기준

| 항목 | 검증 방법 |
|------|----------|
| 충돌 감지 | 같은 고객사+유사 포지션 -> 경고 표시 |
| 충돌 없음 | 다른 고객사 -> 바로 등록 |
| 유사도 계산 | "품질기획팀장" vs "품질기획파트장" -> 높은 유사도 |
| 승인 요청 | pending_approval 상태 + ProjectApproval 생성 |
| 승인 -> 등록 | 관리자 승인 -> Project status = new |
| 합류 처리 | 요청 Project 정리 + 기존 Project에 컨설턴트 추가 |
| 반려 처리 | 요청자에게 사유 전달 |
| 가시성 정책 | 충돌 시에만 제한적 정보 공개, 평소 자기 것만 |
| 대시보드 큐 | 관리자에게 미처리 건 표시 |

---

## 산출물

- `projects/models.py` — ProjectApproval 모델 + Project.status choices 확장
- `projects/views.py` — 충돌 감지 + 승인 요청/취소 + 관리자 판단 뷰
- `projects/forms.py` — ApprovalRequestForm, ApprovalDecisionForm
- `projects/urls.py` — 충돌/승인 관련 URL 추가
- `projects/services/collision.py` — 포지션 유사도 판정 서비스
- `projects/services/approval.py` — 승인 처리 로직 (승인/합류/반려)
- `projects/templates/projects/partials/collision_warning.html` — 충돌 경고
- `projects/templates/projects/approval_queue.html` — 관리자 승인 큐
- P03 프로젝트 등록 폼에 충돌 체크 HTMX 추가
- 테스트 파일

## 프로젝트 컨텍스트 (핸드오프에서 확립된 패턴)

1. **Organization 격리:** 모든 queryset에 `organization=org` 필터. `_get_org(request)` 헬퍼 사용
2. **@login_required:** 모든 view에 적용
3. **동적 extends:** `{% extends request.htmx|yesno:"common/base_partial.html,common/base.html" %}`
4. **HTMX target:** `hx-target="#main-content"` (전체 네비), `hx-target="#tab-content"` (탭 전환)
5. **UI 텍스트:** 한국어 존대말
6. **삭제 보호:** 관련 데이터 존재 시 삭제 차단
7. **HTMX CRUD 패턴:** `{model}Changed` 이벤트 + `#{model}-form-area` + 204+HX-Trigger
8. **DB 저장값:** 한국어 TextChoices 유지 (대면/합격/협상중 등)
9. **상태 전이 서비스:** 허용 전이 맵 + `InvalidTransition` 예외 (P07 submission, P08 draft, P09 lifecycle)
10. **조직 격리 체이닝:** Project(organization=org) -> Submission(project=project) -> Interview/Offer/Draft

**참고:** P11의 ProjectApproval 모델은 이미 models.py에 스켈레톤이 존재할 수 있음(P09 핸드오프 참조). 실제 코드를 반드시 확인하라.
