import pytest
from django.utils import timezone

from accounts.models import Organization
from clients.models import Client
from clients.services.client_queries import list_clients_with_stats
from projects.models import Project, Application


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org")


@pytest.mark.django_db
def test_list_clients_with_stats_zero_projects(org):
    Client.objects.create(organization=org, name="A")
    qs = list_clients_with_stats(org)
    client = qs.get(name="A")
    assert client.offers_count == 0
    assert client.success_count == 0
    assert client.placed_count == 0
    assert client.active_count == 0


@pytest.mark.django_db
def test_list_clients_with_stats_counts_projects(org):
    c = Client.objects.create(organization=org, name="A")
    Project.objects.create(
        client=c, organization=org, title="P1", status="open", result=""
    )
    Project.objects.create(
        client=c, organization=org, title="P2", status="closed", result="success", closed_at=timezone.now()
    )
    qs = list_clients_with_stats(org)
    client = qs.get(pk=c.pk)
    assert client.offers_count == 2
    assert client.success_count == 1
    assert client.active_count == 1
