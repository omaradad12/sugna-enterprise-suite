# PR workflow: new statuses, requester/line manager/procurement fields, status log audit.

from django.db import migrations, models
import django.db.models.deletion


def map_old_pr_statuses(apps, schema_editor):
    PurchaseRequisition = apps.get_model("tenant_grants", "PurchaseRequisition")
    alias = schema_editor.connection.alias
    mapping = {
        "draft": "draft",
        "submitted": "pending_line_manager_approval",
        "approved": "approved_by_line_manager",
        "rejected": "rejected",
        "ordered": "po_issued",
        "received": "fulfilled",
        "closed": "fulfilled",
    }
    for pr in PurchaseRequisition.objects.using(alias).all():
        new_status = mapping.get(pr.status, "draft")
        if pr.status != new_status:
            pr.status = new_status
            pr.save(using=alias, update_fields=["status"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0014_workplan_pr_link_and_purchase_requisition"),
        ("tenant_users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(map_old_pr_statuses, noop),
        migrations.AlterField(
            model_name="purchaserequisition",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("pending_line_manager_approval", "Pending Line Manager Approval"),
                    ("approved_by_line_manager", "Approved by Line Manager"),
                    ("assigned_to_procurement", "Assigned to Procurement"),
                    ("under_procurement_processing", "Under Procurement Processing"),
                    ("po_issued", "PO Issued"),
                    ("fulfilled", "Fulfilled"),
                    ("rejected", "Rejected"),
                    ("cancelled", "Cancelled"),
                ],
                default="draft",
                max_length=45,
            ),
        ),
        migrations.AddField(
            model_name="purchaserequisition",
            name="requested_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="purchase_requisitions_requested",
                to="tenant_users.tenantuser",
            ),
        ),
        migrations.AddField(
            model_name="purchaserequisition",
            name="submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="purchaserequisition",
            name="line_manager_approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="purchaserequisition",
            name="line_manager_approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pr_approved_by_line_manager",
                to="tenant_users.tenantuser",
            ),
        ),
        migrations.AddField(
            model_name="purchaserequisition",
            name="line_manager_rejection_comment",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="purchaserequisition",
            name="line_manager_return_comment",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="purchaserequisition",
            name="assigned_to_procurement_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="purchaserequisition",
            name="procurement_officer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pr_assigned_to_procurement",
                to="tenant_users.tenantuser",
            ),
        ),
        migrations.AddField(
            model_name="purchaserequisition",
            name="po_issued_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="purchaserequisition",
            name="fulfilled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="purchaserequisition",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="purchaserequisition",
            name="cancelled_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pr_cancelled",
                to="tenant_users.tenantuser",
            ),
        ),
        migrations.AddField(
            model_name="purchaserequisition",
            name="cancellation_comment",
            field=models.TextField(blank=True),
        ),
        migrations.CreateModel(
            name="PurchaseRequisitionStatusLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("from_status", models.CharField(blank=True, max_length=45)),
                ("to_status", models.CharField(max_length=45)),
                ("performed_at", models.DateTimeField(auto_now_add=True)),
                ("comment", models.TextField(blank=True)),
                ("performed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="pr_status_logs", to="tenant_users.tenantuser")),
                ("pr", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="status_logs", to="tenant_grants.purchaserequisition")),
            ],
            options={
                "ordering": ["-performed_at"],
                "verbose_name": "PR status log",
                "verbose_name_plural": "PR status logs",
            },
        ),
    ]
