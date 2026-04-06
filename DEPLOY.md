# Sugna Enterprise Suite – Deployment Guide

This guide covers running the project in **development**, deploying to **production**, switching between environments, and updating the application safely.

---

## 1. Running in development

Development uses **DEBUG=true**, permissive **ALLOWED_HOSTS**, and local database defaults so the app can run without extra configuration.

### Option A: Local (no Docker)

1. **Use development defaults (no env file)**

   With no `.env` file, the app uses in-code defaults: `DEBUG=True`, `ALLOWED_HOSTS=*`, and the development database (e.g. `sugna_enterprise_suite` on `localhost`). Just run:

   ```bash
   python manage.py runserver
   ```

   Ensure PostgreSQL is running locally and the default database exists (or create it).

2. **Optional: use `.env.dev`**

   To load development variables from a file (e.g. with `python-dotenv` or by exporting them), copy the repo’s `.env.dev` and adjust if needed. The repo’s `.env.dev` has safe dev values (DEBUG=true, localhost, etc.).

### Option B: Docker (development)

1. **Use the dev env file and override**

   ```bash
   docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up -d
   ```

   This uses `.env.dev` for both Compose substitution and the web container. The compose file overrides `DB_HOST` to `db` so the app connects to the PostgreSQL service.

2. **Run migrations and create a superuser**

   ```bash
   docker compose exec web python manage.py migrate
   docker compose exec web python manage.py createsuperuser
   ```

3. **Optional: use a single `.env`**

   Copy `.env.dev` to `.env`, then:

   ```bash
   docker compose up -d
   ```

   (The default `docker-compose.yml` loads `.env` for the web service.)

---

## 2. Deploying to production

Production must use **DEBUG=false** and environment variables for **SECRET_KEY**, **ALLOWED_HOSTS**, and database configuration. The app is intended to run with Docker/docker-compose.

### Prerequisites

- Docker and Docker Compose on the server
- Project copy (e.g. `git clone` or release archive)

### Steps

1. **Create production env file**

   Create a file named `.env.prod` in the project directory (do not commit it). Use the following as a starting point, then replace the example secrets with your own generated values before deploying:

   ```env
   DJANGO_SECRET_KEY=bNMXD6t0OJSuUSe5E4pF1zFzYHFfLEC4C9CrCOn5KoN_xljhBB-CFncRcW4769QpVqCWVasNs_684SiSso8rWw
   DEBUG=false
   ALLOWED_HOSTS=46.224.112.206

   DB_NAME=sugna_enterprise_suite
   DB_USER=postgres
   DB_PASSWORD=ZWszwq5xYn_iEXcDXJRhV-CaDEzl5Go0
   DB_HOST=db
   DB_PORT=5432

   # Recommended for production (unless you explicitly want the extra dev tenant DBs)
   DB_EXTRA_TENANTS=false

   # Optional: HTTPS origins for CSRF (comma-separated)
   # CSRF_TRUSTED_ORIGINS=https://46.224.112.206
   ```

