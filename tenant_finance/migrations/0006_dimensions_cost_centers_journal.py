# Dimensions: CostCenter model; JournalEntry.dimension & cost_center for integration

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0005_financial_setup_models"),
        ("tenant_users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CostCenter",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=30, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive")], default="active", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="tenant_users.tenantuser",
                    ),
                ),
                (
                    "manager",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="tenant_users.tenantuser",
                    ),
                ),
            ],
            options={
                "ordering": ["code"],
                "verbose_name_plural": "Cost centers",
            },
        ),
        migrations.AddField(
            model_name="journalentry",
            name="cost_center",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenant_finance.costcenter",
            ),
        ),
        migrations.AddField(
            model_name="costcenter",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="children",
                to="tenant_finance.costcenter",
            ),
        ),
        migrations.AddField(
            model_name="journalentry",
            name="dimension",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenant_finance.financialdimension",
            ),
        ),
    ]
