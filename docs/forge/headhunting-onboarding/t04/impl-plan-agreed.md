# Task 4: dashboard 보호 + test fixture 업데이트 (확정 구현계획서)

**Goal:** 대시보드 view에 `membership_required` 데코레이터를 적용하고, 기존 테스트 fixture에 `Membership.status='active'`를 명시하여 테스트 의도를 명확히 한다.

**Design spec:** `docs/forge/headhunting-onboarding/t04/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료), Task 3 (구현 완료)

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `tests/conftest.py` | 수정 | Membership.status='active' 명시 (코드 명확성) |
| `projects/views.py` | 수정 | dashboard에 membership_required 데코레이터 적용 |
| `tests/test_p13_dashboard.py` | 수정 | /dashboard/ 접근 제어 통합 테스트 추가 |

---

- [ ] **Step 1: Update test fixtures to make Membership.status explicit**

In `tests/conftest.py`, update the `user` fixture to explicitly set `status="active"` for code clarity (the model default already provides this, but explicit is better than implicit for test intent):

```python
@pytest.fixture
def user(db, org):
    u = User.objects.create_user(username="consultant1", password="testpass123")
    Membership.objects.create(user=u, organization=org, status="active")
    return u
```

Update `other_user` fixture:

```python
@pytest.fixture
def other_user(db, org):
    u = User.objects.create_user(username="consultant2", password="testpass123")
    Membership.objects.create(user=u, organization=org, status="active")
    return u
```

Update `other_org_user` fixture:

```python
@pytest.fixture
def other_org_user(db):
    other_org = Organization.objects.create(name="Other Org")
    u = User.objects.create_user(username="outsider", password="testpass123")
    Membership.objects.create(user=u, organization=other_org, status="active")
    return u
```

- [ ] **Step 2: Add membership_required to dashboard view**

In `projects/views.py`, add import at top:

```python
from accounts.decorators import membership_required
```

Update the dashboard function:

```python
@login_required
@membership_required
def dashboard(request):
```

**Note:** `dashboard_actions` and `dashboard_team` are not decorated here -- they are in t05's scope ("나머지 모든 view -- `@membership_required`").

- [ ] **Step 3: Add integration tests for dashboard access control**

In `tests/test_p13_dashboard.py`, add tests to `TestDashboardViews` class for all four membership states:

```python
@pytest.mark.django_db
def test_dashboard_no_membership_redirects_to_invite(self):
    """No membership -> redirect to invite page."""
    user = User.objects.create_user(username="nomem_dash", password="test1234")
    c = TestClient()
    c.force_login(user)
    resp = c.get("/dashboard/")
    assert resp.status_code == 302
    assert "/accounts/invite/" in resp.url

@pytest.mark.django_db
def test_dashboard_pending_redirects_to_pending(self):
    """Pending membership -> redirect to pending page."""
    org = Organization.objects.create(name="Pending Org")
    user = User.objects.create_user(username="pend_dash", password="test1234")
    Membership.objects.create(user=user, organization=org, status="pending")
    c = TestClient()
    c.force_login(user)
    resp = c.get("/dashboard/")
    assert resp.status_code == 302
    assert "/accounts/pending/" in resp.url

@pytest.mark.django_db
def test_dashboard_rejected_redirects_to_rejected(self):
    """Rejected membership -> redirect to rejected page."""
    org = Organization.objects.create(name="Rejected Org")
    user = User.objects.create_user(username="rej_dash", password="test1234")
    Membership.objects.create(user=user, organization=org, status="rejected")
    c = TestClient()
    c.force_login(user)
    resp = c.get("/dashboard/")
    assert resp.status_code == 302
    assert "/accounts/rejected/" in resp.url
```

The existing `test_dashboard_explicit_url(self, auth_consultant)` already covers the active-user 200 path.

- [ ] **Step 4: Run existing tests to verify nothing breaks**

Run: `uv run pytest -v`
Expected: All existing tests PASS, plus 3 new tests PASS

- [ ] **Step 5: Commit**

```bash
git add projects/views.py tests/conftest.py tests/test_p13_dashboard.py
git commit -m "feat(projects): protect dashboard with membership_required, update test fixtures"
```

---

## Tempering Rulings Applied

| ID | Severity | Issue | Action |
|----|----------|-------|--------|
| I-R1-01 | MAJOR | Missing route-level regression tests | ACCEPTED — Added Step 3 with integration tests for all 4 states |
| I-R1-02 | MAJOR | --timeout=30 unavailable | ACCEPTED — Changed to `uv run pytest -v` |
| I-R1-03 | MINOR | Fixture normalization incomplete in dashboard tests | REBUTTED — Design spec scopes to conftest.py only |
| I-R1-04 | CRITICAL | No tests for core feature (=I-R1-01) | ACCEPTED — Merged with I-R1-01 |
| I-R1-05 | MAJOR | dashboard_actions/team unprotected | REBUTTED — t05 scope per design spec |
| I-R1-06 | MINOR | Fixture update redundant | PARTIAL — Kept for explicitness, reworded justification |

<!-- forge:t04:구현담금질:complete:2026-04-12T07:15:00+09:00 -->