2. **Build and start (production)**

   ```bash
   docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

   **PostgreSQL must stay running.** If the `db` container stops, Django will return **500** on almost every page (sessions and auth use the default database). The compose files set `restart: unless-stopped` on `db` and `web` so the database comes back after a server reboot. After deploy, confirm all three services are up:

   ```bash
   docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml ps
   ```

   If `db` is not `Up`, start it: `docker compose ... up -d db`, then restart `web`.

3. **Migrations (control plane + every tenant)**

   Tables for apps in `TENANT_APP_LABELS` (including `tenant_grants`, e.g. `tenant_grants_donor`) are **not** created on the platform `default` database (`migrate` only). They exist only on **each tenant’s PostgreSQL database**. You must run **both**:

   ```bash
   docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml exec -T web python manage.py migrate --noinput
   docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml exec -T web python manage.py migrate_all_tenants --noinput
   ```

   Skipping `migrate_all_tenants` causes `ProgrammingError: relation "tenant_grants_…" does not exist` when tenant code runs.

4. **Static files (CSS, JS, admin assets)**

   **Settings:** `STATIC_URL=/static/`, `STATIC_ROOT=/app/staticfiles`, `MEDIA_URL=/media/`, `MEDIA_ROOT=/app/media` (see `config/settings/base.py`).

   **Why styling can disappear in production:** `docker-compose.prod.yml` mounts a **named volume** on `/app/staticfiles`. That mount hides anything collected at **image build** time, so the directory is empty until `collectstatic` runs **inside the running container**.

   **Automatic fix:** The production image uses `deploy/docker-entrypoint.sh` as **ENTRYPOINT**. It runs `python manage.py collectstatic --noinput` before Gunicorn so the shared volume is filled on every `web` container start. The `scripts/deploy.sh` step that runs `collectstatic` remains valid but is redundant (idempotent).

   **Nginx:** The `nginx` service mounts the same static volume at `/staticfiles` (read-only) and serves `location /static/` via `alias /staticfiles/`; media uses `/media`. **WhiteNoise is not used** — with `DEBUG=false`, Django does not add static URL handlers (`sugna_core/urls.py`); the edge proxy must serve `/static/` and `/media/`.

   **Manual check (web container):**

   ```bash
   docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml exec web ls -la /app/staticfiles | head
   ```

   You should see directories such as `admin/`, `css/`, `vendor/`, etc.

5. **Superuser** (optional)

   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

6. **Verification**

   Open your site (and `/admin/`) and confirm everything works. Put a reverse proxy (e.g. Nginx or Caddy) in front of the `web` service and serve static/media from the proxy or a CDN. For a strict production deploy you can remove the `.:/app` volume from the `web` service so the container uses only the built image.

---

## 3. Switching between environments

- **Development → Production (Docker)**  
  - Create `.env.prod` on the server (do not commit it) and set real secrets/domains.  
  - Run with prod override:  
    `docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up -d`

- **Production → Development (Docker)**  
  - Run with dev override:  
    `docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up -d`

- **Local runserver (development only)**  
  - No env file needed; defaults are for development.  
  - Or use `.env.dev` if you load env from a file.

Always use **DEBUG=false** and real **SECRET_KEY** and **ALLOWED_HOSTS** in production; use **DEBUG=true** and dev defaults only in development.

---

## 4. Updating the application safely

To deploy a new version without breaking the running app:

1. **Pull new code**

   ```bash
   git pull
   ```

2. **Rebuild the web image**

   ```bash
   docker compose build web
   ```

3. **Run migrations (control plane + all tenant DBs)**

   ```bash
   docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml exec -T web python manage.py migrate --noinput
   docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml exec -T web python manage.py migrate_all_tenants --noinput
   ```

   Or run the full scripted workflow from the repo root (see `scripts/deploy.sh`):

   ```bash
   export APP_DIR=/path/to/sugna-enterprise-suite
   ./scripts/deploy.sh
   ```

   Set `APP_DIR` to the directory that contains `docker-compose.yml` and `.env.prod` (defaults to `/opt/sugna-enterprise-suite` in the script). **Git hooks must run `migrate_all_tenants`**, not only `migrate`, or tenant tables (`tenant_grants_*`, etc.) will be missing.

4. **Collect static files**

   ```bash
   docker compose exec web python manage.py collectstatic --noinput
   ```

5. **Restart the web service**

   ```bash
   docker compose up -d web
   ```

6. **Check logs**

   ```bash
   docker compose logs -f web
   ```

If you use the dev/prod override files, add the same `-f docker-compose.yml -f docker-compose.prod.yml` (or `.dev.yml`) and `--env-file` to your `docker compose` commands. For non-Docker deployments, run `migrate`, `migrate_all_tenants`, and `collectstatic` in your venv and restart your app server (e.g. gunicorn/systemd).

### systemd / webhook deploy

If you use a service such as `sugna-webhook`, point it at the same workflow as `scripts/deploy.sh` (or invoke that script). Example unit file: `deploy/sugna-webhook.service.example`.

**Custom webhooks (Go, etc.):** If your hook runs `docker compose up` and then immediately `docker compose exec web … migrate`, Docker returns *"Container … is restarting, wait until the container is running"*. The web container needs time to finish its entrypoint (DB wait, migrate, collectstatic). **Do not** exec into `web` in the same second as `up`. Either:

- Run **`scripts/deploy.sh`** from the repo root (it waits for `pg_isready` and for the web container to stay `running`, then runs `deploy_migrate`), or
- If the hook already does `git pull` and `compose up` itself, run **`scripts/webhook_after_compose.sh`** afterward (same waits + `deploy_migrate` + collectstatic + restart, without repeating `up`).

The script waits until PostgreSQL accepts connections (`pg_isready` in the `db` container) and until the `web` container stays in Docker state `running` (not `restarting`) before running `migrate` / `exec`, so you do not hit *"Container ... is restarting"*. Tune waits with `WAIT_DB_MAX_ATTEMPTS`, `WAIT_WEB_MAX_ATTEMPTS`, and `WAIT_POLL_INTERVAL` (each attempt sleeps `WAIT_POLL_INTERVAL` seconds; defaults are documented in `scripts/deploy.sh`).

Migrations use **one** command inside the web container: `python manage.py deploy_migrate --noinput` (or add `--skip-tenant-databases` when `MIGRATE_TENANTS` is not `true`). That runs `migrate` on the **default** database, then `migrate_all_tenants`. If you only run `migrate` on default, tables such as `tenant_grants_donor` are **never** created there (they are tenant-scoped); they live on each **tenant PostgreSQL database**. A `ProgrammingError: relation "tenant_grants_donor" does not exist` during deploy usually means tenant DB migrations were skipped, or something queried tenant models on the default connection without `using(tenant_db)`. Use `deploy_migrate` or run `migrate_all_tenants` after every deploy that changes tenant apps.

---

## 5. Environment variables reference

| Variable            | Development        | Production        | Description |
|---------------------|--------------------|-------------------|-------------|
| **SECRET_KEY** / **DJANGO_SECRET_KEY** | Optional (default in code) | **Required** | Django secret key. |
| **DEBUG**           | Default `true`     | **Must be `false`** | Enable debug mode. |
| **ALLOWED_HOSTS**   | Default `*`        | **Required**      | Comma-separated hosts. |
| **DB_NAME**         | Default `sugna_enterprise_suite` | Optional | Database name. |
| **DB_USER**         | Default `postgres` | Optional         | Database user. |
| **DB_PASSWORD**     | Default in code / `.env.dev` | **Required** | Database password. |
| **DB_HOST**         | `localhost` (runserver) or `db` (Docker) | Usually `db` | Database host. |
| **DB_PORT**         | Default `5432`     | Optional         | Database port. |

Optional: **DB_EXTRA_TENANTS**, **CSRF_TRUSTED_ORIGINS**, **STATIC_ROOT**, **TENANT_APP_LABELS**.

---

## 6. Restart and one-off commands

- Restart web only:  
  `docker compose restart web`
- Restart all:  
  `docker compose restart`
- Stop and start:  
  `docker compose down && docker compose up -d`
- Shell in web container:  
  `docker compose exec web python manage.py shell`
- Run one-off command:  
  `docker compose exec web python manage.py <command>`

Use the same `-f docker-compose.yml -f docker-compose.prod.yml` (or `.dev.yml`) and `--env-file` as in the rest of this guide when applicable.
