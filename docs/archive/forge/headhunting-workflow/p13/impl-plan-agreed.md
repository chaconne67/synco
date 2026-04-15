# P13: Dashboard Implementation Plan (확정)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a dashboard as the default landing page after login, showing today's actions with urgency scoring, weekly schedule, pipeline summary, recent activities, and OWNER team KPI.

**Architecture:** Add `next_contact_date` field to Contact, create `urgency.py` (with `collect_all_actions` + `compute_project_urgency`) and `dashboard.py` services. Add dashboard views in projects app, route from `/` and `/dashboard/` in `main/urls.py`. Update sidebar/bottom nav with dashboard first. OWNER sees approval queue summary (link to `/projects/approvals/`) and team stats. All queries are org-isolated.

**Tech Stack:** Django 5.2, PostgreSQL, HTMX, Tailwind CSS, pytest

**Source documents:**
- 확정 설계서: `docs/forge/headhunting-workflow/p13/design-spec-agreed.md`
- 구현 쟁점 판정: `docs/forge/headhunting-workflow/p13/debate/impl-rulings.md`

---

## Critical Fixes from Implementation Tempering

### Fix 1: collect_all_actions() for today/weekly (I-R1-01)
**Why:** `compute_project_urgency()` returns only 1 action per project. Weekly schedule items are invisible when a red action exists for the same project.
**Change:** Add `collect_all_actions(project)` that returns all actions. `get_today_actions()` and `get_weekly_schedule()` use this instead of `compute_project_urgency()`.

### Fix 2: Team KPI consultant-based counting (I-R1-02)
**Why:** M2M assigned_consultants causes double-counting. Viewer roles inflated the table.
**Change:** Filter to owner/consultant roles only. Use `Contact.consultant` and `Submission.consultant` for per-person counts.

### Fix 3: Single routing strategy in main/urls.py (I-R1-03, I-R1-04)
**Why:** Plan had contradictory routing instructions between Task 4 and Task 6.
**Change:** All dashboard URLs in `main/urls.py`. `path("", dashboard)` before accounts include. No changes to `projects/urls.py`.

### Fix 4: Remove stale Task 5 (I-R1-05)
**Why:** `django.contrib.humanize` already in settings.py:51.
**Change:** Removed.

### Fix 5: Fix activities docstring (I-R1-06)
**Why:** Docstring said "submission drafts" but implementation only queries Submission.
**Change:** Docstring corrected to match implementation.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `projects/models.py` | Modify | Add `next_contact_date` field to Contact |
| `projects/migrations/XXXX_p13_contact_next_contact_date.py` | Create | Migration for new field |
| `projects/services/urgency.py` | Create | Urgency scoring: `collect_all_actions` + `compute_project_urgency` |
| `projects/services/dashboard.py` | Create | Dashboard data aggregation (actions, schedule, pipeline, activity, team) |
| `projects/views.py` | Modify | Add dashboard, dashboard_actions, dashboard_team views |
| `main/urls.py` | Modify | Root `/` → dashboard, add `/dashboard/`, `/dashboard/actions/`, `/dashboard/team/` |
| `main/settings.py` | Modify | Add `LOGIN_REDIRECT_URL = "/"` |
| `accounts/views.py` | Modify | Change `home()` redirect from `candidate_list` to `/` |
| `projects/templates/projects/dashboard.html` | Create | Full dashboard layout |
| `projects/templates/projects/partials/dash_full.html` | Create | Dashboard content (HTMX partial target) |
| `projects/templates/projects/partials/dash_actions.html` | Create | Today's actions section |
| `projects/templates/projects/partials/dash_schedule.html` | Create | Weekly schedule section |
| `projects/templates/projects/partials/dash_pipeline.html` | Create | Pipeline mini chart |
| `projects/templates/projects/partials/dash_activity.html` | Create | Recent activity section |
| `projects/templates/projects/partials/dash_admin.html` | Create | OWNER section (approval queue + team KPI) |
| `templates/common/nav_sidebar.html` | Modify | Add dashboard as first menu item + update JS |
| `templates/common/nav_bottom.html` | Modify | Add dashboard as first mobile nav item + update JS |
| `tests/test_p13_dashboard.py` | Create | Dashboard test suite |

---

### Task 1: Model — Add next_contact_date to Contact

**Files:**
- Modify: `projects/models.py:77-142`
- Create: `projects/migrations/XXXX_p13_contact_next_contact_date.py`
- Test: `tests/test_p13_dashboard.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_p13_dashboard.py
"""P13: Dashboard tests."""

import pytest
from datetime import date, timedelta
from django.test import Client as TestClient
from django.utils import timezone

from accounts.models import Membership, Organization, User
from clients.models import Client
from projects.models import Contact, Project


# --- Fixtures ---

@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def user_owner(db, org):
    user = User.objects.create_user(username="owner13", password="test1234")
    Membership.objects.create(user=user, organization=org, role="owner")
    return user


@pytest.fixture
def user_consultant(db, org):
    user = User.objects.create_user(username="consultant13", password="test1234")
    Membership.objects.create(user=user, organization=org, role="consultant")
    return user


@pytest.fixture
def client_obj(org):
    return Client.objects.create(name="Acme Corp", industry="IT", organization=org)


@pytest.fixture
def project(org, client_obj, user_consultant):
    p = Project.objects.create(
        client=client_obj,
        organization=org,
        title="품질기획팀장",
        status="searching",
        created_by=user_consultant,
    )
    p.assigned_consultants.add(user_consultant)
    return p


@pytest.fixture
def auth_owner(user_owner):
    c = TestClient()
    c.login(username="owner13", password="test1234")
    return c


@pytest.fixture
def auth_consultant(user_consultant):
    c = TestClient()
    c.login(username="consultant13", password="test1234")
    return c


# --- Task 1: Model tests ---

class TestContactNextContactDate:
    @pytest.mark.django_db
    def test_next_contact_date_field_exists(self, project, user_consultant):
        from candidates.models import Candidate

        candidate = Candidate.objects.create(
            name="홍길동",
            owned_by=project.organization,
        )
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_consultant,
            result="응답",
            contacted_at=timezone.now(),
            next_contact_date=date.today() + timedelta(days=3),
        )
        contact.refresh_from_db()
        assert contact.next_contact_date == date.today() + timedelta(days=3)

    @pytest.mark.django_db
    def test_next_contact_date_nullable(self, project, user_consultant):
        from candidates.models import Candidate

        candidate = Candidate.objects.create(
            name="이순신",
            owned_by=project.organization,
        )
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_consultant,
            result="응답",
            contacted_at=timezone.now(),
        )
        contact.refresh_from_db()
        assert contact.next_contact_date is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_p13_dashboard.py::TestContactNextContactDate -v`
