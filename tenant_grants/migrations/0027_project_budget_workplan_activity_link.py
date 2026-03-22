import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0003_core_accounting_models"),
        ("tenant_grants", "0026_donor_restriction_enterprise"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProjectBudget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(default="Main", max_length=120)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="project_budgets",
                        to="tenant_grants.project",
                    ),
                ),
            ],
            options={
                "ordering": ["project", "name"],
            },
        ),
        migrations.CreateModel(
            name="ProjectBudgetLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(max_length=120)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("allocated_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("remaining_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="project_budget_lines",
                        to="tenant_finance.chartaccount",
                    ),
                ),
                (
                    "project_budget",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="tenant_grants.projectbudget",
                    ),
                ),
            ],
            options={
                "ordering": ["project_budget", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="projectbudget",
            constraint=models.UniqueConstraint(fields=("project", "name"), name="uniq_project_budget_project_name"),
        ),
        migrations.AddField(
            model_name="workplanactivity",
            name="actual_cost",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Posted expense total tagged to this activity (system-maintained).",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="workplanactivity",
            name="activity_code",
            field=models.CharField(
                blank=True,
                help_text="Optional short code; defaults to workplan ID when blank.",
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="workplanactivity",
            name="description",
            field=models.TextField(blank=True, help_text="Extended activity description."),
        ),
        migrations.AddField(
            model_name="workplanactivity",
            name="project",
            field=models.ForeignKey(
                blank=True,
                help_text="Implementation project; synced from grant.project when set.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="workplan_activities",
                to="tenant_grants.project",
            ),
        ),
        migrations.AddField(
            model_name="workplanactivity",
            name="project_budget_line",
            field=models.ForeignKey(
                blank=True,
                help_text="Required when the project uses a project budget structure.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="workplan_activities",
                to="tenant_grants.projectbudgetline",
            ),
        ),
        migrations.AlterField(
            model_name="workplanactivity",
            name="budget_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                help_text="Planned cost for this activity (must fit within budget line envelope).",
                max_digits=14,
                null=True,
            ),
        ),
    ]
