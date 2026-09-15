import os

from django.core.exceptions import ImproperlyConfigured

TEST_SECRET_KEY_PREFIX = "skey_test_"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


def require_test_secret_key(key: str | None) -> str:
    """Refuse to start unless the Omise secret key is a test key (spec §4).

    The message never includes the key itself, so a pasted live key does not end up in logs.
    """
    if not key or not key.startswith(TEST_SECRET_KEY_PREFIX):
        raise ImproperlyConfigured(
            "OMISE_SECRET_KEY must be an Omise test key (skey_test_...). "
            "Live keys are not allowed in this project."
        )
    return key
