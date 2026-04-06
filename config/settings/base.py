"""
Shared Django settings for Sugna Enterprise Suite.

Environment-specific modules:
- config.settings.dev
- config.settings.prod
"""

from __future__ import annotations

from pathlib import Path
import os


# /app/config/settings/base.py -> /app
BASE_DIR = Path(__file__).resolve().parents[2]


INSTALLED_APPS = [
    # Third-party admin theme (must come before django.contrib.admin)
    "jazzmin",

    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",

    # Platform apps
    "tenants",
    "platform_dashboard",
    "platform_announcements",
    "platform_email_templates",
    "website",
    "help_center",

    # Tenant-scoped apps (routed to tenant DBs)
    "tenant_users",
    "rbac",
    "tenant_portal",
    "tenant_finance",
    "tenant_grants",
    "tenant_integrations",
    "tenant_audit_risk",
    "tenant_documents",  

    # Domain apps
    "diagnostics",
]


JAZZMIN_SETTINGS = {
    "site_title": "Sugna Enterprise Suite Admin",
    "site_header": "Sugna Enterprise Suite",
    "site_brand": "Sugna",
    "welcome_sign": "Welcome to Sugna Enterprise Suite",
    "show_ui_builder": False,
    # Brand assets (paths relative to STATIC_URL)
    "site_logo": "img/sugna-logo-dark.png",
    "login_logo": "img/sugna-logo-dark.png",
    "login_logo_dark": "img/sugna-logo-light.png",
    "custom_css": "css/sugna_admin.css",
}

JAZZMIN_UI_TWEAKS = {
    "theme": "flatly",
    "navbar": "navbar-light",
    "navbar_fixed": True,
    "footer_fixed": False,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-outline-secondary",
    },
}


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    # Resolve tenant by Host header (domain/subdomain)
    "sugna_core.middleware.TenantResolutionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Tenant-scoped RBAC context (permission cache)
    "tenant_portal.middleware_rbac.RBACContextMiddleware",
    "tenant_portal.middleware_erp_alerts.ErpAlertingMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "sugna_core.urls"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "platform_dashboard" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "tenant_portal.context_processors.org_settings",
                "tenant_portal.tenant_theme.tenant_theme",
                "tenant_portal.context_processors.tenant_entitlements",
                "tenant_portal.context_processors.hospital_workspace",
                "tenant_portal.context_processors.smart_alerts",
                "tenant_portal.context_processors.erp_alerting",
                "tenant_portal.context_processors.platform_announcements",
            ],
        },
    }
]


WSGI_APPLICATION = "sugna_core.wsgi.application"


# Database
# https://docs.djangoproject.com/en/stable/ref/settings/#databases
TENANT_APP_LABELS = (
    os.environ.get("TENANT_APP_LABELS", "").split(",")
    if os.environ.get("TENANT_APP_LABELS")
    else [
        "tenant_users",
        "rbac",
        "tenant_finance",
        "tenant_grants",
        "tenant_integrations",
        "tenant_audit_risk",
    ]
)
DATABASE_ROUTERS = ["sugna_core.db_router.TenantDatabaseRouter"]


def build_databases(*, db_password_default: str | None, default_extra_tenants: bool) -> dict:
    """
    Build DATABASES with:
    - db per tenant optional extras (wardi, hurdo) for dev
    - strict DB_PASSWORD requirement in prod
    """

    name = os.environ.get("DB_NAME", "sugna_enterprise_suite")
    user = os.environ.get("DB_USER", "postgres")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")

    password = os.environ.get("DB_PASSWORD", db_password_default)
    if not password:
        raise RuntimeError(
            "DB_PASSWORD is required. Set it in your environment or compose env-file (e.g. .env.prod)."
        )

    base_db = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": user,
        "PASSWORD": password,
        "HOST": host,
        "PORT": port,
    }

    databases: dict[str, dict] = {"default": base_db}

    # Optional dev tenant DBs (same host/user/password as default)
    extra_default_str = "true" if default_extra_tenants else "false"
    extra_flag = os.environ.get("DB_EXTRA_TENANTS", extra_default_str).lower() in ("true", "1", "yes")
    if extra_flag:
        for alias, db_name in [("wardi", "wardi_db"), ("hurdo", "hurdo_db")]:
            databases[alias] = {**base_db, "NAME": db_name}

    return databases


AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Media files (tenant uploads)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# Audit Screening Upload: temporary storage only (deleted after review/TTL)
SCREENING_UPLOAD_TEMP_ROOT = os.environ.get(
    "SCREENING_UPLOAD_TEMP_ROOT",
    str(BASE_DIR / "tmp" / "audit_screening"),
)
SCREENING_UPLOAD_MAX_AGE_HOURS = int(os.environ.get("SCREENING_UPLOAD_MAX_AGE_HOURS", "48"))
SCREENING_UPLOAD_MAX_FILE_SIZE_MB = int(os.environ.get("SCREENING_UPLOAD_MAX_FILE_SIZE_MB", "0"))
SCREENING_UPLOAD_MAX_SESSION_SIZE_MB = int(os.environ.get("SCREENING_UPLOAD_MAX_SESSION_SIZE_MB", "0"))

# Allow large request bodies for screening uploads
DATA_UPLOAD_MAX_MEMORY_SIZE = int(
    os.environ.get("DATA_UPLOAD_MAX_MEMORY_SIZE", str(1024 * 1024 * 1024))
)  # 1 GB default


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Website contact / demo forms: private inbox (set via environment — not shown in templates).
WEBSITE_INBOUND_EMAIL = os.environ.get("WEBSITE_INBOUND_EMAIL", "").strip()

_default_from = os.environ.get("DEFAULT_FROM_EMAIL", "").strip()
if _default_from:
    DEFAULT_FROM_EMAIL = _default_from
else:
    DEFAULT_FROM_EMAIL = "Sugna Enterprise Suite <webmaster@localhost>"

SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Outbound SMTP: set EMAIL_HOST (+ credentials) on production; without it, console backend logs only.
_email_host = os.environ.get("EMAIL_HOST", "").strip()
if _email_host:
    EMAIL_BACKEND = os.environ.get(
        "EMAIL_BACKEND",
        "django.core.mail.backends.smtp.EmailBackend",
    )
    EMAIL_HOST = _email_host
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() in ("true", "1", "yes")
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "").strip()
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
else:
    EMAIL_BACKEND = os.environ.get(
        "EMAIL_BACKEND",
        "django.core.mail.backends.console.EmailBackend",
    )


LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/platform/"


DIAGNOSTICS_AUTO_REMEDIATE = os.environ.get("DIAGNOSTICS_AUTO_REMEDIATE", "false").lower() in (
    "1",
    "true",
    "yes",
)

# Tenant HTTP auto-migrate (see tenant_portal.migration_checks). Overridden in dev.py / prod.py.
TENANT_AUTO_MIGRATE = False

