# shellcheck shell=bash
# Shared helpers for production deploy. Sourced by deploy.sh and webhook_after_compose.sh.
#
# Call order:
#   1. Set APP_DIR, ENV_FILE, MIGRATE_TENANTS, WAIT_* (optional)
#   2. sugna_deploy_load_env
#   3. wait_for_database && wait_for_web_running_and_stable
#   4. sugna_post_up_migrate

sugna_deploy_load_env() {
  cd "$APP_DIR" || {
    echo "ERROR: Cannot cd to APP_DIR=$APP_DIR" >&2
    return 1
  }
  if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: Env file not found: $ENV_FILE (under $APP_DIR)" >&2
    return 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
}

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

sugna_post_up_migrate() {
  DEPLOY_MIGRATE_ARGS=(python manage.py deploy_migrate --noinput)
  if [ "${MIGRATE_TENANTS:-true}" != "true" ]; then
    DEPLOY_MIGRATE_ARGS+=(--skip-tenant-databases)
  fi
  echo "==> Running database migrations (deploy_migrate: control-plane + tenant DBs unless skipped)"
  compose exec -T web "${DEPLOY_MIGRATE_ARGS[@]}"

  echo "==> Collecting static assets"
  compose exec -T web python manage.py collectstatic --noinput

  echo "==> Restarting web and nginx"
  compose restart web nginx
}
