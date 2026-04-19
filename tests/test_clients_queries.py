import pytest
from django.utils import timezone

from accounts.models import Organization
from clients.models import Client, IndustryCategory
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


@pytest.mark.django_db
def test_filter_by_category(org):
    Client.objects.create(organization=org, name="Bio", industry=IndustryCategory.BIO_PHARMA.value)
    Client.objects.create(organization=org, name="IT", industry=IndustryCategory.IT_SW.value)
    qs = list_clients_with_stats(org, categories=["BIO_PHARMA"])
    assert qs.count() == 1
    assert qs.first().name == "Bio"


@pytest.mark.django_db
def test_filter_by_size(org):
    Client.objects.create(organization=org, name="L", size="대기업")
    Client.objects.create(organization=org, name="S", size="중소")
    qs = list_clients_with_stats(org, sizes=["대기업"])
    assert qs.count() == 1
    assert qs.first().name == "L"


@pytest.mark.django_db
def test_filter_by_region(org):
    Client.objects.create(organization=org, name="A", region="서울")
    Client.objects.create(organization=org, name="B", region="경기")
    qs = list_clients_with_stats(org, regions=["서울"])
    assert qs.count() == 1


@pytest.mark.django_db
def test_filter_by_offers_range(org):
    c1 = Client.objects.create(organization=org, name="Zero")
    c2 = Client.objects.create(organization=org, name="Three")
    for i in range(3):
        Project.objects.create(client=c2, organization=org, title=f"P{i}", status="open")
    qs = list_clients_with_stats(org, offers_range="0")
    assert qs.count() == 1
    assert qs.first().name == "Zero"
    qs = list_clients_with_stats(org, offers_range="1-5")
    assert qs.count() == 1
    assert qs.first().name == "Three"


@pytest.mark.django_db
def test_filter_by_success_status_has(org):
    c1 = Client.objects.create(organization=org, name="HasSuccess")
    c2 = Client.objects.create(organization=org, name="NoOffers")
    Project.objects.create(client=c1, organization=org, title="P", status="closed", result="success", closed_at=timezone.now())
    qs = list_clients_with_stats(org, success_status="has")
    assert qs.count() == 1
    assert qs.first().name == "HasSuccess"


@pytest.mark.django_db
def test_filter_by_success_status_none(org):
    c1 = Client.objects.create(organization=org, name="OffersNoSuccess")
    c2 = Client.objects.create(organization=org, name="HasSuccess")
    Project.objects.create(client=c1, organization=org, title="P", status="open", result="")
    Project.objects.create(client=c2, organization=org, title="Q", status="closed", result="success", closed_at=timezone.now())
    qs = list_clients_with_stats(org, success_status="none")
    assert qs.count() == 1
    assert qs.first().name == "OffersNoSuccess"


@pytest.mark.django_db
def test_filter_by_success_status_no_offers(org):
    Client.objects.create(organization=org, name="NoOffers")
    c2 = Client.objects.create(organization=org, name="HasOffers")
    Project.objects.create(client=c2, organization=org, title="P", status="open")
    qs = list_clients_with_stats(org, success_status="no_offers")
    assert qs.count() == 1
    assert qs.first().name == "NoOffers"
