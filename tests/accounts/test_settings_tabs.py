import pytest
from django.test import Client as TestClient
from django.contrib.auth import get_user_model

from accounts.models import Membership, Organization

User = get_user_model()


@pytest.fixture
def active_user(db):
    org = Organization.objects.create(name="Test Org")
    user = User.objects.create_user(username="tabuser", password="pass")
    Membership.objects.create(user=user, organization=org, status="active")
    return user


@pytest.mark.django_db
class TestSettingsRedirect:
    def test_settings_redirects_to_profile(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/")
        assert response.status_code == 302
        assert response.url == "/accounts/settings/profile/"


@pytest.mark.django_db
class TestSettingsProfileTab:
    def test_profile_tab_returns_200(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/profile/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]

    def test_profile_tab_htmx_returns_partial(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get(
            "/accounts/settings/profile/",
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        assert "accounts/partials/settings_content.html" in [
            t.name for t in response.templates
        ]
        # HTMX partial should not contain full base layout
        content = response.content.decode()
        assert "<html" not in content


@pytest.mark.django_db
class TestSettingsEmailTab:
    def test_email_tab_returns_200(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/email/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]


@pytest.mark.django_db
class TestSettingsTelegramTab:
    def test_telegram_tab_returns_200(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/telegram/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]


@pytest.mark.django_db
class TestSettingsNotifyTab:
    def test_notify_tab_returns_200(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/notify/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]

    def test_notify_tab_post_saves_preferences(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.post(
            "/accounts/settings/notify/",
            {
                "contact_result_web": "on",
                "contact_result_telegram": "",
                "recommendation_feedback_web": "on",
                "recommendation_feedback_telegram": "on",
                "project_approval_web": "on",
                "project_approval_telegram": "",
                "newsfeed_update_web": "",
                "newsfeed_update_telegram": "",
            },
        )
        assert response.status_code == 200
        from accounts.models import NotificationPreference
        pref = NotificationPreference.objects.get(user=active_user)
        assert pref.preferences["contact_result"]["telegram"] is False
