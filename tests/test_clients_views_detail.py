import pytest
from django.urls import reverse
from django.utils import timezone

from clients.models import Client
from projects.models import Project, ProjectStatus



@pytest.fixture
def detail_client(legacy_org):
    return Client.objects.create(
        organization=legacy_org,
        name="DetailCorp",
        website="https://detail.example.com",
        description="헤드헌팅 고객사 설명입니다",
    )


@pytest.mark.django_db
def test_detail_renders_profile(boss_client, detail_client):
    """client_detail 페이지에 고객사 이름·설명·웹사이트가 렌더링된다."""
    url = reverse("clients:client_detail", kwargs={"pk": detail_client.pk})
    resp = boss_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "DetailCorp" in body
    assert "헤드헌팅 고객사 설명입니다" in body
    assert "detail.example.com" in body


@pytest.mark.django_db
def test_detail_projects_panel_all(legacy_org, boss_client, detail_client):
    """status=all 필터 시 진행중·종료 프로젝트 모두 표시된다."""
    Project.objects.create(
        organization=legacy_org,
        client=detail_client,
        title="ActiveProject",
        status=ProjectStatus.OPEN,
    )
    Project.objects.create(
        organization=legacy_org,
        client=detail_client,
        title="ClosedProject",
        status=ProjectStatus.CLOSED,
        result="success",
        closed_at=timezone.now(),
    )
    url = reverse("clients:client_projects_panel", kwargs={"pk": detail_client.pk})
    resp = boss_client.get(url + "?status=all")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "ActiveProject" in body
    assert "ClosedProject" in body


@pytest.mark.django_db
def test_detail_projects_panel_active_only(legacy_org, boss_client, detail_client):
    """status=active 필터 시 진행중 프로젝트만 표시된다."""
    Project.objects.create(
        organization=legacy_org,
        client=detail_client,
        title="ActiveProject",
        status=ProjectStatus.OPEN,
    )
    Project.objects.create(
        organization=legacy_org,
        client=detail_client,
        title="ClosedProject",
        status=ProjectStatus.CLOSED,
        result="success",
        closed_at=timezone.now(),
    )
    url = reverse("clients:client_projects_panel", kwargs={"pk": detail_client.pk})
    resp = boss_client.get(url + "?status=active")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "ActiveProject" in body
    assert "ClosedProject" not in body


@pytest.mark.django_db
def test_detail_empty_projects_shows_cta(boss_client, detail_client):
    """프로젝트가 없을 때 client_detail 에 빈 상태 메시지가 표시된다."""
    url = reverse("clients:client_detail", kwargs={"pk": detail_client.pk})
    resp = boss_client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "등록된 프로젝트가 없습니다" in body
