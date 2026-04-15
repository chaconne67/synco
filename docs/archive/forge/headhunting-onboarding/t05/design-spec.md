# Task 5: 기존 view에 권한 데코레이터 적용

> **출처:** `docs/forge/headhunting-onboarding/phase1/design-spec-agreed.md`
> **선행 조건:** Task 1, 2 (구현 완료), Task 4 (dashboard 보호 + test fixture 업데이트)

---

## 배경

역할 기반 접근 제어(RBAC)를 실현하려면, 기존 모든 view에 적절한 권한 데코레이터를 적용해야 한다. owner만 수행할 수 있는 작업(고객사 생성/수정/삭제, 프로젝트 생성/삭제, 레퍼런스 관리, 승인 큐)과 모든 역할이 접근 가능한 작업(목록 조회, 상세 조회)을 구분한다.

---

## 요구사항

### 권한 매트릭스 (view 적용 대상)

| 기능 | owner | consultant | viewer |
|------|-------|-----------|--------|
| 고객사 CRUD | O | 읽기만 | 읽기만 |
| 프로젝트 생성 | O | X | X |
| 프로젝트 삭제 | O | X | X |
| 프로젝트 조회 | 전체 | 배정된 것만 | 배정된 것만 |
| 후보자 서칭/컨택/추천 | O | 배정된 프로젝트 내 | X |
| 레퍼런스 관리 | O | X | X |
| 프로젝트 승인 큐 | O | 본인 요청만 | X |

### 데코레이터 적용 규칙

```python
# 모든 역할이 접근 가능 (읽기)
@login_required
@membership_required
def client_list(request): ...

# owner만 접근 가능 (쓰기)
@login_required
@role_required("owner")
def client_create(request): ...
```

- `@role_required("owner")`는 내부적으로 `membership_required`를 포함하므로 별도로 적용하지 않아도 된다.
- `@membership_required`는 `@login_required` 뒤에 위치한다.

### clients/views.py 적용 대상

- `client_list`, `client_detail` -- `@membership_required` (모든 역할 읽기 가능)
- `client_create`, `client_update`, `client_delete` -- `@role_required("owner")`
- `contract_create`, `contract_update`, `contract_delete` -- `@role_required("owner")`
- 레퍼런스 관련 모든 view -- `@role_required("owner")`

### projects/views.py 적용 대상

- `project_create`, `project_delete` -- `@role_required("owner")`
- `approval_queue`, `approval_decide` -- `@role_required("owner")`
- 나머지 모든 view -- `@membership_required`

---

## 제약사항

- Task 2에서 구현된 `role_required`, `membership_required` 데코레이터를 사용한다.
- consultant가 owner-only view에 접근하면 403을 반환한다.
- 기존 테스트가 깨지지 않아야 한다 (Task 4에서 fixture 업데이트 완료 전제).
