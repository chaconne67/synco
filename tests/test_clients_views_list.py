import pytest
from django.urls import reverse

from clients.models import Client, IndustryCategory
from projects.models import Project


@pytest.mark.django_db
def test_list_renders_header_and_empty_state(boss_client):
    resp = boss_client.get(reverse("clients:client_list"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Clients" in body
    assert "등록된 고객사" in body


@pytest.mark.django_db
def test_list_renders_cards(db, boss_client):
    Client.objects.create(name="SKBP", industry=IndustryCategory.BIO_PHARMA.value)
    resp = boss_client.get(reverse("clients:client_list"))
    assert "SKBP" in resp.content.decode()


@pytest.mark.django_db
def test_list_category_filter(db, boss_client):
    Client.objects.create(name="BioFirm", industry=IndustryCategory.BIO_PHARMA.value)
    Client.objects.create(name="TechCorp", industry=IndustryCategory.IT_SW.value)
    resp = boss_client.get(reverse("clients:client_list") + "?cat=BIO_PHARMA")
    body = resp.content.decode()
    assert "BioFirm" in body
    assert "TechCorp" not in body


@pytest.mark.django_db
def test_list_size_filter(db, boss_client):
    Client.objects.create(name="Big", size="대기업")
    Client.objects.create(name="Small", size="중소")
    resp = boss_client.get(reverse("clients:client_list") + "?size=대기업")
    body = resp.content.decode()
    assert "Big" in body
    assert "Small" not in body


@pytest.mark.django_db
def test_list_page_endpoint_returns_next_cards(db, boss_client):
    for i in range(10):
        Client.objects.create(name=f"C{i:02d}")
    resp = boss_client.get(reverse("clients:client_list_page") + "?page=2")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert body.count("client-card") == 1


@pytest.mark.django_db
def test_list_active_count_shown(db, boss_client, boss_user):
    from projects.models import ProjectStatus

    c = Client.objects.create(name="A")
    Project.objects.create(
        client=c, title="P", status=ProjectStatus.OPEN, created_by=boss_user
    )
    resp = boss_client.get(reverse("clients:client_list"))
    body = resp.content.decode()
    assert "1" in body
    assert "Active" in body


@pytest.mark.django_db
def test_staff_cannot_see_add_button(staff_client):
    resp = staff_client.get(reverse("clients:client_list"))
    assert "Add Client" not in resp.content.decode()
