#!/usr/bin/env bash
set -euo pipefail

# Run after YOUR webhook (or CI) has already done: git pull && docker compose up -d --build
#
# This script ONLY: waits for PostgreSQL + stable web container, then runs the same
# migrations / collectstatic / restart as scripts/deploy.sh. Use it when you cannot
# call deploy.sh end-to-end (e.g. Go webhook that runs compose up inline).
#
# Typical webhook fix — replace immediate `docker compose exec web migrate` with:
#   APP_DIR=/root/sugna-enterprise-suite /root/sugna-enterprise-suite/scripts/webhook_after_compose.sh
#
# Or point the webhook at ONLY this script after compose up (no duplicate migrate).

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

echo "==> webhook_after_compose: stack should already be up; waiting for DB + web before migrations"
sleep 2

wait_for_database
wait_for_web_running_and_stable

sugna_post_up_migrate

echo "==> webhook_after_compose: done"
