"""
Development Django settings for Sugna Enterprise Suite.

Keep defaults permissive so local dev works without extra configuration.
"""

from __future__ import annotations

import os

from .base import *  # noqa: F403
from .base import build_databases


DEBUG = os.environ.get("DEBUG", "true").lower() in ("true", "1", "yes")

# Auto-run migrate on tenant DB when views detect missing migrations (same idea as sugna_core.settings).
_tam = os.environ.get("TENANT_AUTO_MIGRATE", "").strip().lower()
if _tam in ("true", "1", "yes"):
    TENANT_AUTO_MIGRATE = True
elif _tam in ("false", "0", "no"):
    TENANT_AUTO_MIGRATE = False
else:
    TENANT_AUTO_MIGRATE = DEBUG

SECRET_KEY = (
    os.environ.get("DJANGO_SECRET_KEY")
    or os.environ.get("SECRET_KEY")
    or "django-insecure-dev-only-change-in-production"
)

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "*").split(",") if h.strip()]

if os.environ.get("CSRF_TRUSTED_ORIGINS"):
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ["CSRF_TRUSTED_ORIGINS"].split(",") if o.strip()]


# Development DB config:
# - keep backward compatible fallback password so `python manage.py runserver` works
#   even if you didn't export/load a .env file.
DATABASES = build_databases(db_password_default="@@Hooyomacaan143", default_extra_tenants=True)

