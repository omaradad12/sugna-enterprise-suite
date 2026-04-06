#!/bin/sh
set -e
cd /app

# Apply control-plane migrations before serving (entrypoint runs on each web container start).
# Set SKIP_MIGRATE=1 only if you intentionally run migrate elsewhere (e.g. separate job).
#
# Wait until Django can open a DB connection first. If migrate runs before Postgres accepts
# connections, it exits non-zero and this script never reaches gunicorn → nginx 502.
if [ "${SKIP_MIGRATE:-0}" != "1" ]; then
  echo "Waiting for database..."
  db_ok=0
  i=0
  while [ "$i" -lt 60 ]; do
    if python manage.py shell -c "from django.db import connection; connection.ensure_connection()" 2>/dev/null; then
      db_ok=1
      echo "Database ready."
      break
    fi
    i=$((i + 1))
    sleep 2
  done
  if [ "$db_ok" != "1" ]; then
    echo "ERROR: Could not connect to the database after 120s. Check DB_HOST, credentials, and that Postgres is running." >&2
    exit 1
  fi
  python manage.py migrate --noinput
fi

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
