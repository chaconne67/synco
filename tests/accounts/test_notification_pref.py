import pytest
from django.contrib import admin
from django.db import IntegrityError

from accounts.models import NotificationPreference, _default_notification_preferences

User = __import__("django.contrib.auth", fromlist=["get_user_model"]).get_user_model()


@pytest.mark.django_db
class TestNotificationPreference:
    def test_create_default_preferences(self):
        user = User.objects.create_user(username="np1", password="pass")
        pref = NotificationPreference.objects.create(user=user)
        assert pref.preferences == _default_notification_preferences()

    def test_update_preferences(self):
        user = User.objects.create_user(username="np2", password="pass")
        pref = NotificationPreference.objects.create(user=user)
        pref.preferences["contact_result"]["telegram"] = False
        pref.save()
        pref.refresh_from_db()
        assert pref.preferences["contact_result"]["telegram"] is False

    def test_one_to_one_with_user(self):
        user = User.objects.create_user(username="np3", password="pass")
        NotificationPreference.objects.create(user=user)
        with pytest.raises(IntegrityError):
            NotificationPreference.objects.create(user=user)

    def test_get_or_create_defaults(self):
        user = User.objects.create_user(username="np4", password="pass")
        pref, created = NotificationPreference.objects.get_or_create(user=user)
        assert created is True
        assert pref.preferences == _default_notification_preferences()

    def test_admin_registered(self):
        assert NotificationPreference in admin.site._registry
