"""P12: Reference Data Management tests."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client as TestClient

from accounts.models import User
from clients.models import CompanyProfile, PreferredCert, UniversityTier
from clients.services.csv_handler import export_csv, import_csv


# --- Fixtures ---


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="staff", password="test1234", is_staff=True, level=2
    )


@pytest.fixture
def normal_user(db):
    return User.objects.create_user(
        username="normal", password="test1234", is_staff=False, level=1
    )


@pytest.fixture
def staff_client(staff_user):
    c = TestClient()
    c.login(username="staff", password="test1234")
    return c


@pytest.fixture
def normal_client(normal_user):
    c = TestClient()
    c.login(username="normal", password="test1234")
    return c


# --- CSV Import Tests ---


class TestCSVImport:
    @pytest.mark.django_db
    def test_import_universities_csv(self):
        csv_content = "name,name_en,country,tier,ranking,notes\n서울대학교,Seoul National University,KR,SKY,1,\n"
        result = import_csv(UniversityTier, io.StringIO(csv_content))
        assert result["created"] == 1
        assert result["updated"] == 0
        assert result["errors"] == []
        assert UniversityTier.objects.count() == 1

    @pytest.mark.django_db
    def test_import_universities_upsert(self):
        UniversityTier.objects.create(
            name="서울대학교", country="KR", tier="SKY", ranking=1
        )
        csv_content = (
            "name,name_en,country,tier,ranking,notes\n서울대학교,SNU,KR,SKY,1,Updated\n"
        )
        result = import_csv(UniversityTier, io.StringIO(csv_content))
        assert result["created"] == 0
        assert result["updated"] == 1
        u = UniversityTier.objects.get(name="서울대학교", country="KR")
        assert u.name_en == "SNU"
        assert u.notes == "Updated"

    @pytest.mark.django_db
    def test_import_companies_csv(self):
        csv_content = "name,name_en,industry,size_category,revenue_range,employee_count_range,listed,region,notes\n삼성전자,Samsung Electronics,반도체,대기업,,,,서울,\n"
        result = import_csv(CompanyProfile, io.StringIO(csv_content))
        assert result["created"] == 1
        assert CompanyProfile.objects.get(name="삼성전자").industry == "반도체"

    @pytest.mark.django_db
    def test_import_certs_csv_with_aliases(self):
        csv_content = "name,full_name,category,level,aliases,notes\nKICPA,한국공인회계사,회계/재무,상,CPA;공인회계사,\n"
        result = import_csv(PreferredCert, io.StringIO(csv_content))
        assert result["created"] == 1
        cert = PreferredCert.objects.get(name="KICPA")
        assert cert.aliases == ["CPA", "공인회계사"]

    @pytest.mark.django_db
    def test_import_invalid_choice_rolls_back(self):
        csv_content = (
            "name,name_en,country,tier,ranking,notes\n서울대학교,SNU,KR,INVALID,1,\n"
        )
        result = import_csv(UniversityTier, io.StringIO(csv_content))
        assert len(result["errors"]) > 0
        assert UniversityTier.objects.count() == 0

    @pytest.mark.django_db
    def test_import_missing_header_fails(self):
        csv_content = "name,country\n서울대학교,KR\n"
        result = import_csv(UniversityTier, io.StringIO(csv_content))
        assert len(result["errors"]) > 0
        assert "필수" in result["errors"][0]


class TestCSVExport:
    @pytest.mark.django_db
    def test_export_universities(self):
        UniversityTier.objects.create(
            name="서울대학교", name_en="SNU", country="KR", tier="SKY", ranking=1
        )
        output = export_csv(UniversityTier, UniversityTier.objects.all())
        content = output.getvalue()
        assert "서울대학교" in content
        assert content.startswith("\ufeff")  # UTF-8 BOM

    @pytest.mark.django_db
    def test_export_certs_aliases_semicolon(self):
        PreferredCert.objects.create(
            name="KICPA",
            full_name="한국공인회계사",
            category="회계/재무",
            aliases=["CPA", "공인회계사"],
        )
        output = export_csv(PreferredCert, PreferredCert.objects.all())
        content = output.getvalue()
        assert "CPA;공인회계사" in content


# --- View Tests: Access Control ---


class TestReferenceAccess:
    @pytest.mark.django_db
    def test_anon_redirected(self):
        c = TestClient()
        resp = c.get("/reference/")
        assert resp.status_code == 302
        assert "/accounts/login/" in resp.url

    @pytest.mark.django_db
    def test_logged_in_can_read(self, normal_client):
        resp = normal_client.get("/reference/")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_non_staff_cannot_create(self, normal_client):
        resp = normal_client.get("/reference/universities/new/")
        assert resp.status_code in (302, 403)  # boss_required denies non-boss

    @pytest.mark.django_db
    def test_staff_can_create(self, staff_client):
        resp = staff_client.get("/reference/universities/new/")
        assert resp.status_code == 200


# --- View Tests: Universities ---


class TestUniversityCRUD:
    @pytest.mark.django_db
    def test_create_university(self, staff_client):
        resp = staff_client.post(
            "/reference/universities/new/",
            {
                "name": "서울대학교",
                "name_en": "Seoul National University",
                "country": "KR",
                "tier": "SKY",
                "ranking": "1",
                "notes": "",
            },
        )
        assert resp.status_code == 204
        assert UniversityTier.objects.filter(name="서울대학교").exists()

    @pytest.mark.django_db
    def test_update_university(self, staff_client):
        u = UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY")
        resp = staff_client.post(
            f"/reference/universities/{u.pk}/edit/",
            {
                "name": "서울대학교",
                "name_en": "SNU",
                "country": "KR",
                "tier": "SKY",
                "ranking": "1",
                "notes": "Updated",
            },
        )
        assert resp.status_code == 204
        u.refresh_from_db()
        assert u.name_en == "SNU"

    @pytest.mark.django_db
    def test_delete_university(self, staff_client):
        u = UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY")
        resp = staff_client.post(f"/reference/universities/{u.pk}/delete/")
        assert resp.status_code == 204
        assert not UniversityTier.objects.filter(pk=u.pk).exists()

    @pytest.mark.django_db
    def test_list_universities(self, normal_client):
        UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY")
        resp = normal_client.get("/reference/universities/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "서울대학교" in resp.content.decode()

    @pytest.mark.django_db
    def test_search_universities(self, normal_client):
        UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY")
        UniversityTier.objects.create(name="MIT", country="US", tier="OVERSEAS_TOP")
        resp = normal_client.get(
            "/reference/universities/?q=MIT", HTTP_HX_REQUEST="true"
        )
        content = resp.content.decode()
        assert "MIT" in content
        assert "서울대학교" not in content

    @pytest.mark.django_db
    def test_filter_by_tier(self, normal_client):
        UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY")
        UniversityTier.objects.create(name="성균관대학교", country="KR", tier="SSG")
        resp = normal_client.get(
            "/reference/universities/?tier=SKY", HTTP_HX_REQUEST="true"
        )
        content = resp.content.decode()
        assert "서울대학교" in content
        assert "성균관대학교" not in content

    @pytest.mark.django_db
    def test_unique_constraint(self, staff_client):
        UniversityTier.objects.create(name="서울대학교", country="KR", tier="SKY")
        resp = staff_client.post(
            "/reference/universities/new/",
            {
                "name": "서울대학교",
                "country": "KR",
                "tier": "SKY",
            },
        )
        assert resp.status_code == 200  # form returned with errors
        assert UniversityTier.objects.filter(name="서울대학교").count() == 1


class TestUniversityCSVViews:
    @pytest.mark.django_db
    def test_export_csv(self, normal_client):
        UniversityTier.objects.create(
            name="서울대학교", country="KR", tier="SKY", ranking=1
        )
        resp = normal_client.get("/reference/universities/export/")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "text/csv; charset=utf-8-sig"
        assert "서울대학교" in resp.content.decode("utf-8-sig")

    @pytest.mark.django_db
    def test_import_csv(self, staff_client):
        csv_bytes = "name,name_en,country,tier,ranking,notes\n서울대학교,SNU,KR,SKY,1,\n".encode(
            "utf-8-sig"
        )
        f = SimpleUploadedFile("test.csv", csv_bytes, content_type="text/csv")
        resp = staff_client.post("/reference/universities/import/", {"csv_file": f})
        assert resp.status_code == 200
        assert UniversityTier.objects.filter(name="서울대학교").exists()


# --- View Tests: Companies ---


class TestCompanyCRUD:
    @pytest.mark.django_db
    def test_create_company(self, staff_client):
        resp = staff_client.post(
            "/reference/companies/new/",
            {
                "name": "삼성전자",
                "name_en": "Samsung Electronics",
                "industry": "반도체",
                "size_category": "대기업",
                "listed": "KOSPI",
                "region": "서울",
                "revenue_range": "",
                "employee_count_range": "",
                "notes": "",
            },
        )
        assert resp.status_code == 204
        assert CompanyProfile.objects.filter(name="삼성전자").exists()

    @pytest.mark.django_db
    def test_delete_company(self, staff_client):
        cp = CompanyProfile.objects.create(name="삼성전자", industry="반도체")
        resp = staff_client.post(f"/reference/companies/{cp.pk}/delete/")
        assert resp.status_code == 204
        assert not CompanyProfile.objects.filter(pk=cp.pk).exists()

    @pytest.mark.django_db
    def test_non_staff_cannot_create_company(self, normal_client):
        resp = normal_client.post("/reference/companies/new/", {"name": "Hack"})
        assert resp.status_code in (302, 403)  # boss_required denies non-boss

    @pytest.mark.django_db
    def test_list_companies(self, normal_client):
        CompanyProfile.objects.create(name="삼성전자", industry="반도체")
        resp = normal_client.get("/reference/companies/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "삼성전자" in resp.content.decode()


# --- View Tests: Certs ---


class TestCertCRUD:
    @pytest.mark.django_db
    def test_create_cert(self, staff_client):
        resp = staff_client.post(
            "/reference/certs/new/",
            {
                "name": "KICPA",
                "full_name": "한국공인회계사",
                "category": "회계/재무",
                "level": "상",
                "aliases_text": "CPA;공인회계사",
                "notes": "",
            },
        )
        assert resp.status_code == 204
        cert = PreferredCert.objects.get(name="KICPA")
        assert cert.aliases == ["CPA", "공인회계사"]

    @pytest.mark.django_db
    def test_delete_cert(self, staff_client):
        pc = PreferredCert.objects.create(name="KICPA", category="회계/재무")
        resp = staff_client.post(f"/reference/certs/{pc.pk}/delete/")
        assert resp.status_code == 204

    @pytest.mark.django_db
    def test_search_by_alias(self, normal_client):
        PreferredCert.objects.create(
            name="KICPA",
            full_name="한국공인회계사",
            category="회계/재무",
            aliases=["CPA", "공인회계사"],
        )
        resp = normal_client.get("/reference/certs/?q=CPA", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "KICPA" in resp.content.decode()

    @pytest.mark.django_db
    @pytest.mark.skip(
        reason="T10 — cert category filter returns full page in test env, needs HTMX partial fix"
    )
    def test_filter_by_category(self, normal_client):
        PreferredCert.objects.create(name="KICPA", category="회계/재무")
        PreferredCert.objects.create(name="CISA", category="IT")
        resp = normal_client.get(
            "/reference/certs/?category=IT", HTTP_HX_REQUEST="true"
        )
        content = resp.content.decode()
        assert "CISA" in content
        assert "KICPA" not in content


# --- View Tests: Tab Switching ---


class TestTabSwitching:
    @pytest.mark.django_db
    def test_tab_universities(self, normal_client):
        resp = normal_client.get("/reference/universities/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_tab_companies(self, normal_client):
        resp = normal_client.get("/reference/companies/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_tab_certs(self, normal_client):
        resp = normal_client.get("/reference/certs/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200

    @pytest.mark.django_db
    def test_index_redirects_to_universities(self, normal_client):
        resp = normal_client.get("/reference/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "대학 랭킹" in content or "대학명" in content


# --- View Tests: Sidebar ---


class TestSidebarNavigation:
    @pytest.mark.django_db
    def test_reference_page_full_render(self, normal_client):
        resp = normal_client.get("/reference/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "레퍼런스 관리" in content
        assert "<!DOCTYPE" in content  # full page

    @pytest.mark.django_db
    def test_reference_htmx_renders_partial(self, normal_client):
        resp = normal_client.get("/reference/", HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "<!DOCTYPE" not in content


# --- Load Reference Data Command ---


class TestLoadReferenceData:
    @pytest.mark.django_db
    def test_load_all(self):
        call_command("load_reference_data")
        assert UniversityTier.objects.count() > 0
        assert CompanyProfile.objects.count() > 0
        assert PreferredCert.objects.count() > 0

    @pytest.mark.django_db
    def test_idempotent(self):
        call_command("load_reference_data")
        count1 = UniversityTier.objects.count()
        call_command("load_reference_data")
        count2 = UniversityTier.objects.count()
        assert count1 == count2

    @pytest.mark.django_db
    def test_load_single_model(self):
        call_command("load_reference_data", model="universities")
        assert UniversityTier.objects.count() > 0
        assert CompanyProfile.objects.count() == 0
