from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_users", "0001_initial"),
        ("tenant_grants", "0005_budgetline_account_description"),
    ]

    operations = [
        migrations.CreateModel(
            name="GrantAssignment",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True)),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                (
                    "grant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="finance_assignments",
                        to="tenant_grants.grant",
                    ),
                ),
                (
                    "officer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grant_assignments",
                        to="tenant_users.tenantuser",
                    ),
                ),
            ],
            options={
                "ordering": ["-assigned_at"],
                "unique_together": {("grant", "officer", "is_active")},
            },
        ),
    ]

