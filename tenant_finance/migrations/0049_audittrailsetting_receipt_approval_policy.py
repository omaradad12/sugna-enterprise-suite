from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0048_bankaccount_enterprise_controls"),
    ]

    operations = [
        migrations.AddField(
            model_name="audittrailsetting",
            name="receipt_approval_mode",
            field=models.CharField(
                choices=[
                    ("no_approval", "No approval required"),
                    ("above_amount", "Approval required above configurable amount"),
                    ("cash_only", "Approval required for cash receipts only"),
                    ("donor_only", "Approval required for donor receipts only"),
                ],
                default="no_approval",
                help_text="Optional approval policy for receipt transactions.",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="audittrailsetting",
            name="receipt_approval_threshold",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Threshold amount used when mode is 'Approval required above configurable amount'.",
                max_digits=14,
            ),
        ),
    ]
