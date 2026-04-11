import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")
RUNNING_TESTS = "pytest" in sys.modules or any(
    arg in {"pytest", "test"} for arg in sys.argv
)

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-dev-only-key-not-for-production"
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY environment variable is required in production"
        )

ALLOWED_HOSTS = os.environ.get(
    "ALLOWED_HOSTS", "49.247.46.171,localhost,127.0.0.1,synco.kr"
).split(",")

CSRF_TRUSTED_ORIGINS = os.environ.get(
    "CSRF_TRUSTED_ORIGINS", "https://synco.kr,https://www.synco.kr"
).split(",")

# CSRF — make token available to JS via cookie
CSRF_COOKIE_HTTPONLY = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Third-party
    "django_htmx",
    "widget_tweaks",
    # Local
    "accounts",
    "candidates",
    "clients",
    "projects",
    "data_extraction",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "main.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "projects.context_processors.pending_approval_count",
                "projects.context_processors.has_new_news",
                "accounts.context_processors.membership",
            ],
        },
    },
]

WSGI_APPLICATION = "main.wsgi.application"


# Database

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
        )
    }
elif DEBUG:
    DATABASES = {
        "default": dj_database_url.parse(
            "sqlite:///db.sqlite3",
            conn_max_age=600,
        )
    }
else:
    raise ImproperlyConfigured(
        "DATABASE_URL environment variable is required in production"
    )


# Auth

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"

AUTHENTICATION_BACKENDS = [
    "accounts.backends.KakaoBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Kakao OAuth
KAKAO_CLIENT_ID = os.environ.get("KAKAO_CLIENT_ID", "")
KAKAO_CLIENT_SECRET = os.environ.get("KAKAO_CLIENT_SECRET", "")
KAKAO_REDIRECT_URI = os.environ.get("KAKAO_REDIRECT_URI", "")

# Gemini Embedding
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# OpenAI (Whisper API)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
SITE_URL = os.environ.get("SITE_URL", "https://synco.kr")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")

# Google Drive OAuth files
GOOGLE_TOKEN_PATH = os.environ.get(
    "GOOGLE_TOKEN_PATH", str(BASE_DIR / ".secrets" / "google_token.json")
)
GOOGLE_CLIENT_SECRET_PATH = os.environ.get(
    "GOOGLE_CLIENT_SECRET_PATH",
    str(BASE_DIR / ".secrets" / "client_secret.json"),
)


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization

LANGUAGE_CODE = "ko-kr"

TIME_ZONE = "Asia/Seoul"

USE_I18N = True

USE_TZ = True


# Static files

STATIC_URL = "/static/"

STATICFILES_DIRS = [BASE_DIR / "static"]

STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files (uploads)
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Cache (used for Telegram webhook dedup)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}


# Default primary key field type

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# LLM Provider Configuration
# Default: claude_cli (uses Claude Code subscription, no API key needed)
# Fallback chain: kimi > minimax (configured but not active until tested)
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "claude_cli")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

# Provider-specific configs (options ready for future testing)
LLM_PROVIDERS = {
    "claude_cli": {
        "model": "",
    },
    "kimi": {
        "base_url": os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1"),
        "model": os.environ.get("LLM_MODEL", "kimi-k2.5"),
    },
    "minimax": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": os.environ.get("LLM_MODEL", "minimax/minimax-m2.7"),
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": os.environ.get("LLM_MODEL", "anthropic/claude-sonnet-4"),
    },
}

# Production security settings
if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get(
        "SECURE_SSL_REDIRECT",
        "false" if RUNNING_TESTS else "true",
    ).lower() in ("true", "1", "yes")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Extension cross-origin cookie support (production only)
if os.environ.get("SYNCO_ENV") == "production":
    SESSION_COOKIE_SAMESITE = "None"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = "None"
    CSRF_COOKIE_SECURE = True