Expected: FAIL

- [ ] **Step 3: Add next_contact_date field to Contact**

In `projects/models.py`, inside the `Contact` class, after `locked_until` (line 119), add:

```python
    next_contact_date = models.DateField(null=True, blank=True)  # 재컨택 예정일
```

- [ ] **Step 4: Generate and apply migration**

```bash
uv run python manage.py makemigrations projects --name p13_contact_next_contact_date
uv run python manage.py migrate
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_p13_dashboard.py::TestContactNextContactDate -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add projects/models.py projects/migrations/*p13_contact_next_contact_date* tests/test_p13_dashboard.py
git commit -m "feat(p13): add next_contact_date field to Contact model"
```

---

### Task 2: Service — Urgency scoring with collect_all_actions

**Files:**
- Create: `projects/services/urgency.py`
- Test: `tests/test_p13_dashboard.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_p13_dashboard.py`:

```python
# --- Task 2: Urgency tests ---

class TestUrgencyScoring:
    @pytest.mark.django_db
    def test_recontact_today_is_priority_1(self, project, user_consultant):
        from candidates.models import Candidate
        from projects.services.urgency import compute_project_urgency

        candidate = Candidate.objects.create(name="홍길동", owned_by=project.organization)
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_consultant,
            result="응답",
            contacted_at=timezone.now() - timedelta(days=7),
            next_contact_date=date.today(),
        )
        action = compute_project_urgency(project)
        assert action is not None
        assert action["priority"] == 1
        assert action["level"] == "red"

    @pytest.mark.django_db
    def test_interview_tomorrow_is_priority_2(self, project, user_consultant):
        from candidates.models import Candidate
        from projects.models import Interview, Submission
        from projects.services.urgency import compute_project_urgency

        candidate = Candidate.objects.create(name="이순신", owned_by=project.organization)
        sub = Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_consultant,
            status="통과",
        )
        Interview.objects.create(
            submission=sub,
            round=1,
            scheduled_at=timezone.now() + timedelta(hours=30),
            type="대면",
        )
        action = compute_project_urgency(project)
        assert action is not None
        assert action["priority"] == 2
        assert action["level"] == "red"

    @pytest.mark.django_db
    def test_collect_all_returns_multiple_actions(self, project, user_consultant):
        """Fix I-R1-01: collect_all_actions returns all priorities, not just max."""
        from candidates.models import Candidate
        from projects.models import Interview, Submission
        from projects.services.urgency import collect_all_actions

        candidate = Candidate.objects.create(name="홍길동", owned_by=project.organization)
        # Red action: recontact today
        Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_consultant,
            result="응답",
            contacted_at=timezone.now() - timedelta(days=7),
            next_contact_date=date.today(),
        )
        # Yellow action: interview this week
        sub = Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_consultant,
            status="통과",
        )
        Interview.objects.create(
            submission=sub,
            round=1,
            scheduled_at=timezone.now() + timedelta(days=4),
            type="대면",
        )

        actions = collect_all_actions(project)
        levels = {a["level"] for a in actions}
        assert "red" in levels
        assert "yellow" in levels

    @pytest.mark.django_db
    def test_new_project_within_3days_is_priority_8(self, org, client_obj, user_consultant):
        from projects.services.urgency import compute_project_urgency

        new_proj = Project.objects.create(
            client=client_obj,
            organization=org,
            title="신규 프로젝트",
            status="new",
            created_by=user_consultant,
        )
        action = compute_project_urgency(new_proj)
        assert action is not None
        assert action["priority"] == 8
        assert action["level"] == "green"

    @pytest.mark.django_db
    def test_closed_project_returns_none(self, org, client_obj, user_consultant):
        from projects.services.urgency import compute_project_urgency

        closed = Project.objects.create(
            client=client_obj,
            organization=org,
            title="종료 프로젝트",
            status="closed_success",
            created_by=user_consultant,
        )
        action = compute_project_urgency(closed)
        assert action is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_p13_dashboard.py::TestUrgencyScoring -v`
Expected: FAIL

- [ ] **Step 3: Implement urgency service**

Create `projects/services/urgency.py`:

```python
"""긴급도 자동 산정 로직."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from projects.models import (
    Contact,
    Interview,
    Offer,
    Project,
    ProjectStatus,
    Submission,
)

# Closed statuses — no urgency
CLOSED_STATUSES = {
    ProjectStatus.CLOSED_SUCCESS,
    ProjectStatus.CLOSED_FAIL,
    ProjectStatus.CLOSED_CANCEL,
    ProjectStatus.ON_HOLD,
    ProjectStatus.PENDING_APPROVAL,
}


def collect_all_actions(project: Project) -> list[dict]:
    """
    프로젝트의 모든 긴급도 액션을 수집.

    Returns list of dicts with keys: priority, level, label, detail, project, related_object.
    Returns empty list if project is closed/on_hold/pending.
    """
    if project.status in CLOSED_STATUSES:
        return []

    now = timezone.now()
    today = now.date()
    tomorrow = today + timedelta(days=1)
    week_end = today + timedelta(days=(6 - today.weekday()))

    actions: list[dict] = []

    # --- Priority 1: 재컨택 예정일이 오늘이거나 과거 ---
    overdue_contacts = Contact.objects.filter(
        project=project,
        next_contact_date__lte=today,
    ).exclude(
        result=Contact.Result.RESERVED,
    ).select_related("candidate")

    for contact in overdue_contacts:
        days_overdue = (today - contact.next_contact_date).days
        detail = "오늘" if days_overdue == 0 else f"D+{days_overdue} 지연"
        actions.append({
            "priority": 1,
            "level": "red",
            "label": "재컨택",
            "detail": detail,
            "project": project,
            "related_object": contact,
        })

    # --- Priority 2: 면접 일정이 오늘~내일 ---
    imminent_interviews = Interview.objects.filter(
        submission__project=project,
        scheduled_at__date__gte=today,
        scheduled_at__date__lte=tomorrow,
        result="대기",
    ).select_related("submission__candidate")

    for interview in imminent_interviews:
        actions.append({
            "priority": 2,
            "level": "red",
            "label": "면접 임박",
            "detail": f"{interview.round}차 면접 {interview.scheduled_at.strftime('%m/%d')}",
            "project": project,
            "related_object": interview,
        })

    # --- Priority 3: 서류 제출 후 검토 대기 2일 이상 ---
    pending_submissions = Submission.objects.filter(
        project=project,
        status="제출",
        submitted_at__lte=now - timedelta(days=2),
    ).select_related("candidate")

    for sub in pending_submissions:
        days_waiting = (now - sub.submitted_at).days
        actions.append({
            "priority": 3,
            "level": "red",
            "label": "서류 검토 필요",
            "detail": f"대기: {days_waiting}일",
            "project": project,
            "related_object": sub,
        })

    # --- Priority 4: 잠금 만료 1일 이내 ---
    expiring_locks = Contact.objects.filter(
        project=project,
        result=Contact.Result.RESERVED,
        locked_until__gt=now,
        locked_until__lte=now + timedelta(days=1),
    ).select_related("candidate")

    for contact in expiring_locks:
        actions.append({
            "priority": 4,
            "level": "red",
            "label": "컨택 잠금 만료 임박",
            "detail": f"만료: {contact.locked_until.strftime('%m/%d %H:%M')}",
            "project": project,
            "related_object": contact,
        })

    # --- Priority 5: 면접 일정 이번 주 ---
    week_interviews = Interview.objects.filter(
        submission__project=project,
        scheduled_at__date__gt=tomorrow,
        scheduled_at__date__lte=week_end,
        result="대기",
    ).select_related("submission__candidate")

    for interview in week_interviews:
        actions.append({
            "priority": 5,
            "level": "yellow",
            "label": "면접 예정",
            "detail": f"{interview.round}차 {interview.scheduled_at.strftime('%m/%d (%a)')}",
            "project": project,
            "related_object": interview,
        })

    # --- Priority 6: 재컨택 예정 이번 주 ---
    week_recontacts = Contact.objects.filter(
        project=project,
        next_contact_date__gt=today,
        next_contact_date__lte=week_end,
    ).exclude(
        result=Contact.Result.RESERVED,
    ).select_related("candidate")

    for contact in week_recontacts:
        actions.append({
            "priority": 6,
            "level": "yellow",
            "label": "재컨택 예정",
            "detail": f"{contact.next_contact_date.strftime('%m/%d')} 예정",
            "project": project,
            "related_object": contact,
        })

    # --- Priority 7: 오퍼 회신 대기 7일 이상 ---
    stale_offers = Offer.objects.filter(
        submission__project=project,
        status="협상중",
        created_at__lte=now - timedelta(days=7),
    )

    for offer in stale_offers:
        days_waiting = (now - offer.created_at).days
        actions.append({
            "priority": 7,
            "level": "yellow",
            "label": "오퍼 회신 대기",
            "detail": f"D+{days_waiting}",
            "project": project,
            "related_object": offer,
        })

    # --- Priority 8: 신규 프로젝트 (D+3 이내) ---
    if project.status == ProjectStatus.NEW and project.days_elapsed <= 3:
        actions.append({
            "priority": 8,
            "level": "green",
            "label": "서칭 시작 필요",
            "detail": f"신규: D+{project.days_elapsed}",
            "project": project,
            "related_object": None,
        })

    # --- Priority 9: 기타 진행 중 ---
    if not actions:
        actions.append({
            "priority": 9,
            "level": "green",
            "label": "정상 진행",
            "detail": project.get_status_display(),
            "project": project,
            "related_object": None,
        })

    return actions


def compute_project_urgency(project: Project) -> dict | None:
    """
    프로젝트의 가장 높은 긴급도 액션 1개를 결정.

    Returns dict or None if project is closed/on_hold/pending.
    """
    actions = collect_all_actions(project)
    if not actions:
        return None
    return min(actions, key=lambda a: a["priority"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_p13_dashboard.py::TestUrgencyScoring -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/urgency.py tests/test_p13_dashboard.py
git commit -m "feat(p13): implement urgency scoring with collect_all_actions"
```

---

### Task 3: Service — Dashboard data aggregation

**Files:**
- Create: `projects/services/dashboard.py`
- Test: `tests/test_p13_dashboard.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_p13_dashboard.py`:

```python
# --- Task 3: Dashboard service tests ---

class TestDashboardService:
    @pytest.mark.django_db
    def test_get_today_actions_returns_sorted_red_items(self, user_consultant, org, project):
        from projects.services.dashboard import get_today_actions

        actions = get_today_actions(user_consultant, org)
        assert isinstance(actions, list)
        for action in actions:
            assert action["level"] == "red"
        priorities = [a["priority"] for a in actions]
        assert priorities == sorted(priorities)

    @pytest.mark.django_db
    def test_get_weekly_schedule_returns_yellow_items(self, user_consultant, org, project):
        from projects.services.dashboard import get_weekly_schedule

        schedule = get_weekly_schedule(user_consultant, org)
        assert isinstance(schedule, list)
        for action in schedule:
            assert action["level"] == "yellow"

    @pytest.mark.django_db
    def test_get_pipeline_summary_counts(self, user_consultant, org, project):
        from projects.services.dashboard import get_pipeline_summary

        summary = get_pipeline_summary(user_consultant, org)
        assert "status_counts" in summary
        assert "total_active" in summary
        assert "month_closed" in summary
        assert summary["total_active"] >= 1

    @pytest.mark.django_db
    def test_get_pipeline_summary_org_isolation(self, user_consultant, org, project):
        from projects.services.dashboard import get_pipeline_summary

        other_org = Organization.objects.create(name="Other Org")
        other_client = Client.objects.create(name="Other", industry="IT", organization=other_org)
        Project.objects.create(
            client=other_client,
            organization=other_org,
            title="외부 프로젝트",
            status="searching",
            created_by=user_consultant,
        )
        summary = get_pipeline_summary(user_consultant, org)
        assert summary["total_active"] == 1

    @pytest.mark.django_db
    def test_get_recent_activities(self, user_consultant, org, project):
        from projects.services.dashboard import get_recent_activities

        activities = get_recent_activities(user_consultant, org, limit=10)
        assert isinstance(activities, list)

    @pytest.mark.django_db
    def test_get_team_summary_excludes_viewer(self, user_owner, org, project):
        """Fix I-R1-02: viewer role should not appear in team summary."""
        from projects.services.dashboard import get_team_summary

        viewer = User.objects.create_user(username="viewer13", password="test1234")
        Membership.objects.create(user=viewer, organization=org, role="viewer")

        summary = get_team_summary(user_owner, org)
        usernames = [c["user"].username for c in summary["consultants"]]
        assert "viewer13" not in usernames

    @pytest.mark.django_db
    def test_get_pending_approvals_empty(self, org):
        from projects.services.dashboard import get_pending_approvals

        qs = get_pending_approvals(org)
        assert qs.count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_p13_dashboard.py::TestDashboardService -v`
