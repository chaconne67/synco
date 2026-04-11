"""P02: Client Management view tests.

Tests for Client CRUD, Organization isolation, login_required,
search, contact_persons JSON, delete protection, and Contract inline CRUD.
"""

import json

import pytest
from django.test import Client as TestClient

from accounts.models import Membership, Organization, User
from clients.models import Client, Contract
from projects.models import Project


# --- Fixtures ---


@pytest.fixture
def org(db):
    return Organization.objects.create(name="Test Firm")


@pytest.fixture
def org2(db):
    return Organization.objects.create(name="Other Firm")


@pytest.fixture
def user_with_org(db, org):
    user = User.objects.create_user(username="tester", password="test1234")
    Membership.objects.create(user=user, organization=org, role="owner")
    return user


@pytest.fixture
def user_with_org2(db, org2):
    user = User.objects.create_user(username="tester2", password="test1234")
    Membership.objects.create(user=user, organization=org2)
    return user


@pytest.fixture
def auth_client(user_with_org):
    c = TestClient()
    c.login(username="tester", password="test1234")
    return c


@pytest.fixture
def auth_client2(user_with_org2):
    c = TestClient()
    c.login(username="tester2", password="test1234")
    return c


@pytest.fixture
def client_obj(org):
    return Client.objects.create(
        name="Acme Corp",
        industry="IT",
        size="대기업",
        region="Seoul",
        organization=org,
    )


@pytest.fixture
def client_obj2(org2):
    return Client.objects.create(
        name="Other Corp",
        industry="Finance",
        organization=org2,
    )


# --- Login Required ---


class TestLoginRequired:
    @pytest.mark.django_db
    def test_list_requires_login(self):
        c = TestClient()
        resp = c.get("/clients/")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    @pytest.mark.django_db
    def test_create_requires_login(self):
        c = TestClient()
        resp = c.get("/clients/new/")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    @pytest.mark.django_db
    def test_detail_requires_login(self, client_obj):
        c = TestClient()
        resp = c.get(f"/clients/{client_obj.pk}/")
        assert resp.status_code == 302

    @pytest.mark.django_db
    def test_update_requires_login(self, client_obj):
        c = TestClient()
        resp = c.get(f"/clients/{client_obj.pk}/edit/")
        assert resp.status_code == 302

    @pytest.mark.django_db
    def test_delete_requires_login(self, client_obj):
        c = TestClient()
        resp = c.post(f"/clients/{client_obj.pk}/delete/")
        assert resp.status_code == 302


# --- Client CRUD ---


class TestClientCRUD:
    @pytest.mark.django_db
    def test_list_page_renders(self, auth_client):
        resp = auth_client.get("/clients/")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_list_shows_own_clients(self, auth_client, client_obj):
        resp = auth_client.get("/clients/")
        assert resp.status_code == 200
        assert "Acme Corp" in resp.content.decode()

    @pytest.mark.django_db
    def test_create_client(self, auth_client, org):
        resp = auth_client.post(
            "/clients/new/",
            {
                "name": "New Client",
                "industry": "Tech",
                "size": "스타트업",
                "region": "Busan",
                "notes": "Test notes",
                "contact_persons_json": "[]",
            },
        )
        assert resp.status_code == 302  # redirect to detail
        assert Client.objects.filter(name="New Client", organization=org).exists()

    @pytest.mark.django_db
    def test_create_client_with_contact_persons(self, auth_client, org):
        persons = [
            {"name": "Kim", "position": "CTO", "phone": "010-1234", "email": "k@e.com"}
        ]
        resp = auth_client.post(
            "/clients/new/",
            {
                "name": "Contact Test",
                "contact_persons_json": json.dumps(persons),
            },
        )
        assert resp.status_code == 302
        client = Client.objects.get(name="Contact Test")
        assert len(client.contact_persons) == 1
        assert client.contact_persons[0]["name"] == "Kim"

    @pytest.mark.django_db
    def test_detail_page_renders(self, auth_client, client_obj):
        resp = auth_client.get(f"/clients/{client_obj.pk}/")
        assert resp.status_code == 200
        assert "Acme Corp" in resp.content.decode()

    @pytest.mark.django_db
    def test_update_client(self, auth_client, client_obj):
        resp = auth_client.post(
            f"/clients/{client_obj.pk}/edit/",
            {
                "name": "Acme Updated",
                "industry": "IT",
                "size": "대기업",
                "region": "Seoul",
                "notes": "",
                "contact_persons_json": "[]",
            },
        )
        assert resp.status_code == 302
        client_obj.refresh_from_db()
        assert client_obj.name == "Acme Updated"

    @pytest.mark.django_db
    def test_delete_client(self, auth_client, client_obj):
        pk = client_obj.pk
        resp = auth_client.post(f"/clients/{pk}/delete/")
        assert resp.status_code == 302
        assert not Client.objects.filter(pk=pk).exists()

    @pytest.mark.django_db
    def test_delete_only_post(self, auth_client, client_obj):
        resp = auth_client.get(f"/clients/{client_obj.pk}/delete/")
        assert resp.status_code == 405


