# Audit fields for inter-fund transfer reversals (NGO compliance)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_users", "0001_initial"),
        ("tenant_finance", "0036_inter_fund_transfer_fields_and_journal_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="interfundtransfer",
            name="reversed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="interfundtransfer",
            name="reversed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="interfund_transfers_reversed",
                to="tenant_users.tenantuser",
            ),
        ),
    ]
