import pytest

from clients.models import Client, IndustryCategory


@pytest.mark.django_db
def test_industry_category_has_11_choices():
    assert len(IndustryCategory.choices) == 11


@pytest.mark.django_db
def test_industry_category_values_include_expected():
    values = {c.value for c in IndustryCategory}
    assert "바이오/제약" in values
    assert "IT/SW" in values
    assert "기타" in values


@pytest.mark.django_db
def test_industry_category_enum_names_for_url_params():
    assert IndustryCategory["BIO_PHARMA"].value == "바이오/제약"
    assert IndustryCategory["IT_SW"].value == "IT/SW"
    assert IndustryCategory["ETC"].value == "기타"



@pytest.mark.django_db
def test_client_has_website_field(legacy_org):
    c = Client.objects.create(organization=legacy_org, name="X", website="https://example.com")
    c.refresh_from_db()
    assert c.website == "https://example.com"


@pytest.mark.django_db
def test_client_has_description_field(legacy_org):
    c = Client.objects.create(organization=legacy_org, name="X", description="desc")
    c.refresh_from_db()
    assert c.description == "desc"


@pytest.mark.django_db
def test_client_logo_upload_to_path(legacy_org):
    c = Client.objects.create(organization=legacy_org, name="X")
    field = c._meta.get_field("logo")
    assert field.upload_to == "clients/logos/"


@pytest.mark.django_db
def test_industry_default_is_etc(legacy_org):
    c = Client.objects.create(organization=legacy_org, name="X")
    assert c.industry == IndustryCategory.ETC.value


@pytest.mark.django_db
def test_industry_accepts_valid_category(legacy_org):
    c = Client.objects.create(
        organization=legacy_org, name="X", industry=IndustryCategory.BIO_PHARMA.value
    )
    c.refresh_from_db()
    assert c.industry == "바이오/제약"
