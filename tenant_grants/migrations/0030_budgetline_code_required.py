from django.db import migrations, models


def backfill_budget_line_code(apps, schema_editor):
    conn = schema_editor.connection
    existing_tables = set(conn.introspection.table_names(cursor=conn.cursor()))
    if "tenant_grants_budgetline" not in existing_tables:
        return

    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE tenant_grants_budgetline
            SET budget_line_code = 'BL-' || LPAD(CAST(id AS text), 6, '0')
            WHERE budget_line_code IS NULL OR TRIM(budget_line_code) = '';
            """
        )


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0029_grant_financial_report_proxies"),
    ]

    operations = [
        migrations.AddField(
            model_name="budgetline",
            name="budget_line_code",
            field=models.CharField(
                default="",
                help_text="Budget line code mapped to COA account code (unique per grant/project).",
                max_length=50,
            ),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_budget_line_code, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="budgetline",
            constraint=models.UniqueConstraint(
                fields=("grant", "budget_line_code"),
                name="uniq_budgetline_grant_code",
            ),
        ),
    ]

