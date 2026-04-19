import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import Membership, Organization, User
from clients.models import Client
from projects.models import Project, ProjectStatus


# ---------------------------------------------------------------------------
# Fixtures (local, self-contained — do not rely on conftest project fixture
# which uses a different client_company)
# ---------------------------------------------------------------------------

@pytest.fixture
def org(db):
    return Organization.objects.create(name="DetailTestOrg")


@pytest.fixture
def owner(org):
    u = User.objects.create_user(username="detail_owner", password="x")
    Membership.objects.create(user=u, organization=org, role="owner", status="active")
    return u


@pytest.fixture
def owner_client(client, owner):
    client.force_login(owner)
    return client


@pytest.fixture
def detail_client(org):
    return Client.objects.create(
        organization=org,
        name="DetailCorp",
        website="https://detail.example.com",
        description="헤드헌팅 고객사 설명입니다",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_detail_renders_profile(owner_client, detail_client):
    """client_detail 페이지에 고객사 이름·설명·웹사이트가 렌더링된다."""
    url = reverse("clients:client_detail", kwargs={"pk": detail_client.pk})
    resp = owner_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "DetailCorp" in body
    assert "헤드헌팅 고객사 설명입니다" in body
    # website is displayed without protocol prefix
    assert "detail.example.com" in body


@pytest.mark.django_db
def test_detail_projects_panel_all(org, owner_client, detail_client):
    """status=all 필터 시 진행중·종료 프로젝트 모두 표시된다."""
    Project.objects.create(
        organization=org,
        client=detail_client,
        title="ActiveProject",
        status=ProjectStatus.OPEN,
    )
    Project.objects.create(
        organization=org,
        client=detail_client,
        title="ClosedProject",
        status=ProjectStatus.CLOSED,
        result="success",
        closed_at=timezone.now(),
    )
    url = reverse("clients:client_projects_panel", kwargs={"pk": detail_client.pk})
    resp = owner_client.get(url + "?status=all")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "ActiveProject" in body
    assert "ClosedProject" in body


@pytest.mark.django_db
def test_detail_projects_panel_active_only(org, owner_client, detail_client):
    """status=active 필터 시 진행중 프로젝트만 표시된다."""
    Project.objects.create(
        organization=org,
        client=detail_client,
        title="ActiveProject",
        status=ProjectStatus.OPEN,
    )
    Project.objects.create(
        organization=org,
        client=detail_client,
        title="ClosedProject",
        status=ProjectStatus.CLOSED,
        result="success",
        closed_at=timezone.now(),
    )
    url = reverse("clients:client_projects_panel", kwargs={"pk": detail_client.pk})
    resp = owner_client.get(url + "?status=active")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "ActiveProject" in body
    assert "ClosedProject" not in body


@pytest.mark.django_db
def test_detail_empty_projects_shows_cta(owner_client, detail_client):
    """프로젝트가 없을 때 client_detail 에 빈 상태 메시지가 표시된다."""
    url = reverse("clients:client_detail", kwargs={"pk": detail_client.pk})
    resp = owner_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "등록된 프로젝트가 없습니다" in body
