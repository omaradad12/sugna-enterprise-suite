"""
Compatibility settings module.

The project previously used a single `sugna_core/settings.py`.
We now split into:
- `sugna_core.settings_dev`
- `sugna_core.settings_prod`

This file keeps backward compatibility so existing commands that rely on
`DJANGO_SETTINGS_MODULE=sugna_core.settings` continue to work.
"""

import os


_env = (os.environ.get("DJANGO_ENV") or "").strip().lower()
if _env in ("prod", "production", "server"):
    from config.settings.prod import *  # noqa: F403
elif _env in ("dev", "development", "local"):
    from config.settings.dev import *  # noqa: F403
else:
    # Backward-compatible default: when DEBUG is unset, treat it as dev.
    _debug = os.environ.get("DEBUG", "true").lower() in ("true", "1", "yes")
    if _debug:
        from config.settings.dev import *  # noqa: F403
    else:
        from config.settings.prod import *  # noqa: F403


# Ensure Django admin + the app generate absolute static URLs that match
# the Nginx `/static/` location and the shared `staticfiles` volume.
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

