from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0030_documentnumberlog"),
        ("tenant_users", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fiscalperiod",
            name="status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("open", "Open"),
                    ("soft_closed", "Soft closed"),
                    ("hard_closed", "Hard closed"),
                ],
                db_index=True,
                default="open",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="fiscalperiod",
            name="closed_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="fiscalperiod",
            name="reopened_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fiscalperiod",
            name="reopened_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="fiscalperiod",
            name="reopened_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenant_users.tenantuser",
            ),
        ),
        migrations.CreateModel(
            name="PeriodControlSetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("soft_close_allowed_roles", models.CharField(blank=True, help_text="Comma-separated role names allowed to post in soft-closed periods.", max_length=255)),
                ("reopen_allowed_roles", models.CharField(blank=True, help_text="Comma-separated role names allowed to reopen periods (requires reason).", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="PeriodActionLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("open", "Open"), ("soft_close", "Soft close"), ("hard_close", "Hard close"), ("reopen", "Reopen")], db_index=True, max_length=20)),
                ("from_status", models.CharField(blank=True, max_length=20)),
                ("to_status", models.CharField(blank=True, max_length=20)),
                ("reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("fiscal_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="tenant_finance.fiscalyear")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="action_logs", to="tenant_finance.fiscalperiod")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenant_users.tenantuser")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.RunSQL(
            sql="""
            UPDATE tenant_finance_fiscalperiod
            SET status = 'hard_closed'
            WHERE is_closed = TRUE AND (status IS NULL OR status = '' OR status = 'closed');
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
            UPDATE tenant_finance_fiscalperiod
            SET status = 'open'
            WHERE is_closed = FALSE AND (status IS NULL OR status = '' OR status = 'closed');
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

