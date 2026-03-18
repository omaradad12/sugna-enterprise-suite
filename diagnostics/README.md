# Self-Healing Diagnostics Module

Platform- and tenant-level health checks, root cause analysis, and automated remediation.

## Operating modes

- **Automatic (continuous):** Schedule `run_diagnostics` (e.g. cron every 5 min). Use `--auto-remediate` or `DIAGNOSTICS_AUTO_REMEDIATE=true` to run allowed remediation actions for open incidents.
- **Manual (on-demand):** Use **Platform → Diagnostics → Run scan** (scope: platform, tenant, database, api, service) or `POST /api/diagnostics/scan/` to get a detailed report and optionally apply fixes.

## Quick start

- **Run checks (platform + tenants):**  
  `python manage.py run_diagnostics`

- **Run with auto-remediation:**  
  `python manage.py run_diagnostics --auto-remediate`  
  Or set `DIAGNOSTICS_AUTO_REMEDIATE=true` in environment.

- **Health endpoint (e.g. for load balancer):**  
  `GET /api/diagnostics/health/`  
  Returns 200 and `{"status": "ok", "database": "connected"}` when default DB is up.  
  `GET /api/diagnostics/health/?full=1` (staff) adds tenant DBs and cache status.

- **Manual scan (API):**  
  `POST /api/diagnostics/scan/` with body `{"scope": "platform"|"tenant"|"database"|"api"|"service", "tenant_id": 123, "apply_fixes": false}`.  
  Returns full diagnostic report (summary, check_runs, findings, incidents).

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/diagnostics/health/` | Platform health (DB); ?full=1 for tenants + cache (staff) |
| POST | `/api/diagnostics/scan/` | Run manual scan (body: scope, tenant_id?, service?, apply_fixes?) |
| GET | `/api/diagnostics/reports/` | List reports (filter: trigger, date_from, date_to) |
| GET | `/api/diagnostics/reports/<id>/` | Report detail + runs, findings, incidents |
| GET | `/api/diagnostics/checks/runs/` | List check runs |
| GET | `/api/diagnostics/checks/runs/<id>/` | Run detail + findings |
| GET | `/api/diagnostics/findings/` | List findings |
| GET | `/api/diagnostics/incidents/` | List incidents |
| GET | `/api/diagnostics/incidents/<id>/` | Incident detail + remediation logs |
| POST | `/api/diagnostics/incidents/<id>/remediate/` | Run remediation (action_code or run_all=1, optional approved=1) |
| GET | `/api/diagnostics/remediation-logs/` | List remediation logs |

## Scan targets (manual)

- **platform:** Default DB, app registry, cache.
- **tenant:** Single tenant DB (tenant_id required).
- **database:** Default DB only, or one tenant DB if tenant_id given.
- **api:** HTTP GET to health URL (configurable via `DIAGNOSTICS_HEALTH_URL`).
- **service:** One of cache, default_db, app_registry.

## Automation

Schedule automatic mode, e.g. cron every 5 minutes:

```bash
*/5 * * * * cd /path/to/project && python manage.py run_diagnostics --auto-remediate
```

Or set `DIAGNOSTICS_AUTO_REMEDIATE=true` and run without the flag.

## Policy

Remediation actions are allowed by default for: `reconnect_default_db`, `clear_django_cache`, `warm_tenant_connections`, `reconnect_tenant_db`, `run_tenant_migrations`, `mark_tenant_maintenance`.  
Override in Django admin: **Diagnostics → Remediation policies** (allow/require_approval per action_code).
