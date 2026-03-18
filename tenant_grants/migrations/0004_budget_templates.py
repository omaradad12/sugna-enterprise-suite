from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0003_funds_donors_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="BudgetTemplate",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                (
                    "scope",
                    models.CharField(
                        choices=[
                            ("generic", "Generic"),
                            ("project", "Project / grant"),
                            ("donor", "Donor"),
                        ],
                        default="generic",
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "donor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="budget_templates",
                        to="tenant_grants.donor",
                    ),
                ),
                (
                    "grant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="budget_templates",
                        to="tenant_grants.grant",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="BudgetTemplateLine",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("category", models.CharField(max_length=200)),
                ("default_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("order", models.PositiveIntegerField(default=0)),
                ("notes", models.CharField(blank=True, max_length=255)),
                (
                    "template",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="tenant_grants.budgettemplate",
                    ),
                ),
            ],
            options={
                "ordering": ["template", "order", "id"],
            },
        ),
    ]

