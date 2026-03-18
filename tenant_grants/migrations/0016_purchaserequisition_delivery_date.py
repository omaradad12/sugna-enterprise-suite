# Add delivery_date to Purchase Requisition.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0015_pr_workflow_and_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaserequisition",
            name="delivery_date",
            field=models.DateField(blank=True, help_text="Requested or expected delivery date.", null=True),
        ),
    ]
