import pytest
from django.utils import timezone

from clients.models import Client, IndustryCategory
from clients.services.client_queries import (
    available_regions,
    category_counts,
    client_projects,
    client_stats,
    list_clients_with_stats,
)
from projects.models import Project


@pytest.mark.django_db
def test_list_clients_with_stats_zero_projects():
    Client.objects.create(name="A")
    qs = list_clients_with_stats()
    client = qs.get(name="A")
    assert client.offers_count == 0
    assert client.success_count == 0
    assert client.placed_count == 0
    assert client.active_count == 0


@pytest.mark.django_db
def test_list_clients_with_stats_counts_projects():
    c = Client.objects.create(name="A")
    Project.objects.create(client=c, title="P1", status="open", result="")
    Project.objects.create(
        client=c,
        title="P2",
        status="closed",
        result="success",
        closed_at=timezone.now(),
    )
    qs = list_clients_with_stats()
    client = qs.get(pk=c.pk)
    assert client.offers_count == 2
    assert client.success_count == 1
    assert client.active_count == 1


@pytest.mark.django_db
def test_filter_by_category():
    Client.objects.create(name="Bio", industry=IndustryCategory.BIO_PHARMA.value)
    Client.objects.create(name="IT", industry=IndustryCategory.IT_SW.value)
    qs = list_clients_with_stats(categories=["BIO_PHARMA"])
    assert qs.count() == 1
    assert qs.first().name == "Bio"


@pytest.mark.django_db
def test_filter_by_size():
    Client.objects.create(name="L", size="대기업")
    Client.objects.create(name="S", size="중소")
    qs = list_clients_with_stats(sizes=["대기업"])
    assert qs.count() == 1
    assert qs.first().name == "L"


@pytest.mark.django_db
def test_filter_by_region():
    Client.objects.create(name="A", region="서울")
    Client.objects.create(name="B", region="경기")
    qs = list_clients_with_stats(regions=["서울"])
    assert qs.count() == 1


@pytest.mark.django_db
def test_filter_by_offers_range():
    Client.objects.create(name="Zero")
    c2 = Client.objects.create(name="Three")
    for i in range(3):
        Project.objects.create(client=c2, title=f"P{i}", status="open")
    qs = list_clients_with_stats(offers_range="0")
    assert qs.count() == 1
    assert qs.first().name == "Zero"
    qs = list_clients_with_stats(offers_range="1-5")
    assert qs.count() == 1
    assert qs.first().name == "Three"


@pytest.mark.django_db
def test_filter_by_success_status_has():
    c1 = Client.objects.create(name="HasSuccess")
    Client.objects.create(name="NoOffers")
    Project.objects.create(
        client=c1,
        title="P",
        status="closed",
        result="success",
        closed_at=timezone.now(),
    )
    qs = list_clients_with_stats(success_status="has")
    assert qs.count() == 1
    assert qs.first().name == "HasSuccess"


@pytest.mark.django_db
def test_filter_by_success_status_none():
    c1 = Client.objects.create(name="OffersNoSuccess")
    c2 = Client.objects.create(name="HasSuccess")
    Project.objects.create(client=c1, title="P", status="open", result="")
    Project.objects.create(
        client=c2,
        title="Q",
        status="closed",
        result="success",
        closed_at=timezone.now(),
    )
    qs = list_clients_with_stats(success_status="none")
    assert qs.count() == 1
    assert qs.first().name == "OffersNoSuccess"


@pytest.mark.django_db
def test_filter_by_success_status_no_offers():
    Client.objects.create(name="NoOffers")
    c2 = Client.objects.create(name="HasOffers")
    Project.objects.create(client=c2, title="P", status="open")
    qs = list_clients_with_stats(success_status="no_offers")
    assert qs.count() == 1
    assert qs.first().name == "NoOffers"


@pytest.mark.django_db
def test_category_counts():
    Client.objects.create(name="A", industry="바이오/제약")
    Client.objects.create(name="B", industry="바이오/제약")
    Client.objects.create(name="C", industry="IT/SW")
    counts = category_counts()
    assert counts["BIO_PHARMA"] == 2
    assert counts["IT_SW"] == 1
    assert counts["FINANCE"] == 0


@pytest.mark.django_db
def test_available_regions():
    Client.objects.create(name="A", region="서울")
    Client.objects.create(name="B", region="서울")
    Client.objects.create(name="C", region="경기")
    Client.objects.create(name="D", region="")
    regions = available_regions()
    assert sorted(regions) == ["경기", "서울"]


@pytest.mark.django_db
def test_client_stats():
    c = Client.objects.create(name="A")
    Project.objects.create(client=c, title="P", status="open")
    Project.objects.create(
        client=c, title="Q", status="closed", result="success", closed_at=timezone.now()
    )
    stats = client_stats(c)
    assert stats["offers"] == 2
    assert stats["success"] == 1
    assert stats["active"] == 1
    assert stats["placed"] == 0


@pytest.mark.django_db
def test_client_projects_status_filter():
    c = Client.objects.create(name="A")
    Project.objects.create(client=c, title="P1", status="open")
    Project.objects.create(
        client=c,
        title="P2",
        status="closed",
        result="success",
        closed_at=timezone.now(),
    )
    assert client_projects(c, status_filter="active").count() == 1
    assert client_projects(c, status_filter="closed").count() == 1
    assert client_projects(c, status_filter="all").count() == 2
