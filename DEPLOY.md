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

   ```bash
   cp .env.prod .env
   ```

   Edit `.env` and set **real** values:

   - **DJANGO_SECRET_KEY** (or **SECRET_KEY**) – long random string, e.g.  
     `python -c "import secrets; print(secrets.token_urlsafe(50))"`
   - **DEBUG** – must be `false` (or `0`)
   - **ALLOWED_HOSTS** – your domain(s), comma-separated (e.g. `app.example.com,www.app.example.com`)
   - **DB_PASSWORD** – strong PostgreSQL password
   - **DB_HOST** – keep `db` when using docker-compose

   Optionally set **CSRF_TRUSTED_ORIGINS** (comma-separated HTTPS origins) and **DB_EXTRA_TENANTS=false** if you don’t use the extra dev tenant DBs.

2. **Build and start (production)**

   Using the production override:

   ```bash
   docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml build
   docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```

   Or, with `.env` already in place:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

3. **Migrations**

   ```bash
   docker compose exec web python manage.py migrate
   ```

   Run any tenant-specific migrations if your setup uses them.

4. **Static files**

   ```bash
   docker compose exec web python manage.py collectstatic --noinput
   ```

5. **Superuser** (optional)

   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

6. **Verification**

   Open your site (and `/admin/`) and confirm everything works. Put a reverse proxy (e.g. Nginx or Caddy) in front of the `web` service and serve static/media from the proxy or a CDN. For a strict production deploy you can remove the `.:/app` volume from the `web` service so the container uses only the built image.

---

## 3. Switching between environments

- **Development → Production (Docker)**  
  - Copy production env: `cp .env.prod .env`  
  - Edit `.env` with real secrets and domains.  
  - Run with prod override:  
    `docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml up -d`

- **Production → Development (Docker)**  
  - Copy dev env: `cp .env.dev .env` (or use `.env.dev` directly).  
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

3. **Run migrations**

   ```bash
   docker compose exec web python manage.py migrate
   ```

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

If you use the dev/prod override files, add the same `-f docker-compose.yml -f docker-compose.prod.yml` (or `.dev.yml`) to your `docker compose` commands. For non-Docker deployments, run `migrate` and `collectstatic` in your venv and restart your app server (e.g. gunicorn/systemd).

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
