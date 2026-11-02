"""Settings used by pytest: fast, isolated, no external services."""

from .base import *  # noqa: F403

SECRET_KEY = "test-secret-key"
DEBUG = False

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

# Fast hasher; never use outside tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Throttling is covered by its own test; keep it out of the way elsewhere.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {"anon": "10000/min", "user": "10000/min", "login": "10000/min"},
}
