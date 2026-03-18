from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0025_documentseries_scope_and_counters"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                # DocumentSeries: add missing scope fields safely
                """
                ALTER TABLE tenant_finance_documentseries
                ADD COLUMN IF NOT EXISTS scope varchar(20) NOT NULL DEFAULT 'global';
                """,
                """
                ALTER TABLE tenant_finance_documentseries
                ADD COLUMN IF NOT EXISTS project_id bigint NULL;
                """,
                """
                ALTER TABLE tenant_finance_documentseries
                ADD COLUMN IF NOT EXISTS grant_id bigint NULL;
                """,
                # Unique constraint: ensure new scope-aware uniqueness exists
                """
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uniq_documentseries_type_year_prefix_scope'
                  ) THEN
                    ALTER TABLE tenant_finance_documentseries
                    ADD CONSTRAINT uniq_documentseries_type_year_prefix_scope
                    UNIQUE (document_type, fiscal_year_id, prefix, scope, project_id, grant_id);
                  END IF;
                END$$;
                """,
                # Counter table (idempotent)
                """
                CREATE TABLE IF NOT EXISTS tenant_finance_documentsequencecounter (
                  id bigserial PRIMARY KEY,
                  period_key varchar(20) NOT NULL,
                  current_number integer NOT NULL DEFAULT 0,
                  updated_at timestamptz NOT NULL DEFAULT NOW(),
                  series_id bigint NOT NULL REFERENCES tenant_finance_documentseries(id) ON DELETE CASCADE,
                  project_id bigint NULL REFERENCES tenant_grants_project(id) ON DELETE CASCADE,
                  grant_id bigint NULL REFERENCES tenant_grants_grant(id) ON DELETE CASCADE
                );
                """,
                """
                CREATE INDEX IF NOT EXISTS tenant_finance_documentsequencecounter_period_key_idx
                ON tenant_finance_documentsequencecounter(period_key);
                """,
                """
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uniq_docseries_counter_series_period_scope'
                  ) THEN
                    ALTER TABLE tenant_finance_documentsequencecounter
                    ADD CONSTRAINT uniq_docseries_counter_series_period_scope
                    UNIQUE (series_id, period_key, project_id, grant_id);
                  END IF;
                END$$;
                """,
            ],
            reverse_sql=migrations.RunSQL.noop,
        )
    ]

