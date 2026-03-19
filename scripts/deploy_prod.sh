#!/usr/bin/env bash
set -euo pipefail

# Backward-compatible wrapper.
# Prefer `scripts/deploy.sh` for the full production workflow.

APP_DIR="${APP_DIR:-/opt/sugna-enterprise-suite}"
ENV_FILE="${ENV_FILE:-.env.prod}"

export MIGRATE_TENANTS="${MIGRATE_TENANTS:-true}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/deploy.sh"

