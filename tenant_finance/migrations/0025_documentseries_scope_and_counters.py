import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0024_audittrailsetting_dynamics_ui_extensions"),
        ("tenant_grants", "0022_project_grant_dimension_improvements"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentseries",
            name="scope",
            field=models.CharField(
                choices=[("global", "Global"), ("project", "Project"), ("grant", "Grant")],
                db_index=True,
                default="global",
                help_text="Scope of the sequence: global, per project, or per grant.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="documentseries",
            name="project",
            field=models.ForeignKey(
                blank=True,
                help_text="Project for project-scoped sequences (optional).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenant_grants.project",
            ),
        ),
        migrations.AddField(
            model_name="documentseries",
            name="grant",
            field=models.ForeignKey(
                blank=True,
                help_text="Grant for grant-scoped sequences (optional).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenant_grants.grant",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="documentseries",
            name="uniq_documentseries_type_year_prefix",
        ),
        migrations.AddConstraint(
            model_name="documentseries",
            constraint=models.UniqueConstraint(
                fields=("document_type", "fiscal_year", "prefix", "scope", "project", "grant"),
                name="uniq_documentseries_type_year_prefix_scope",
            ),
        ),
        migrations.CreateModel(
            name="DocumentSequenceCounter",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period_key", models.CharField(db_index=True, help_text="Reset period key (e.g. 2026, 2026-03, all).", max_length=20)),
                ("current_number", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("grant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="+", to="tenant_grants.grant")),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="+", to="tenant_grants.project")),
                ("series", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="counters", to="tenant_finance.documentseries")),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("series", "period_key", "project", "grant"),
                        name="uniq_docseries_counter_series_period_scope",
                    )
                ],
            },
        ),
    ]