# --- Organization Isolation ---


class TestOrganizationIsolation:
    @pytest.mark.django_db
    def test_cannot_see_other_org_clients(self, auth_client, client_obj2):
        resp = auth_client.get("/clients/")
        assert "Other Corp" not in resp.content.decode()

    @pytest.mark.django_db
    def test_cannot_access_other_org_client_detail(self, auth_client, client_obj2):
        resp = auth_client.get(f"/clients/{client_obj2.pk}/")
        assert resp.status_code == 404

    @pytest.mark.django_db
    def test_cannot_update_other_org_client(self, auth_client, client_obj2):
        resp = auth_client.post(
            f"/clients/{client_obj2.pk}/edit/",
            {"name": "Hacked", "contact_persons_json": "[]"},
        )
        assert resp.status_code == 404

    @pytest.mark.django_db
    def test_cannot_delete_other_org_client(self, auth_client, client_obj2):
        resp = auth_client.post(f"/clients/{client_obj2.pk}/delete/")
        assert resp.status_code == 404


# --- Search ---


class TestSearch:
    @pytest.mark.django_db
    def test_search_by_name(self, auth_client, client_obj):
        resp = auth_client.get("/clients/?q=Acme")
        assert resp.status_code == 200
        assert "Acme Corp" in resp.content.decode()

    @pytest.mark.django_db
    def test_search_by_industry(self, auth_client, client_obj):
        resp = auth_client.get("/clients/?q=IT")
        assert resp.status_code == 200
        assert "Acme Corp" in resp.content.decode()

    @pytest.mark.django_db
    def test_search_no_results(self, auth_client, client_obj):
        resp = auth_client.get("/clients/?q=nonexistent")
        assert resp.status_code == 200
        assert "Acme Corp" not in resp.content.decode()


# --- Contact Persons ---


class TestContactPersons:
    @pytest.mark.django_db
    def test_contact_persons_saved_and_displayed(self, auth_client, org):
        persons = [
            {"name": "Park", "position": "HR", "phone": "010-9999", "email": "p@e.com"},
            {"name": "Lee", "position": "CEO", "phone": "010-8888", "email": "l@e.com"},
        ]
        auth_client.post(
            "/clients/new/",
            {
                "name": "CP Test",
                "contact_persons_json": json.dumps(persons),
            },
        )
        client = Client.objects.get(name="CP Test")
        assert len(client.contact_persons) == 2
        assert client.contact_persons[0]["name"] == "Park"
        assert client.contact_persons[1]["name"] == "Lee"

        # Check detail page shows them
        resp = auth_client.get(f"/clients/{client.pk}/")
        content = resp.content.decode()
        assert "Park" in content
        assert "Lee" in content


# --- Delete Protection ---


class TestDeleteProtection:
    @pytest.mark.django_db
    def test_cannot_delete_with_active_project(
        self, auth_client, client_obj, user_with_org, org
    ):
        Project.objects.create(
            client=client_obj,
            organization=org,
            title="Active Project",
            status="searching",
            created_by=user_with_org,
        )
        resp = auth_client.post(f"/clients/{client_obj.pk}/delete/")
        # Should NOT redirect (client not deleted), render detail with error
        assert resp.status_code == 200
        assert Client.objects.filter(pk=client_obj.pk).exists()
        assert "진행중인 프로젝트가 있어 삭제할 수 없습니다" in resp.content.decode()

    @pytest.mark.django_db
    def test_can_delete_with_closed_project(
        self, auth_client, client_obj, user_with_org, org
    ):
        Project.objects.create(
            client=client_obj,
            organization=org,
            title="Closed Project",
            status="closed_success",
            created_by=user_with_org,
        )
        resp = auth_client.post(f"/clients/{client_obj.pk}/delete/")
        assert resp.status_code == 302
        assert not Client.objects.filter(pk=client_obj.pk).exists()

    @pytest.mark.django_db
    def test_can_delete_with_on_hold_project(
        self, auth_client, client_obj, user_with_org, org
    ):
        Project.objects.create(
            client=client_obj,
            organization=org,
            title="On Hold Project",
            status="on_hold",
            created_by=user_with_org,
        )
        resp = auth_client.post(f"/clients/{client_obj.pk}/delete/")
        assert resp.status_code == 302
        assert not Client.objects.filter(pk=client_obj.pk).exists()


