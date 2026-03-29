import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-rtn5-85r@b0w9q2(05xo#5$1_79w(jsjv7stx_@^$t*j9mpj9&",
)

DEBUG = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.environ.get(
    "ALLOWED_HOSTS", "49.247.46.171,localhost,127.0.0.1,synco.kr"
).split(",")

CSRF_TRUSTED_ORIGINS = os.environ.get(
    "CSRF_TRUSTED_ORIGINS", "https://synco.kr,https://www.synco.kr"
).split(",")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "django_htmx",
    "widget_tweaks",
    # Local
    "accounts",
    "contacts",
    "meetings",
    "intelligence",
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
            ],
        },
    },
]

WSGI_APPLICATION = "main.wsgi.application"


# Database

DATABASES = {
    "default": dj_database_url.config(
        default="sqlite:///db.sqlite3",
        conn_max_age=600,
    )
}


# Auth

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "/accounts/login/"

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

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
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
