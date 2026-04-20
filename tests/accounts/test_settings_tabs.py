import pytest
from django.test import Client as TestClient
from django.contrib.auth import get_user_model


User = get_user_model()


@pytest.fixture
def active_user(db):
    user = User.objects.create_user(username="tabuser", password="pass")
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
    def test_profile_full_page_renders_tab_bar(self, active_user):
        """Full page request renders settings.html with tab bar."""
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/profile/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]
        assert "accounts/partials/settings_tab_bar.html" in [
            t.name for t in response.templates
        ]
        content = response.content.decode()
        # Tab bar buttons present
        assert "프로필" in content
        assert "이메일" in content
        assert "텔레그램" in content
        assert "알림" in content
        # Profile content present
        assert "내 정보" in content

    def test_profile_htmx_main_entry_includes_tab_bar(self, active_user):
        """HTMX request to #main-content includes tab bar (sidebar entry)."""
        client = TestClient()
        client.force_login(active_user)
        response = client.get(
            "/accounts/settings/profile/",
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="main-content",
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "프로필" in content
        assert "이메일" in content
        assert "settings-content" in content  # Container for tab content
        assert "<html" not in content  # No full page wrapper

    def test_profile_htmx_tab_switch_returns_partial_only(self, active_user):
        """HTMX request to #settings-content returns only profile partial."""
        client = TestClient()
        client.force_login(active_user)
        response = client.get(
            "/accounts/settings/profile/",
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="settings-content",
        )
        assert response.status_code == 200
        assert "accounts/partials/settings_content.html" in [
            t.name for t in response.templates
        ]
        content = response.content.decode()
        assert "내 정보" in content
        assert "<html" not in content
        # Should NOT contain tab bar (only partial)
        assert "settings_tab_bar" not in content


@pytest.mark.django_db
class TestSettingsEmailTab:
    def test_email_tab_returns_200_with_tab_bar(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/email/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]
        content = response.content.decode()
        assert "Gmail" in content or "이메일" in content


@pytest.mark.django_db
class TestSettingsTelegramTab:
    def test_telegram_tab_returns_200_with_tab_bar(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/telegram/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]
        content = response.content.decode()
        assert "텔레그램" in content


@pytest.mark.django_db
class TestSettingsNotifyTab:
    def test_notify_tab_returns_200_with_tab_bar(self, active_user):
        client = TestClient()
        client.force_login(active_user)
        response = client.get("/accounts/settings/notify/")
        assert response.status_code == 200
        assert "accounts/settings.html" in [t.name for t in response.templates]
        content = response.content.decode()
        assert "알림 설정" in content

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

    def test_notify_htmx_post_returns_partial(self, active_user):
        """HTMX POST returns only the notify partial, not full page."""
        client = TestClient()
        client.force_login(active_user)
        response = client.post(
            "/accounts/settings/notify/",
            {
                "contact_result_web": "on",
            },
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="settings-content",
        )
        assert response.status_code == 200
        assert "accounts/partials/settings_notify.html" in [
            t.name for t in response.templates
        ]
        content = response.content.decode()
        assert "알림 설정" in content
        assert "<html" not in content