Expected: FAIL

- [ ] **Step 3: Implement dashboard service**

Create `projects/services/dashboard.py`:

```python
"""대시보드 데이터 집계 서비스."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from accounts.models import Membership, Organization, User
from projects.models import (
    Contact,
    Interview,
    Offer,
    Project,
    ProjectApproval,
    ProjectStatus,
    Submission,
)
from projects.services.urgency import collect_all_actions

INACTIVE_STATUSES = {
    ProjectStatus.CLOSED_SUCCESS,
    ProjectStatus.CLOSED_FAIL,
    ProjectStatus.CLOSED_CANCEL,
    ProjectStatus.ON_HOLD,
    ProjectStatus.PENDING_APPROVAL,
}

PIPELINE_STATUSES = [
    ProjectStatus.NEW,
    ProjectStatus.SEARCHING,
    ProjectStatus.RECOMMENDING,
    ProjectStatus.INTERVIEWING,
    ProjectStatus.NEGOTIATING,
]


def _my_active_projects(user: User, org: Organization) -> QuerySet:
    """현재 사용자의 활성 프로젝트."""
    return (
        Project.objects.filter(organization=org)
        .filter(Q(assigned_consultants=user) | Q(created_by=user))
        .exclude(status__in=INACTIVE_STATUSES)
        .distinct()
    )


def get_today_actions(user: User, org: Organization) -> list[dict]:
    """긴급도 자동 산정 후 오늘의 액션 목록 반환 (빨강 only)."""
    projects = _my_active_projects(user, org)

    actions = []
    for project in projects:
        all_actions = collect_all_actions(project)
        actions.extend(a for a in all_actions if a["level"] == "red")

    actions.sort(key=lambda a: a["priority"])
    return actions


def get_weekly_schedule(user: User, org: Organization) -> list[dict]:
    """이번 주 일정 (노랑 level actions)."""
    projects = _my_active_projects(user, org)

    actions = []
    for project in projects:
        all_actions = collect_all_actions(project)
        actions.extend(a for a in all_actions if a["level"] == "yellow")

    actions.sort(key=lambda a: a["priority"])
    return actions


def get_pipeline_summary(user: User, org: Organization) -> dict:
    """내 프로젝트 상태별 카운트 + 이번 달 클로즈 건수."""
    my_projects = (
        Project.objects.filter(organization=org)
        .filter(Q(assigned_consultants=user) | Q(created_by=user))
        .distinct()
    )

    status_counts = {}
    for status_value in PIPELINE_STATUSES:
        status_counts[status_value] = my_projects.filter(status=status_value).count()

    total_active = sum(status_counts.values())

    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_closed = my_projects.filter(
        status=ProjectStatus.CLOSED_SUCCESS,
        updated_at__gte=month_start,
    ).count()

    return {
        "status_counts": status_counts,
        "total_active": total_active,
        "month_closed": month_closed,
    }


def get_recent_activities(
    user: User, org: Organization, limit: int = 10
) -> list[dict]:
    """최근 활동 로그 반환.

    Aggregates recent contacts, project creations, and submissions
    from user's projects, sorted by time descending.
    """
    my_projects = (
        Project.objects.filter(organization=org)
        .filter(Q(assigned_consultants=user) | Q(created_by=user))
        .distinct()
    )
    project_ids = list(my_projects.values_list("pk", flat=True))
    activities: list[dict] = []

    recent_contacts = (
        Contact.objects.filter(project_id__in=project_ids)
        .exclude(result=Contact.Result.RESERVED)
        .select_related("candidate", "project")
        .order_by("-created_at")[:limit]
    )
    for contact in recent_contacts:
        activities.append({
            "type": "contact",
            "timestamp": contact.created_at,
            "description": (
                f"{contact.candidate.name} 컨택 기록 추가 ({contact.project.title})"
            ),
        })

    recent_projects = (
        Project.objects.filter(pk__in=project_ids)
        .select_related("client")
        .order_by("-created_at")[:limit]
    )
    for proj in recent_projects:
        client_name = proj.client.name if proj.client else ""
        activities.append({
            "type": "project",
            "timestamp": proj.created_at,
            "description": f"{client_name} {proj.title} 프로젝트 등록",
        })

    recent_subs = (
        Submission.objects.filter(project_id__in=project_ids)
        .select_related("candidate", "project")
        .order_by("-created_at")[:limit]
    )
    for sub in recent_subs:
        activities.append({
            "type": "submission",
            "timestamp": sub.created_at,
            "description": (
                f"{sub.candidate.name} 제출서류 생성 ({sub.project.title})"
            ),
        })

    activities.sort(key=lambda a: a["timestamp"], reverse=True)
    return activities[:limit]


def get_team_summary(admin_user: User, org: Organization) -> dict:
    """팀 전체 현황 + KPI (OWNER 전용).

    Fix I-R1-02: Only owner/consultant roles. Use Contact.consultant
    and Submission.consultant for per-person counts to avoid double-counting.
    """
    members = Membership.objects.filter(
        organization=org,
        role__in=[Membership.Role.OWNER, Membership.Role.CONSULTANT],
    ).select_related("user")

    consultants = []

    for member in members:
        user = member.user

        active_count = (
            Project.objects.filter(organization=org)
            .filter(Q(assigned_consultants=user) | Q(created_by=user))
            .exclude(status__in=INACTIVE_STATUSES)
            .distinct()
            .count()
        )

        # Per-consultant counts based on consultant FK (no double-counting)
        contact_count = Contact.objects.filter(
            project__organization=org,
            consultant=user,
        ).exclude(result=Contact.Result.RESERVED).count()

        submission_count = Submission.objects.filter(
            project__organization=org,
            consultant=user,
        ).count()

        interview_count = Interview.objects.filter(
            submission__project__organization=org,
            submission__consultant=user,
        ).count()

        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        closed_count = (
            Project.objects.filter(organization=org)
            .filter(Q(assigned_consultants=user) | Q(created_by=user))
            .filter(status=ProjectStatus.CLOSED_SUCCESS, updated_at__gte=month_start)
            .distinct()
            .count()
        )

        consultants.append({
            "user": user,
            "active": active_count,
            "contacts": contact_count,
            "submissions": submission_count,
            "interviews": interview_count,
            "closed": closed_count,
        })

    # KPI from org-wide distinct records
    total_contacts = Contact.objects.filter(
        project__organization=org,
    ).exclude(result=Contact.Result.RESERVED).count()

    total_submissions = Submission.objects.filter(
        project__organization=org,
    ).count()

    total_interviews = Interview.objects.filter(
        submission__project__organization=org,
    ).count()

    contact_to_submission = (
        round(total_submissions / total_contacts * 100)
        if total_contacts > 0
        else 0
    )
    submission_to_interview = (
        round(total_interviews / total_submissions * 100)
        if total_submissions > 0
        else 0
    )

    return {
        "consultants": consultants,
        "kpi": {
            "contact_to_submission": contact_to_submission,
            "submission_to_interview": submission_to_interview,
        },
    }


def get_pending_approvals(org: Organization) -> QuerySet:
    """미처리 승인 요청 목록 (OWNER 전용)."""
    return ProjectApproval.objects.filter(
        project__organization=org,
        status=ProjectApproval.Status.PENDING,
    ).select_related("project", "requested_by")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_p13_dashboard.py::TestDashboardService -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add projects/services/dashboard.py tests/test_p13_dashboard.py
git commit -m "feat(p13): implement dashboard data aggregation service"
```

