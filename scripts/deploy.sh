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
#   git pull -> docker compose up --build -> migrate -> collectstatic -> restart

APP_DIR="${APP_DIR:-/opt/sugna-enterprise-suite}"
ENV_FILE="${ENV_FILE:-.env.prod}"

MIGRATE_TENANTS="${MIGRATE_TENANTS:-true}"

cd "$APP_DIR"

echo "==> Pulling latest code"
git pull --ff-only

echo "==> Building & starting containers"
docker compose \
  --env-file "$ENV_FILE" \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d --build

echo "==> Running Django migrations (control-plane)"
docker compose \
  --env-file "$ENV_FILE" \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  exec -T web python manage.py migrate --noinput

if [ "$MIGRATE_TENANTS" = "true" ]; then
  echo "==> Running tenant migrations (all tenants with db_name)"
  docker compose \
    --env-file "$ENV_FILE" \
    -f docker-compose.yml \
    -f docker-compose.prod.yml \
    exec -T web python manage.py migrate_all_tenants --noinput
fi

echo "==> Collecting static assets (idempotent; web entrypoint also runs collectstatic on start)"
docker compose \
  --env-file "$ENV_FILE" \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  exec -T web python manage.py collectstatic --noinput

echo "==> Restarting services"
docker compose \
  --env-file "$ENV_FILE" \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  restart web nginx

echo "==> Deployment complete"

