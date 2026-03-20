# Sugna Enterprise Suite — DB-per-tenant architecture

## Control plane (`sugna_enterprise_suite`)

**Django `default` database.** Holds only shared platform metadata:

| Area | App / models |
|------|----------------|
| Tenants | `tenants.Tenant`, `tenants.TenantDomain`, `tenants.TenantModule` |
| Catalog | `tenants.Module`, `tenants.SubscriptionPlan` |
| Routing | Tenant DB credentials on `Tenant` (`db_name`, `db_user`, `db_password`, `db_host`, `db_port`) |
| Other shared apps | `platform_dashboard`, `help_center`, `diagnostics`, Django `auth` for staff, etc. |

**Router rule:** `TenantDatabaseRouter.allow_migrate`: tenant app labels migrate only on non-`default` aliases; control-plane apps migrate only on `default`.

## Tenant databases (`hurdo_db`, `wardi_db`, `sugna_training_db`, …)

**Dynamic alias:** `tenant_{slug}` registered at runtime in `settings.DATABASES` via `tenants.db.ensure_tenant_db_configured`.

| Area | App labels (see `TENANT_APP_LABELS` in settings) |
|------|---------------------------------------------------|
| Users & RBAC | `tenant_users`, `rbac` |
| Operations | `tenant_finance`, `tenant_grants`, `tenant_integrations`, `tenant_audit_risk`, `tenant_portal` |

## Commands (run against control plane unless noted)

- `run_full_tenant_provisioning()` (`tenants/services/onboarding.py`) — **recommended pipeline**: DDL → save `Tenant.db_*` → migrate → defaults → optional `bootstrap_tenant_rbac`. Used by platform tenant registration.
- `provision_tenant_onboard` — CLI wrapper for the same full pipeline.
- `retry_tenant_provisioning` — re-run after failure (reuses saved `db_*` when present).
- `provision_tenant_db` — lower-level: store credentials + optional `CREATE USER` / `CREATE DATABASE` (saves credentials before DDL; use onboarding for strict ordering).
- `migrate_tenant` — `migrate` on one tenant alias
- `migrate_all_tenants` — same for all tenants with `db_name`
- `bootstrap_tenant_rbac` — permissions, roles, tenant admin user **in tenant DB**
- `seed_platform` — modules + subscription plans **in control plane**
- `sync_modules` — alias for `seed_platform`

## Tenant row provisioning fields

- `provisioning_status`: `not_started` | `in_progress` | `success` | `failed`
- `provisioning_error`: last error text
- `provisioned_at`: set when status reaches `success`

On failure before credentials are saved, `db_*` stay empty. After migrate failure, `db_*` may be set so you can fix and use `retry_tenant_provisioning`.

## Verification (psql / pgAdmin)

1. List databases: `\l` — expect `sugna_enterprise_suite` + each tenant DB.
2. Control plane: `\c sugna_enterprise_suite` then `SELECT slug, db_name FROM tenants_tenant;`
3. Tenant: `\c hurdo_db` then `\dt` — expect tables for tenant apps (e.g. `tenant_users_tenantuser`).