---

### Task 4: Views + Templates — Dashboard views and all templates

**Files:**
- Modify: `projects/views.py`
- Create: `projects/templates/projects/dashboard.html`
- Create: `projects/templates/projects/partials/dash_full.html`
- Create: `projects/templates/projects/partials/dash_actions.html`
- Create: `projects/templates/projects/partials/dash_schedule.html`
- Create: `projects/templates/projects/partials/dash_pipeline.html`
- Create: `projects/templates/projects/partials/dash_activity.html`
- Create: `projects/templates/projects/partials/dash_admin.html`

- [ ] **Step 1: Add dashboard views to projects/views.py**

Append to `projects/views.py`:

```python
# ---------------------------------------------------------------------------
# P13: Dashboard
# ---------------------------------------------------------------------------


@login_required
def dashboard(request):
    """대시보드 메인 화면."""
    org = _get_org(request)
    user = request.user

    from projects.services.dashboard import (
        get_pending_approvals,
        get_pipeline_summary,
        get_recent_activities,
        get_team_summary,
        get_today_actions,
        get_weekly_schedule,
    )

    today_actions = get_today_actions(user, org)
    weekly_schedule = get_weekly_schedule(user, org)
    pipeline = get_pipeline_summary(user, org)
    activities = get_recent_activities(user, org, limit=10)

    is_owner = False
    try:
        is_owner = request.user.membership.role == "owner"
    except Exception:
        pass

    context = {
        "today_actions": today_actions,
        "weekly_schedule": weekly_schedule,
        "pipeline": pipeline,
        "activities": activities,
        "is_owner": is_owner,
    }

    if is_owner:
        context["pending_approvals"] = get_pending_approvals(org)
        context["team_summary"] = get_team_summary(user, org)

    if getattr(request, "htmx", None):
        return render(request, "projects/partials/dash_full.html", context)
    return render(request, "projects/dashboard.html", context)


@login_required
def dashboard_actions(request):
    """오늘의 액션 HTMX partial (새로고침용)."""
    org = _get_org(request)

    from projects.services.dashboard import get_today_actions

    today_actions = get_today_actions(request.user, org)
    return render(
        request,
        "projects/partials/dash_actions.html",
        {"today_actions": today_actions},
    )


@login_required
def dashboard_team(request):
    """팀 현황 HTMX partial (OWNER 전용)."""
    is_owner = False
    try:
        is_owner = request.user.membership.role == "owner"
    except Exception:
        pass

    if not is_owner:
        return HttpResponse(status=403)

    org = _get_org(request)

    from projects.services.dashboard import get_pending_approvals, get_team_summary

    context = {
        "pending_approvals": get_pending_approvals(org),
        "team_summary": get_team_summary(request.user, org),
    }
    return render(request, "projects/partials/dash_admin.html", context)
```

- [ ] **Step 2: Create dashboard.html**

Create `projects/templates/projects/dashboard.html`:

```html
{% extends "common/base.html" %}

{% block title %}대시보드 — synco{% endblock %}

{% block content %}
{% include "projects/partials/dash_full.html" %}
{% endblock %}
```

- [ ] **Step 3: Create dash_full.html**

Create `projects/templates/projects/partials/dash_full.html`:

```html
{% load humanize %}
<div class="p-4 lg:p-6 space-y-6">
  <div class="flex items-center justify-between">
    <h1 class="text-[22px] font-bold text-gray-900">대시보드</h1>
    <span class="text-[14px] text-gray-500">{% now "Y년 n월 j일" %}</span>
  </div>

  <div id="dash-actions">
    {% include "projects/partials/dash_actions.html" %}
  </div>

  {% include "projects/partials/dash_schedule.html" %}
  {% include "projects/partials/dash_pipeline.html" %}
  {% include "projects/partials/dash_activity.html" %}

  {% if is_owner %}
  {% include "projects/partials/dash_admin.html" %}
  {% endif %}
</div>
```

- [ ] **Step 4: Create dash_actions.html**

Create `projects/templates/projects/partials/dash_actions.html`:

