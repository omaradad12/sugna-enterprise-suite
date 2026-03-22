"""
Production Django settings for Sugna Enterprise Suite.

These settings intentionally fail fast when required production secrets are missing.
"""

from __future__ import annotations

import os

from .base import *  # noqa: F403
from .base import build_databases


DEBUG = False


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY is required for production (set it in .env.prod).")


ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
if not ALLOWED_HOSTS or ALLOWED_HOSTS == ["*"]:
    raise RuntimeError("ALLOWED_HOSTS must be set to your domain(s) in .env.prod (not '*').")

# Always allow local access for Docker health checks / local curl debugging.
# Django will strip the port (e.g. "127.0.0.1:8000") during validation.
ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS + ["127.0.0.1", "localhost"]))


# HTTPS POSTs (e.g. platform tenant registration) fail CSRF checks if this is empty/mis-set.
# When unset, derive https://<host> for each concrete entry in ALLOWED_HOSTS (not wildcards).
_csrf_origins_env = (os.environ.get("CSRF_TRUSTED_ORIGINS") or "").strip()
if _csrf_origins_env:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins_env.split(",") if o.strip()]
else:
    CSRF_TRUSTED_ORIGINS = []
    for host in ALLOWED_HOSTS:
        if not host or host == "*" or "*" in host or host.startswith("."):
            continue
        CSRF_TRUSTED_ORIGINS.append(f"https://{host}")


# Security hardening: only intended to be enabled behind TLS-terminating reverse proxy (Nginx)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "false").lower() in ("true", "1", "yes")

# Default to disabled to avoid breaking deployments that are not yet behind HTTPS.
# Enable explicitly once TLS is correctly configured end-to-end.
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.environ.get("SECURE_HSTS_INCLUDE_SUBDOMAINS", "true").lower() in (
    "true",
    "1",
    "yes",
)
SECURE_HSTS_PRELOAD = os.environ.get("SECURE_HSTS_PRELOAD", "false").lower() in ("true", "1", "yes")

# Extra hardening headers (SecurityMiddleware covers many, but keep explicit for clarity)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
REFERRER_POLICY = "same-origin"

CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")


# Production DB config: require DB_PASSWORD, default no extra dev tenant DBs
DATABASES = build_databases(db_password_default=None, default_extra_tenants=False)


# Logging to Docker stdout/stderr
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "verbose"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}

