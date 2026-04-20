import pytest
from django.urls import reverse
from django.utils import timezone

from clients.models import Client
from projects.models import Project, ProjectStatus


@pytest.fixture
def legacy_org(db):
    """Temporary shim until T7 drops organization FK."""
    from accounts.models import Organization

    return Organization.objects.create(name="Legacy")


@pytest.fixture
def delete_client(legacy_org):
    return Client.objects.create(
        organization=legacy_org,
        name="DeleteCorp",
        website="https://delete.example.com",
        description="삭제 테스트 고객사",
    )


@pytest.mark.django_db
def test_delete_blocks_when_any_projects_exist(legacy_org, boss_client, delete_client):
    """client_delete 시 ANY 프로젝트(open/closed)가 있으면 삭제를 막는다."""
    Project.objects.create(
        organization=legacy_org,
        client=delete_client,
        title="ClosedSuccessProject",
        status=ProjectStatus.CLOSED,
        result="success",
        closed_at=timezone.now(),
    )

    url = reverse("clients:client_delete", kwargs={"pk": delete_client.pk})
    resp = boss_client.post(url)

    assert Client.objects.filter(pk=delete_client.pk).exists()
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "삭제할 수 없습니다" in body


@pytest.mark.django_db
def test_delete_allows_when_no_projects(boss_client, delete_client):
    """프로젝트가 없을 때 client_delete가 클라이언트를 삭제한다."""
    pk = delete_client.pk
    url = reverse("clients:client_delete", kwargs={"pk": pk})
    resp = boss_client.post(url)

    assert resp.status_code in (200, 302)
    assert not Client.objects.filter(pk=pk).exists()