```html
<section class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <div class="flex items-center justify-between mb-3">
    <h2 class="text-[16px] font-semibold text-gray-900">오늘의 액션</h2>
    <button hx-get="/dashboard/actions/" hx-target="#dash-actions" hx-swap="innerHTML"
            class="text-[13px] text-primary hover:underline">새로고침</button>
  </div>
  {% if today_actions %}
  <ul class="space-y-2">
    {% for action in today_actions %}
    <li class="flex items-center justify-between py-2 px-3 rounded-lg bg-red-50">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-red-500"></span>
        <span class="text-[14px] font-medium text-gray-900">{{ action.label }}</span>
        <span class="text-[13px] text-gray-500">{{ action.project.title }}</span>
      </div>
      <span class="text-[13px] text-gray-500">{{ action.detail }}</span>
    </li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="text-[14px] text-gray-400 text-center py-4">오늘 긴급한 액션이 없습니다.</p>
  {% endif %}
</section>
```

- [ ] **Step 5: Create dash_schedule.html**

Create `projects/templates/projects/partials/dash_schedule.html`:

```html
<section class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-[16px] font-semibold text-gray-900 mb-3">이번 주</h2>
  {% if weekly_schedule %}
  <ul class="space-y-2">
    {% for action in weekly_schedule %}
    <li class="flex items-center justify-between py-2 px-3 rounded-lg bg-yellow-50">
      <div class="flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-yellow-500"></span>
        <span class="text-[14px] font-medium text-gray-900">{{ action.label }}</span>
        <span class="text-[13px] text-gray-500">{{ action.project.title }}</span>
      </div>
      <span class="text-[13px] text-gray-500">{{ action.detail }}</span>
    </li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="text-[14px] text-gray-400 text-center py-4">이번 주 일정이 없습니다.</p>
  {% endif %}
</section>
```

- [ ] **Step 6: Create dash_pipeline.html**

Create `projects/templates/projects/partials/dash_pipeline.html`:

```html
<section class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-[16px] font-semibold text-gray-900 mb-3">내 파이프라인</h2>
  <div class="flex items-center gap-2 text-[14px] flex-wrap">
    <span class="px-2 py-1 rounded bg-blue-50 text-blue-700">신규({{ pipeline.status_counts.new|default:"0" }})</span>
    <span class="text-gray-400">&rarr;</span>
    <span class="px-2 py-1 rounded bg-blue-50 text-blue-700">서칭({{ pipeline.status_counts.searching|default:"0" }})</span>
    <span class="text-gray-400">&rarr;</span>
    <span class="px-2 py-1 rounded bg-blue-50 text-blue-700">추천({{ pipeline.status_counts.recommending|default:"0" }})</span>
    <span class="text-gray-400">&rarr;</span>
    <span class="px-2 py-1 rounded bg-blue-50 text-blue-700">면접({{ pipeline.status_counts.interviewing|default:"0" }})</span>
    <span class="text-gray-400">&rarr;</span>
    <span class="px-2 py-1 rounded bg-blue-50 text-blue-700">오퍼({{ pipeline.status_counts.negotiating|default:"0" }})</span>
  </div>
  <div class="mt-2 text-[13px] text-gray-500">
    진행 중: {{ pipeline.total_active }}건 | 이번 달 클로즈: {{ pipeline.month_closed }}건
  </div>
</section>
```

- [ ] **Step 7: Create dash_activity.html**

Create `projects/templates/projects/partials/dash_activity.html`:

```html
{% load humanize %}
<section class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-[16px] font-semibold text-gray-900 mb-3">최근 활동</h2>
  {% if activities %}
  <ul class="space-y-2">
    {% for activity in activities %}
    <li class="flex items-center gap-3 py-1.5">
      <span class="text-[12px] text-gray-400 whitespace-nowrap min-w-[60px] text-right">
        {{ activity.timestamp|naturaltime }}
      </span>
      <span class="text-[14px] text-gray-700">{{ activity.description }}</span>
    </li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="text-[14px] text-gray-400 text-center py-4">최근 활동이 없습니다.</p>
  {% endif %}
</section>
```

- [ ] **Step 8: Create dash_admin.html**

Create `projects/templates/projects/partials/dash_admin.html`:

```html
<!-- 승인 요청 -->
<section class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <div class="flex items-center justify-between mb-3">
    <h2 class="text-[16px] font-semibold text-gray-900">
      승인 요청
      {% if pending_approvals %}
      <span class="ml-1 text-[13px] text-red-500">({{ pending_approvals.count }}건)</span>
      {% endif %}
    </h2>
    {% if pending_approvals %}
    <a href="/projects/approvals/"
       hx-get="/projects/approvals/" hx-target="#main-content" hx-push-url="true"
       class="text-[13px] text-primary hover:underline">승인 큐 보기 &rarr;</a>
    {% endif %}
  </div>
  {% if pending_approvals %}
  <ul class="space-y-2">
    {% for approval in pending_approvals %}
    <li class="flex items-center justify-between py-2 px-3 rounded-lg bg-yellow-50">
      <span class="text-[14px] text-gray-900">
        {{ approval.requested_by.first_name|default:approval.requested_by.username }}
        &rarr; {{ approval.project.title }}
      </span>
    </li>
    {% endfor %}
  </ul>
  {% else %}
  <p class="text-[14px] text-gray-400 text-center py-4">대기 중인 승인 요청이 없습니다.</p>
  {% endif %}
</section>

<!-- 팀 전체 현황 -->
{% if team_summary %}
<section class="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
  <h2 class="text-[16px] font-semibold text-gray-900 mb-3">팀 전체 현황</h2>
  <div class="overflow-x-auto">
    <table class="w-full text-[14px]">
      <thead>
        <tr class="text-gray-500 border-b">
          <th class="text-left py-2 pr-4">컨설턴트</th>
          <th class="text-center py-2 px-2">진행</th>
          <th class="text-center py-2 px-2">컨택</th>
          <th class="text-center py-2 px-2">추천</th>
          <th class="text-center py-2 px-2">면접</th>
          <th class="text-center py-2 px-2">클로즈</th>
        </tr>
      </thead>
      <tbody>
        {% for c in team_summary.consultants %}
        <tr class="border-b border-gray-50">
          <td class="py-2 pr-4 font-medium">{{ c.user.first_name|default:c.user.username }}</td>
          <td class="text-center py-2 px-2">{{ c.active }}</td>
          <td class="text-center py-2 px-2">{{ c.contacts }}</td>
          <td class="text-center py-2 px-2">{{ c.submissions }}</td>
          <td class="text-center py-2 px-2">{{ c.interviews }}</td>
          <td class="text-center py-2 px-2">{{ c.closed }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <div class="mt-3 text-[13px] text-gray-500">
    팀 KPI: 컨택&rarr;추천 {{ team_summary.kpi.contact_to_submission }}%
    | 추천&rarr;면접 {{ team_summary.kpi.submission_to_interview }}%
  </div>
</section>
{% endif %}
```

