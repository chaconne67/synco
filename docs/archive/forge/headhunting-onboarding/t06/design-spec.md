# Task 6: 프로젝트 목록 consultant 필터링

> **출처:** `docs/forge/headhunting-onboarding/phase1/design-spec-agreed.md`
> **선행 조건:** Task 1, 2 (구현 완료), Task 5 (기존 view에 권한 데코레이터 적용)

---

## 배경

현재 프로젝트 목록은 조직 내 모든 프로젝트를 표시한다. RBAC 도입에 따라 consultant는 자신에게 배정된 프로젝트만 볼 수 있어야 한다. owner는 조직 전체 프로젝트를 볼 수 있다.

---

## 요구사항

### 권한 매트릭스

| 역할 | 프로젝트 조회 범위 |
|------|-------------------|
| owner | 조직 전체 프로젝트 |
| consultant | 배정된 프로젝트만 (`assigned_consultants` M2M 필드 기준) |
| viewer | 배정된 프로젝트만 |

### 구현 방식

```python
membership = request.user.membership
if membership.role == "owner":
    qs = Project.objects.filter(organization=org)
else:
    qs = Project.objects.filter(
        organization=org, assigned_consultants=request.user
    )
```

- 기존 필터/정렬 로직은 변경하지 않고, 기본 queryset만 역할에 따라 분기한다.

---

## 제약사항

- `assigned_consultants` M2M 필드는 기존 Project 모델에 이미 존재한다.
- Task 5에서 `@membership_required`가 project_list에 적용된 상태를 전제한다.
- 기존 필터/정렬/페이지네이션 로직은 그대로 유지한다.
