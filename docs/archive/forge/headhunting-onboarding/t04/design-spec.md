# Task 4: dashboard 보호 + test fixture 업데이트

> **출처:** `docs/forge/headhunting-onboarding/phase1/design-spec-agreed.md`
> **선행 조건:** Task 1, 2 (구현 완료), Task 3 (카카오 로그인 플로우 수정 + 온보딩 화면)

---

## 배경

온보딩 플로우(Task 3)가 구현되면, 대시보드를 포함한 기존 view들도 Membership 상태를 검증해야 한다. Membership이 없거나 pending/rejected 상태인 사용자가 대시보드에 직접 접근하는 것을 차단해야 한다. 또한 기존 테스트 fixture들이 Membership.status 필드를 명시하지 않으므로, 테스트가 올바르게 동작하도록 fixture를 업데이트해야 한다.

---

## 요구사항

### 접근 제어 구현 방식

```python
@login_required
@membership_required
def dashboard(request):
    ...
```

- `membership_required` 데코레이터(Task 2에서 구현 완료)를 대시보드 view에 적용
- Membership 없음 -> `/accounts/invite/` 리다이렉트
- Membership.status=pending -> `/accounts/pending/` 리다이렉트
- Membership.status=rejected -> `/accounts/rejected/` 리다이렉트
- Membership.status=active -> 통과

### 테스트 fixture 업데이트

기존 `tests/conftest.py`의 user, other_user, other_org_user fixture에 `status="active"`를 명시적으로 추가한다.

---

## 제약사항

- Task 2에서 구현된 `membership_required` 데코레이터를 그대로 사용한다.
- 기존 테스트가 깨지지 않도록 fixture에 `status="active"`를 추가한다.
- 대시보드 view의 기존 로직은 변경하지 않고, 데코레이터만 추가한다.