- [ ] **Step 9: Commit**

```bash
git add projects/views.py projects/templates/projects/dashboard.html projects/templates/projects/partials/dash_*.html
git commit -m "feat(p13): add dashboard views and templates"
```

---

### Task 5: URL routing + login redirect

**Files:**
- Modify: `main/urls.py`
- Modify: `main/settings.py`
- Modify: `accounts/views.py`
- Test: `tests/test_p13_dashboard.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_p13_dashboard.py`:

```python
# --- Task 5: Routing + view tests ---

class TestDashboardViews:
    @pytest.mark.django_db
    def test_dashboard_requires_login(self):
        c = TestClient()
        resp = c.get("/dashboard/")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    @pytest.mark.django_db
    def test_root_is_dashboard(self, auth_consultant):
        resp = auth_consultant.get("/")
        assert resp.status_code == 200
        assert "대시보드" in resp.content.decode()

    @pytest.mark.django_db
    def test_dashboard_explicit_url(self, auth_consultant):
        resp = auth_consultant.get("/dashboard/")
        assert resp.status_code == 200
        assert "대시보드" in resp.content.decode()

    @pytest.mark.django_db
    def test_dashboard_owner_sees_admin(self, auth_owner):
        resp = auth_owner.get("/dashboard/")
        content = resp.content.decode()
        assert "팀 전체 현황" in content

    @pytest.mark.django_db
    def test_dashboard_consultant_no_admin(self, auth_consultant):
        resp = auth_consultant.get("/dashboard/")
        content = resp.content.decode()
        assert "팀 전체 현황" not in content

    @pytest.mark.django_db
    def test_dashboard_actions_partial(self, auth_consultant):
        resp = auth_consultant.get("/dashboard/actions/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_dashboard_team_owner_only(self, auth_consultant, auth_owner):
        resp = auth_consultant.get("/dashboard/team/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 403

        resp = auth_owner.get("/dashboard/team/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_unauthenticated_root_redirects_to_login(self):
        c = TestClient()
        resp = c.get("/")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_p13_dashboard.py::TestDashboardViews -v`
Expected: FAIL

- [ ] **Step 3: Update main/urls.py**

Replace `main/urls.py` with:

```python
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from projects.views import dashboard, dashboard_actions, dashboard_team

urlpatterns = [
    path("admin/", admin.site.urls),
    # P13: Dashboard — root and explicit URLs
    path("", dashboard, name="dashboard"),
    path("dashboard/", dashboard, name="dashboard_explicit"),
    path("dashboard/actions/", dashboard_actions, name="dashboard_actions"),
    path("dashboard/team/", dashboard_team, name="dashboard_team"),
    # Accounts (login, logout, settings, etc.)
    path("accounts/", include("accounts.urls_accounts")),
    path("candidates/", include("candidates.urls")),
    path("clients/", include("clients.urls")),
    path("projects/", include("projects.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

**Wait — `include("accounts.urls")` is currently mounted at `""`, which means it handles `accounts/login/`, `accounts/settings/`, etc.** We cannot just mount it at `accounts/` because the existing URLs already have `accounts/` prefix built in: e.g. `path("accounts/login/", ...)`.

So if we mount at `accounts/`, the URL would become `accounts/accounts/login/`. Instead, we need to keep the `path("", include("accounts.urls"))` but put our dashboard route BEFORE it so Django matches `/` to dashboard first.

**Corrected main/urls.py:**

```python
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from projects.views import dashboard, dashboard_actions, dashboard_team

