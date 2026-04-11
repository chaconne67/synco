# Task 4: dashboard 보호 + test fixture 업데이트

**Goal:** 대시보드 view에 `membership_required` 데코레이터를 적용하고, 기존 테스트 fixture에 `Membership.status='active'`를 명시하여 기존 테스트가 깨지지 않도록 한다.

**Design spec:** `docs/forge/headhunting-onboarding/t04/design-spec.md`

**depends_on:** Task 1 (구현 완료), Task 2 (구현 완료), Task 3

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/views.py` | 수정 | dashboard에 membership_required 데코레이터 적용 |
| `tests/conftest.py` | 수정 | Membership.status='active' 추가 |

---

- [ ] **Step 1: Update test fixtures to include Membership.status**

In `tests/conftest.py`, update the `user` fixture:

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

- [ ] **Step 3: Run existing tests to verify nothing breaks**

Run: `uv run pytest -v --timeout=30`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add projects/views.py tests/conftest.py
git commit -m "feat(projects): protect dashboard with membership_required, update test fixtures"
```
