"""Local development settings."""

from decouple import config

from .base import *  # noqa: F403

DEBUG = config("DEBUG", default=True, cast=bool)
SECRET_KEY = config("SECRET_KEY", default="dev-only-insecure-key-do-not-use-in-production")
