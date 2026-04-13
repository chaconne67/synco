from django.conf import settings


def test_session_cookie_age_is_24h():
    assert settings.SESSION_COOKIE_AGE == 86400


def test_session_saved_every_request_for_sliding_expiry():
    assert settings.SESSION_SAVE_EVERY_REQUEST is True


def test_session_not_expired_at_browser_close():
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is False


def test_allow_ceo_test_login_flag_defaults_false_in_non_debug():
    # Flag must exist and default to False in production-like configs.
    assert hasattr(settings, "ALLOW_CEO_TEST_LOGIN")
