# PR line items for activity breakdown: add/remove lines per PR.

from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion


def backfill_pr_lines(apps, schema_editor):
    PurchaseRequisition = apps.get_model("tenant_grants", "PurchaseRequisition")
    PurchaseRequisitionLine = apps.get_model("tenant_grants", "PurchaseRequisitionLine")
    alias = schema_editor.connection.alias
    for pr in PurchaseRequisition.objects.using(alias).all():
        if not PurchaseRequisitionLine.objects.using(alias).filter(pr=pr).exists():
            PurchaseRequisitionLine.objects.using(alias).create(
                pr=pr,
                line_number=1,
                item_description=pr.item_description or "",
                quantity=pr.quantity or Decimal("1"),
                estimated_unit_cost=pr.estimated_unit_cost or Decimal("0"),
                estimated_total_cost=pr.estimated_total_cost or Decimal("0"),
                budget_line=pr.budget_line or "",
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0016_purchaserequisition_delivery_date"),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseRequisitionLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("line_number", models.PositiveSmallIntegerField(default=1)),
                ("item_description", models.TextField()),
                ("quantity", models.DecimalField(decimal_places=2, default=1, max_digits=12)),
                ("estimated_unit_cost", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("estimated_total_cost", models.DecimalField(decimal_places=2, default=0, help_text="Quantity × unit cost (set in save).", max_digits=14)),
                ("budget_line", models.CharField(blank=True, max_length=120)),
                ("pr", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="tenant_grants.purchaserequisition")),
            ],
            options={
                "ordering": ["pr", "line_number", "id"],
                "verbose_name": "PR line",
                "verbose_name_plural": "PR lines",
            },
        ),
        migrations.RunPython(backfill_pr_lines, noop),
    ]
