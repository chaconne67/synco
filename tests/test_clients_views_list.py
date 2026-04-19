import pytest
from django.urls import reverse

from accounts.models import Organization, Membership, User
from clients.models import Client, IndustryCategory
from projects.models import Project


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Org")


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
def test_list_renders_header_and_empty_state(owner_client):
    resp = owner_client.get(reverse("clients:client_list"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Clients" in body
    assert "등록된 고객사" in body


@pytest.mark.django_db
def test_list_renders_cards(org, owner_client):
    Client.objects.create(
        organization=org,
        name="SKBP",
        industry=IndustryCategory.BIO_PHARMA.value
    )
    resp = owner_client.get(reverse("clients:client_list"))
    assert "SKBP" in resp.content.decode()


@pytest.mark.django_db
def test_list_category_filter(org, owner_client):
    Client.objects.create(
        organization=org,
        name="BioFirm",
        industry=IndustryCategory.BIO_PHARMA.value
    )
    Client.objects.create(
        organization=org,
        name="TechCorp",
        industry=IndustryCategory.IT_SW.value
    )
    resp = owner_client.get(reverse("clients:client_list") + "?cat=BIO_PHARMA")
    body = resp.content.decode()
    assert "BioFirm" in body
    assert "TechCorp" not in body


@pytest.mark.django_db
def test_list_size_filter(org, owner_client):
    Client.objects.create(organization=org, name="Big", size="대기업")
    Client.objects.create(organization=org, name="Small", size="중소")
    resp = owner_client.get(reverse("clients:client_list") + "?size=대기업")
    body = resp.content.decode()
    assert "Big" in body
    assert "Small" not in body


@pytest.mark.django_db
def test_list_page_endpoint_returns_next_cards(org, owner_client):
    for i in range(10):
        Client.objects.create(organization=org, name=f"C{i:02d}")
    resp = owner_client.get(reverse("clients:client_list_page") + "?page=2")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert body.count("client-logo-tile") == 1


@pytest.mark.django_db
def test_list_active_count_shown(org, owner_client):
    c = Client.objects.create(organization=org, name="A")
    Project.objects.create(client=c, organization=org, title="P", status="open")
    resp = owner_client.get(reverse("clients:client_list"))
    body = resp.content.decode()
    assert "1" in body
    assert "Active" in body


@pytest.mark.django_db
def test_member_cannot_see_add_button(org, db, client):
    member = User.objects.create_user(username="m", password="x")
    Membership.objects.create(user=member, organization=org, role="consultant")
    client.force_login(member)
    resp = client.get(reverse("clients:client_list"))
    assert "Add Client" not in resp.content.decode()
