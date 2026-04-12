import pytest
from django.test import Client as TestClient
from django.contrib.auth import get_user_model

from accounts.models import Membership, Organization

User = get_user_model()


@pytest.fixture
def active_user(db):
    org = Organization.objects.create(name="Test Org")
    user = User.objects.create_user(username="emailuser", password="pass")
    Membership.objects.create(user=user, organization=org, status="active")
    return user


@pytest.mark.django_db
class TestEmailDisconnect:
    """Verify email_disconnect redirects to settings_email tab."""

    def test_disconnect_redirects_to_settings_email(self, active_user):
        """email_disconnect should redirect to /accounts/settings/email/."""
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/email/disconnect/")
        assert response.status_code == 302
        assert response.url == "/accounts/settings/email/"


@pytest.mark.django_db
class TestLegacyEmailSettings:
    """Verify legacy email_settings page backward compatibility."""

    def test_legacy_email_settings_returns_full_page(self, active_user):
        """GET /accounts/email/settings/ returns email_settings.html (full page)."""
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/email/settings/")
        assert response.status_code == 200
        assert "accounts/email_settings.html" in [t.name for t in response.templates]

    def test_legacy_email_settings_post_returns_full_page(self, active_user):
        """POST to legacy email_settings returns full page (not partial)."""
        client = TestClient()
        client.force_login(active_user)
        response = client.post(
            "/accounts/email/settings/",
            {"filter_from": "test@example.com", "is_active": "on"},
        )
        assert response.status_code == 200
        assert "accounts/email_settings.html" in [t.name for t in response.templates]


@pytest.mark.django_db
class TestSettingsEmailHTMX:
    """Verify settings_email tab handles HTMX POST with partial response."""

    def test_settings_email_htmx_post_returns_partial(self, active_user):
        """HTMX POST to settings_email returns partial template."""
        from accounts.models import EmailMonitorConfig

        EmailMonitorConfig.objects.create(
            user=active_user,
            gmail_credentials=b"",
            is_active=True,
        )
        client = TestClient()
        client.force_login(active_user)
        response = client.post(
            "/accounts/settings/email/",
            {"filter_from": "test@example.com", "is_active": "on"},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="settings-content",
        )
        assert response.status_code == 200
        assert "accounts/partials/settings_email.html" in [
            t.name for t in response.templates
        ]
        content = response.content.decode()
        assert "<html" not in content

    def test_settings_email_full_page_get(self, active_user):
        """Full page GET to settings_email renders settings.html shell."""
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/email/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]
