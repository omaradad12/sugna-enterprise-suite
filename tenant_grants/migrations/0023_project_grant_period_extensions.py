from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0022_project_grant_dimension_improvements"),
        ("tenant_users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="original_end_date",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="Original planned project end date (baseline).",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="revised_end_date",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="Revised end date after approved extensions (optional).",
            ),
        ),
        migrations.AddField(
            model_name="grant",
            name="original_end_date",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="Original planned grant end date (baseline).",
            ),
        ),
        migrations.AddField(
            model_name="grant",
            name="revised_end_date",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="Revised end date after approved extensions (optional).",
            ),
        ),
        migrations.CreateModel(
            name="ProjectPeriodExtension",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("revised_end_date", models.DateField()),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenant_users.tenantuser")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="period_extensions", to="tenant_grants.project")),
            ],
            options={"ordering": ["-revised_end_date", "-id"]},
        ),
        migrations.CreateModel(
            name="GrantPeriodExtension",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("revised_end_date", models.DateField()),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenant_users.tenantuser")),
                ("grant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="period_extensions", to="tenant_grants.grant")),
            ],
            options={"ordering": ["-revised_end_date", "-id"]},
        ),
        migrations.RunSQL(
            sql="""
            UPDATE tenant_grants_project
            SET original_end_date = COALESCE(original_end_date, end_date)
            WHERE original_end_date IS NULL AND end_date IS NOT NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
            UPDATE tenant_grants_grant
            SET original_end_date = COALESCE(original_end_date, end_date)
            WHERE original_end_date IS NULL AND end_date IS NOT NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

