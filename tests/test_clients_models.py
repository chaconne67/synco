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
