import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import Membership, Organization, User
from clients.models import Client
from projects.models import Project, ProjectStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def org(db):
    return Organization.objects.create(name="DeleteTestOrg")


@pytest.fixture
def owner(org):
    u = User.objects.create_user(username="delete_owner", password="x")
    Membership.objects.create(user=u, organization=org, role="owner", status="active")
    return u


@pytest.fixture
def owner_client(client, owner):
    client.force_login(owner)
    return client


@pytest.fixture
def delete_client(org):
    return Client.objects.create(
        organization=org,
        name="DeleteCorp",
        website="https://delete.example.com",
        description="삭제 테스트 고객사",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_delete_blocks_when_any_projects_exist(org, owner_client, delete_client):
    """client_delete 시 ANY 프로젝트(open/closed)가 있으면 삭제를 막는다.

    현재 closed-success 프로젝트 1건을 생성. 이전 로직은 open 프로젝트만 확인했으므로
    이 테스트는 실패해야 함. 수정 후 통과.
    """
    Project.objects.create(
        organization=org,
        client=delete_client,
        title="ClosedSuccessProject",
        status=ProjectStatus.CLOSED,
        result="success",
        closed_at=timezone.now(),
    )

    url = reverse("clients:client_delete", kwargs={"pk": delete_client.pk})
    resp = owner_client.post(url)

    # 클라이언트는 여전히 존재해야 함
    assert Client.objects.filter(pk=delete_client.pk).exists()

    # 응답 바디에 오류 메시지 포함
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "삭제할 수 없습니다" in body


@pytest.mark.django_db
def test_delete_allows_when_no_projects(org, owner_client, delete_client):
    """프로젝트가 없을 때 client_delete가 클라이언트를 삭제한다."""
    pk = delete_client.pk
    url = reverse("clients:client_delete", kwargs={"pk": pk})
    resp = owner_client.post(url)

    # 삭제 후 redirect 또는 200
    assert resp.status_code in (200, 302)

    # 클라이언트는 삭제되어야 함
    assert not Client.objects.filter(pk=pk).exists()
