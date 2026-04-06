#!/usr/bin/env bash
set -euo pipefail

# Enterprise production deployment script for Sugna Enterprise Suite.
#
# Expected environment:
# - Docker + Docker Compose installed on the server
# - A checked-out git repository at APP_DIR
# - .env.prod exists in APP_DIR (do not commit secrets)
#
# Flow:
#   git pull -> docker compose up --build ->
#   wait until DB accepts connections ->
#   wait until web container is running (not "restarting") and briefly stable ->
#   migrate -> migrate_all_tenants (optional) -> collectstatic -> restart web + nginx
#
# Why wait: `docker compose exec` fails with "container is restarting" if you run
# migrations immediately after `up` while the web container is still crash-looping
# or still starting. The web entrypoint also runs migrate/collectstatic; this script
# runs them again after the stack is healthy (second migrate is a no-op when caught up).
#
# Optional: set SKIP_MIGRATE=1 on the web service in compose if you want migrations
# only from this script (not from the container entrypoint).
#
# Tunable via environment:
#   WAIT_DB_MAX_ATTEMPTS   default 60   (× sleep interval below)
#   WAIT_WEB_MAX_ATTEMPTS  default 90
#   WAIT_POLL_INTERVAL     default 2    seconds between checks

APP_DIR="${APP_DIR:-/opt/sugna-enterprise-suite}"
ENV_FILE="${ENV_FILE:-.env.prod}"
MIGRATE_TENANTS="${MIGRATE_TENANTS:-true}"

WAIT_DB_MAX_ATTEMPTS="${WAIT_DB_MAX_ATTEMPTS:-60}"
WAIT_WEB_MAX_ATTEMPTS="${WAIT_WEB_MAX_ATTEMPTS:-90}"
WAIT_POLL_INTERVAL="${WAIT_POLL_INTERVAL:-2}"
STABILITY_SECONDS="${STABILITY_SECONDS:-3}"

cd "$APP_DIR"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: Env file not found: $ENV_FILE (under $APP_DIR)" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

compose() {
  docker compose --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.prod.yml "$@"
}

fail_tail_logs() {
  echo "" >&2
  echo "---- docker compose ps -a ----" >&2
  compose ps -a || true
  echo "" >&2
  echo "---- web logs (last 200 lines) ----" >&2
  compose logs web --tail 200 2>&1 || true
  echo "" >&2
  echo "---- db logs (last 80 lines) ----" >&2
  compose logs db --tail 80 2>&1 || true
}

wait_for_database() {
  local attempt=0
  local dbuser="${DB_USER:-postgres}"
  local dbname="${DB_NAME:-sugna_enterprise_suite}"
  echo "==> Waiting for PostgreSQL to accept connections (pg_isready)..."
  while [ "$attempt" -lt "$WAIT_DB_MAX_ATTEMPTS" ]; do
    if compose exec -T db pg_isready -U "$dbuser" -d "$dbname" &>/dev/null; then
      echo "    OK: Database is healthy (user=$dbuser db=$dbname)."
      return 0
    fi
    attempt=$((attempt + 1))
    printf '    ... db not ready yet (%s/%s)\n' "$attempt" "$WAIT_DB_MAX_ATTEMPTS"
    sleep "$WAIT_POLL_INTERVAL"
  done
  echo "ERROR: Database did not become ready within the time limit." >&2
  fail_tail_logs
  return 1
}

wait_for_web_running_and_stable() {
  local attempt=0
  echo "==> Waiting for web container to be running (not restarting) and stable..."
  echo "    (Avoids: 'Container ... is restarting, wait until the container is running')"
  while [ "$attempt" -lt "$WAIT_WEB_MAX_ATTEMPTS" ]; do
    local cid
    cid="$(compose ps -q web 2>/dev/null | head -n1 || true)"
    if [ -n "${cid:-}" ]; then
      local status
      status="$(docker inspect --format '{{.State.Status}}' "$cid" 2>/dev/null || echo unknown)"
      case "$status" in
        running)
          # Must stay running after a short pause (catches immediate crash / restart loops).
          sleep "$STABILITY_SECONDS"
          local status2
          status2="$(docker inspect --format '{{.State.Status}}' "$cid" 2>/dev/null || echo unknown)"
          if [ "$status2" = "running" ]; then
            echo "    OK: Web container is up and stable (docker state=running)."
            return 0
          fi
          printf '    ... web flapped (%s -> %s), still waiting (%s/%s)\n' \
            "$status" "$status2" "$((attempt + 1))" "$WAIT_WEB_MAX_ATTEMPTS"
          ;;
        created|paused|dead|unknown)
          printf '    ... web state=%s (%s/%s)\n' "$status" "$((attempt + 1))" "$WAIT_WEB_MAX_ATTEMPTS"
          ;;
        restarting|exited)
          printf '    ... web state=%s — still waiting (%s/%s)\n' "$status" "$((attempt + 1))" "$WAIT_WEB_MAX_ATTEMPTS"
          ;;
        *)
          printf '    ... web state=%s (%s/%s)\n' "$status" "$((attempt + 1))" "$WAIT_WEB_MAX_ATTEMPTS"
          ;;
      esac
    else
      printf '    ... web service has no container id yet (%s/%s)\n' "$((attempt + 1))" "$WAIT_WEB_MAX_ATTEMPTS"
    fi
    attempt=$((attempt + 1))
    sleep "$WAIT_POLL_INTERVAL"
  done
  echo "ERROR: Web container did not become running and stable in time." >&2
  fail_tail_logs
  return 1
}

echo "==> Pulling latest code"
git pull --ff-only

echo "==> Building & starting containers"
compose up -d --build

echo "==> Brief pause before health checks (let Docker schedule containers)"
sleep 2

wait_for_database
wait_for_web_running_and_stable

echo "==> Running Django migrations (control-plane)"
compose exec -T web python manage.py migrate --noinput

if [ "$MIGRATE_TENANTS" = "true" ]; then
  echo "==> Running tenant migrations (all tenants with db_name)"
  compose exec -T web python manage.py migrate_all_tenants --noinput
fi

echo "==> Collecting static assets"
compose exec -T web python manage.py collectstatic --noinput

echo "==> Restarting web and nginx (apply any runtime changes; nginx picks up static volume)"
compose restart web nginx

echo "==> Deployment complete"