# --- HTMX navigation ---


class TestHTMXNavigation:
    @pytest.mark.django_db
    def test_list_htmx_renders_partial(self, auth_client):
        resp = auth_client.get(
            "/clients/",
            HTTP_HX_REQUEST="true",
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        # Should not contain full HTML page (no <!DOCTYPE)
        assert "<!DOCTYPE" not in content

    @pytest.mark.django_db
    def test_list_full_page_renders(self, auth_client):
        resp = auth_client.get("/clients/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "<!DOCTYPE" in content


# --- Contract Inline CRUD ---


class TestContractCRUD:
    @pytest.mark.django_db
    def test_create_contract(self, auth_client, client_obj):
        resp = auth_client.post(
            f"/clients/{client_obj.pk}/contracts/new/",
            {
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "status": "체결",
                "terms": "Standard terms",
            },
        )
        assert resp.status_code == 200  # returns partial
        assert Contract.objects.filter(client=client_obj).exists()
        contract = Contract.objects.get(client=client_obj)
        assert contract.status == "체결"

    @pytest.mark.django_db
    def test_update_contract(self, auth_client, client_obj):
        contract = Contract.objects.create(
            client=client_obj,
            start_date="2026-01-01",
            status="협의중",
        )
        resp = auth_client.post(
            f"/clients/{client_obj.pk}/contracts/{contract.pk}/edit/",
            {
                "start_date": "2026-02-01",
                "status": "체결",
                "terms": "Updated terms",
            },
        )
        assert resp.status_code == 200
        contract.refresh_from_db()
        assert contract.status == "체결"
        assert contract.terms == "Updated terms"

    @pytest.mark.django_db
    def test_delete_contract(self, auth_client, client_obj):
        contract = Contract.objects.create(
            client=client_obj,
            start_date="2026-01-01",
            status="만료",
        )
        pk = contract.pk
        resp = auth_client.post(
            f"/clients/{client_obj.pk}/contracts/{pk}/delete/",
        )
        assert resp.status_code == 200
        assert not Contract.objects.filter(pk=pk).exists()

    @pytest.mark.django_db
    def test_contract_delete_only_post(self, auth_client, client_obj):
        contract = Contract.objects.create(
            client=client_obj,
            start_date="2026-01-01",
        )
        resp = auth_client.get(
            f"/clients/{client_obj.pk}/contracts/{contract.pk}/delete/",
        )
        assert resp.status_code == 405

    @pytest.mark.django_db
    def test_contract_isolation(self, auth_client, client_obj2):
        """Cannot create contracts on other org's clients."""
        resp = auth_client.post(
            f"/clients/{client_obj2.pk}/contracts/new/",
            {"start_date": "2026-01-01", "status": "체결"},
        )
        assert resp.status_code == 404

    @pytest.mark.django_db
    def test_detail_shows_contracts(self, auth_client, client_obj):
        Contract.objects.create(
            client=client_obj,
            start_date="2026-01-01",
            end_date="2026-12-31",
            status="체결",
            terms="Annual contract",
        )
        resp = auth_client.get(f"/clients/{client_obj.pk}/")
        content = resp.content.decode()
        assert "계약 이력" in content
        assert "2026" in content

    @pytest.mark.django_db
    def test_detail_shows_active_projects(
        self, auth_client, client_obj, user_with_org, org
    ):
        Project.objects.create(
            client=client_obj,
            organization=org,
            title="Dev Hire",
            status="searching",
            created_by=user_with_org,
        )
        resp = auth_client.get(f"/clients/{client_obj.pk}/")
        content = resp.content.decode()
        assert "Dev Hire" in content

    @pytest.mark.django_db
    def test_detail_hides_closed_projects(
        self, auth_client, client_obj, user_with_org, org
    ):
        Project.objects.create(
            client=client_obj,
            organization=org,
            title="Closed Hire",
            status="closed_success",
            created_by=user_with_org,
        )
        resp = auth_client.get(f"/clients/{client_obj.pk}/")
        content = resp.content.decode()
        assert "Closed Hire" not in content
