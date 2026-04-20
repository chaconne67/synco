import pytest
from django.urls import reverse

from accounts.models import Membership, Organization, User


@pytest.fixture
def org(db):
    return Organization.objects.create(name="TestOrg")


@pytest.fixture
def owner(org):
    u = User.objects.create_user(username="owner", password="x")
    Membership.objects.create(user=u, organization=org, role="owner")
    return u


@pytest.fixture
def owner_client(client, owner):
    client.force_login(owner)
    return client


@pytest.mark.django_db
def test_dashboard_renders_with_empty_org(owner_client):
    """Skeleton: dashboard renders 200 with empty org, no crash."""
    resp = owner_client.get(reverse("dashboard"))
    assert resp.status_code == 200
    assert b"Monthly Success" in resp.content


from datetime import timedelta

from django.utils import timezone

from clients.models import Client
from projects.models import Project


def _close_project(project, result, at):
    """Helper: close a project at specific datetime."""
    Project.objects.filter(pk=project.pk).update(
        status="closed", result=result, closed_at=at
    )


@pytest.fixture
def client_obj(org):
    return Client.objects.create(organization=org, name="ClientCo")


@pytest.mark.django_db
def test_s1_monthly_success_counts(owner_client, org, client_obj):
    """S1-1: 이번 달 성공/진행중/성공률 렌더."""
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month = month_start - timedelta(days=1)

    # 이번 달 성공 2건
    for i in range(2):
        p = Project.objects.create(organization=org, client=client_obj, title=f"S{i}")
        _close_project(p, "success", month_start + timedelta(days=1))
    # 이번 달 실패 1건
    p = Project.objects.create(organization=org, client=client_obj, title="F1")
    _close_project(p, "fail", month_start + timedelta(days=2))
    # 지난 달 성공 (제외되어야 함)
    p = Project.objects.create(organization=org, client=client_obj, title="OLD")
    _close_project(p, "success", last_month)
    # 진행 중 3건
    for i in range(3):
        Project.objects.create(organization=org, client=client_obj, title=f"O{i}")

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()

    # 큰 숫자 = 이번 달 성공 2건
    assert 'data-testid="s1-success-count">2<' in body
    # 진행 중 = 3건
    assert 'data-testid="s1-active-count">3<' in body
    # 성공률 = 2 / (2+1) = 67%
    assert 'data-testid="s1-success-rate">67<' in body


@pytest.mark.django_db
def test_s1_monthly_success_empty(owner_client):
    """S1-1 빈 조직: 0/0/— 렌더."""
    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    assert 'data-testid="s1-success-count">0<' in body
    assert 'data-testid="s1-active-count">0<' in body
    assert 'data-testid="s1-success-rate">—<' in body
