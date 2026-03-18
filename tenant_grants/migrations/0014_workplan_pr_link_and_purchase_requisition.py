# Workplan: budget_line, procurement_requirement, approved_for_pr.
# Purchase Requisition model linked to workplan activity.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0013_workplan_activity"),
    ]

    operations = [
        migrations.AddField(
            model_name="workplanactivity",
            name="budget_line",
            field=models.CharField(blank=True, help_text="Budget line or category for this activity.", max_length=120),
        ),
        migrations.AddField(
            model_name="workplanactivity",
            name="procurement_requirement",
            field=models.TextField(blank=True, help_text="Description of procurement need for this activity."),
        ),
        migrations.AddField(
            model_name="workplanactivity",
            name="approved_for_pr",
            field=models.BooleanField(default=False, help_text="When True, a Purchase Requisition can be raised from this activity."),
        ),
        migrations.CreateModel(
            name="PurchaseRequisition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pr_number", models.CharField(max_length=50, unique=True)),
                ("pr_date", models.DateField()),
                ("budget_line", models.CharField(blank=True, max_length=120)),
                ("item_description", models.TextField()),
                ("quantity", models.DecimalField(decimal_places=2, default=1, max_digits=12)),
                ("estimated_unit_cost", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("estimated_total_cost", models.DecimalField(decimal_places=2, default=0, help_text="Quantity × unit cost; validated against activity budget.", max_digits=14)),
                ("procurement_method", models.CharField(blank=True, choices=[("open_tender", "Open Tender"), ("request_quotation", "Request for Quotation"), ("direct_purchase", "Direct Purchase"), ("framework", "Framework Agreement"), ("other", "Other")], default="other", max_length=30)),
                ("priority", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")], default="medium", max_length=20)),
                ("justification", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved"), ("rejected", "Rejected"), ("ordered", "Ordered"), ("received", "Received"), ("closed", "Closed")], default="draft", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("donor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="purchase_requisitions", to="tenant_grants.donor")),
                ("grant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="purchase_requisitions", to="tenant_grants.grant")),
                ("workplan_activity", models.ForeignKey(help_text="Approved workplan activity this PR is raised from.", on_delete=django.db.models.deletion.PROTECT, related_name="purchase_requisitions", to="tenant_grants.workplanactivity")),
            ],
            options={
                "ordering": ["-pr_date", "-created_at"],
                "verbose_name": "Purchase requisition",
                "verbose_name_plural": "Purchase requisitions",
            },
        ),
    ]