urlpatterns = [
    path("admin/", admin.site.urls),
    # P13: Dashboard — root entry point (must be before accounts.urls include)
    path("", dashboard, name="dashboard"),
    path("dashboard/", dashboard, name="dashboard_explicit"),
    path("dashboard/actions/", dashboard_actions, name="dashboard_actions"),
    path("dashboard/team/", dashboard_team, name="dashboard_team"),
    # Accounts (includes login, settings, etc. at root prefix)
    path("", include("accounts.urls")),
    path("candidates/", include("candidates.urls")),
    path("clients/", include("clients.urls")),
    path("projects/", include("projects.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

This works because:
- `path("", dashboard)` matches `/` exactly (no trailing slash issue since Django APPEND_SLASH handles it)
- `path("", include("accounts.urls"))` still routes `accounts/login/`, `accounts/settings/`, etc.
- The old `path("", lambda r: redirect("/candidates/"), name="root")` is removed

- [ ] **Step 4: Update accounts/views.py — change home() redirect**

Change line 12 from:

```python
    return redirect("candidate_list")
```

to:

```python
    return redirect("/")
```

- [ ] **Step 5: Add LOGIN_REDIRECT_URL to settings**

In `main/settings.py`, add after the auth-related settings:

```python
LOGIN_REDIRECT_URL = "/"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_p13_dashboard.py::TestDashboardViews -v`
Expected: PASS

- [ ] **Step 7: Run full test suite for regressions**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All PASS. If any test expects `/` → candidates redirect, update it.

- [ ] **Step 8: Commit**

```bash
git add main/urls.py main/settings.py accounts/views.py tests/test_p13_dashboard.py
git commit -m "feat(p13): route root URL to dashboard, update login redirect"
```

---

### Task 6: Navigation — Sidebar and bottom nav updates

**Files:**
- Modify: `templates/common/nav_sidebar.html`
- Modify: `templates/common/nav_bottom.html`

- [ ] **Step 1: Update sidebar — add dashboard as first item**

Replace `templates/common/nav_sidebar.html` with:

```html
<div class="mb-8">
  <h1 class="text-heading font-bold text-primary">synco</h1>
</div>
<nav class="space-y-1 flex-1" id="sidebar-nav" aria-label="사이드바 네비게이션">
  <a href="/"
     hx-get="/" hx-target="#main-content" hx-push-url="true"
     data-nav="dashboard"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
    대시보드
  </a>
  <a href="/candidates/"
     hx-get="/candidates/" hx-target="#main-content" hx-push-url="true"
     data-nav="candidates"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
    후보자
  </a>
  <a href="/projects/"
     hx-get="/projects/" hx-target="#main-content" hx-push-url="true"
     data-nav="projects"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/></svg>
    프로젝트
  </a>
  <a href="/clients/"
     hx-get="/clients/" hx-target="#main-content" hx-push-url="true"
     data-nav="clients"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>
    고객사
  </a>
  <a href="/accounts/settings/"
     hx-get="/accounts/settings/" hx-target="#main-content" hx-push-url="true"
     data-nav="settings"
     class="sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] text-gray-500 hover:bg-gray-50">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
    설정
  </a>

<script>
function updateSidebar() {
  var path = window.location.pathname;
  document.querySelectorAll('.sidebar-tab').forEach(function(tab) {
    var key = tab.dataset.nav;
    var active = (key === 'dashboard' && (path === '/' || path.startsWith('/dashboard'))) ||
                 (key === 'candidates' && path.startsWith('/candidates')) ||
                 (key === 'projects' && path.startsWith('/projects')) ||
                 (key === 'clients' && path.startsWith('/clients')) ||
                 (key === 'settings' && path.includes('/settings'));
    tab.className = 'sidebar-tab flex items-center gap-3 px-3 py-2.5 rounded-lg text-[15px] ' +
      (active ? 'bg-primary-light text-primary font-semibold' : 'text-gray-500 hover:bg-gray-50');
  });
}
updateSidebar();
document.body.addEventListener('htmx:pushedIntoHistory', updateSidebar);
document.body.addEventListener('htmx:replacedInHistory', updateSidebar);
</script>
</nav>
```

- [ ] **Step 2: Update bottom nav — add dashboard as first item**

Replace `templates/common/nav_bottom.html` with:

```html
{% load static %}
<nav class="fixed bottom-0 inset-x-0 bg-white border-t border-gray-200 lg:hidden z-40" id="bottom-nav" aria-label="메인 네비게이션">
  <div class="max-w-md mx-auto flex justify-around py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))]">
    <a href="/"
       hx-get="/" hx-target="#main-content" hx-push-url="true"
       data-nav="dashboard"
       class="nav-tab flex flex-col items-center py-1 px-3 min-w-[64px] text-gray-500">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
      <span class="text-[12px] mt-0.5">대시보드</span>
    </a>
    <a href="/candidates/"
       hx-get="/candidates/" hx-target="#main-content" hx-push-url="true"
       data-nav="candidates"
       class="nav-tab flex flex-col items-center py-1 px-3 min-w-[64px] text-gray-500">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
      <span class="text-[12px] mt-0.5">후보자</span>
    </a>
    <a href="/projects/"
       hx-get="/projects/" hx-target="#main-content" hx-push-url="true"
       data-nav="projects"
       class="nav-tab flex flex-col items-center py-1 px-3 min-w-[64px] text-gray-500">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/></svg>
      <span class="text-[12px] mt-0.5">프로젝트</span>
    </a>
    <a href="/clients/"
       hx-get="/clients/" hx-target="#main-content" hx-push-url="true"
       data-nav="clients"
       class="nav-tab flex flex-col items-center py-1 px-3 min-w-[64px] text-gray-500">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>
      <span class="text-[12px] mt-0.5">고객사</span>
    </a>
    <a href="/accounts/settings/"
       hx-get="/accounts/settings/" hx-target="#main-content" hx-push-url="true"
       data-nav="settings"
       class="nav-tab flex flex-col items-center py-1 px-3 min-w-[64px] text-gray-500">
      <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
      <span class="text-[12px] mt-0.5">설정</span>
    </a>
  </div>
</nav>

<script>
function updateNav() {
  var path = window.location.pathname;
  document.querySelectorAll('.nav-tab').forEach(function(tab) {
    var key = tab.dataset.nav;
    var active = (key === 'dashboard' && (path === '/' || path.startsWith('/dashboard'))) ||
                 (key === 'candidates' && path.startsWith('/candidates')) ||
                 (key === 'projects' && path.startsWith('/projects')) ||
                 (key === 'clients' && path.startsWith('/clients')) ||
                 (key === 'settings' && path.includes('/settings'));
    tab.className = tab.className.replace(/text-primary font-semibold|text-gray-500/g, '');
    tab.classList.add(active ? 'text-primary' : 'text-gray-500');
    if (active) tab.classList.add('font-semibold');
  });
}
updateNav();
document.body.addEventListener('htmx:pushedIntoHistory', updateNav);
document.body.addEventListener('htmx:replacedInHistory', updateNav);
</script>
```

- [ ] **Step 3: Commit**

```bash
git add templates/common/nav_sidebar.html templates/common/nav_bottom.html
git commit -m "feat(p13): add dashboard to sidebar and bottom nav as first menu item"
```

---

### Task 7: Full integration test + regression fix + lint

- [ ] **Step 1: Run all P13 tests**

Run: `uv run pytest tests/test_p13_dashboard.py -v`
Expected: All PASS

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 3: Fix any regressions**

If tests assert `/` redirects to candidates, update them.

- [ ] **Step 4: Run ruff**

```bash
uv run ruff check projects/services/urgency.py projects/services/dashboard.py projects/views.py accounts/views.py main/urls.py main/settings.py tests/test_p13_dashboard.py --fix
uv run ruff format projects/services/urgency.py projects/services/dashboard.py projects/views.py accounts/views.py main/urls.py main/settings.py tests/test_p13_dashboard.py
```

- [ ] **Step 5: Migration check**

```bash
uv run python manage.py makemigrations --check --dry-run
```
Expected: "No changes detected"

- [ ] **Step 6: Commit any fixes**

```bash
git add -u
git commit -m "fix(p13): regressions and lint"
```

<!-- forge:p13:구현담금질:complete:2026-04-09T01:30:00+09:00 -->
