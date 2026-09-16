"""Django settings for the payment demo backend (spec §4, §7)."""

import os
from pathlib import Path

from dotenv import load_dotenv

from config.guards import require_env, require_test_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent

# Real environment variables win over .env values.
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = require_env("DJANGO_SECRET_KEY")
DEBUG = os.environ.get("DEBUG", "False").strip().lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

# Omise, test mode only. The guard runs on every startup, including manage.py commands.
OMISE_SECRET_KEY = require_test_secret_key(os.environ.get("OMISE_SECRET_KEY"))
OMISE_API_BASE = os.environ.get("OMISE_API_BASE", "https://api.omise.co").rstrip("/")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")

# Testing only (spec §13.2): shorten the PromptPay QR lifetime so the expiry case can be
# tried without waiting 24 hours. Unset means Omise's own default of 24 hours.
_promptpay_expiry = os.environ.get("PROMPTPAY_EXPIRES_IN_SECONDS", "").strip()
PROMPTPAY_EXPIRES_IN_SECONDS = int(_promptpay_expiry) if _promptpay_expiry else None

# No login, sessions or admin (spec §1), so the contrib apps are left out.
INSTALLED_APPS = [
    "corsheaders",
    "rest_framework",
    "payments",
]

# No session or cookie auth, so there is nothing for CSRF middleware to protect (spec §7).
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL runs in Docker (docker-compose.yml). docker compose reads the same .env file,
# so the container and Django always share one set of credentials.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": require_env("POSTGRES_DB"),
        "USER": require_env("POSTGRES_USER"),
        "PASSWORD": require_env("POSTGRES_PASSWORD"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

# Blocks real Omise calls during tests (see config/test_runner.py).
TEST_RUNNER = "config.test_runner.NoNetworkTestRunner"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Spec §14 rule 14: only the frontend may call the API from a browser.
CORS_ALLOWED_ORIGINS = [FRONTEND_URL]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    # django.contrib.auth is not installed, so there is no AnonymousUser.
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "payments.exceptions.api_exception_handler",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "loggers": {
        "payments": {"handlers": ["console"], "level": "INFO"},
    },
}
