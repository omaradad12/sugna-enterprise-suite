#!/bin/sh
set -e
cd /app

# In Docker Compose production, STATIC_ROOT (/app/staticfiles) is a named volume.
# That mount hides any files collected at image build time, so the volume is empty
# until collectstatic runs. Populate it before gunicorn starts so nginx can serve
# /static/ from the shared volume.
#
# Set SKIP_COLLECTSTATIC=1 (e.g. in dev Docker) to skip when Django serves static via
# staticfiles_urlpatterns (DEBUG=True).
if [ "${SKIP_COLLECTSTATIC:-0}" != "1" ]; then
  python manage.py collectstatic --noinput
fi

exec "$@"
