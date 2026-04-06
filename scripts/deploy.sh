#!/usr/bin/env bash
set -euo pipefail

# Enterprise production deployment script for Sugna Enterprise Suite.
#
# Expected environment:
# - Docker + Docker Compose installed on the server
# - A checked-out git repository at APP_DIR (defaults to parent of this script = repo root)
# - .env.prod exists in APP_DIR (do not commit secrets)
#
# Flow:
#   git pull -> docker compose up --build ->
#   wait until DB accepts connections ->
#   wait until web container is running (not "restarting") and briefly stable ->
#   deploy_migrate -> collectstatic -> restart web + nginx
#
# If you use an external webhook that runs `docker compose up` itself, do NOT run
# `docker compose exec web migrate` immediately after — use scripts/webhook_after_compose.sh
# instead (same waits + migrations as this script, without git pull / compose up).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
ENV_FILE="${ENV_FILE:-.env.prod}"
MIGRATE_TENANTS="${MIGRATE_TENANTS:-true}"

WAIT_DB_MAX_ATTEMPTS="${WAIT_DB_MAX_ATTEMPTS:-60}"
WAIT_WEB_MAX_ATTEMPTS="${WAIT_WEB_MAX_ATTEMPTS:-90}"
WAIT_POLL_INTERVAL="${WAIT_POLL_INTERVAL:-2}"
STABILITY_SECONDS="${STABILITY_SECONDS:-3}"

# shellcheck source=deploy_lib.sh
source "$SCRIPT_DIR/deploy_lib.sh"

sugna_deploy_load_env

echo "==> Pulling latest code"
git pull --ff-only

echo "==> Building & starting containers"
compose up -d --build

echo "==> Brief pause before health checks (let Docker schedule containers)"
sleep 2

wait_for_database
wait_for_web_running_and_stable

sugna_post_up_migrate

echo "==> Deployment complete"
