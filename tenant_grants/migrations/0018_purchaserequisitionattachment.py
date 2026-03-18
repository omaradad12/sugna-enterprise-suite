# PR attachments.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0017_purchaserequisitionline"),
        ("tenant_users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseRequisitionAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="grants/pr_attachments/%Y/%m/")),
                ("original_filename", models.CharField(blank=True, max_length=255)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="pr_attachments_uploaded", to="tenant_users.tenantuser")),
                ("pr", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="tenant_grants.purchaserequisition")),
            ],
            options={
                "ordering": ["-uploaded_at"],
                "verbose_name": "PR attachment",
                "verbose_name_plural": "PR attachments",
            },
        ),
    ]
