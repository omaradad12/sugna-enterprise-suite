# Project + bank account dimensions for NGO inter-fund / inter-project transfers

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0037_interfund_transfer_reversal_audit"),
        ("tenant_grants", "0023_project_grant_period_extensions"),
    ]

    operations = [
        migrations.AddField(
            model_name="interfundtransfer",
            name="from_project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="interfund_transfers_from",
                to="tenant_grants.project",
                help_text="Source project (when using project/bank workflow).",
            ),
        ),
        migrations.AddField(
            model_name="interfundtransfer",
            name="to_project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="interfund_transfers_to",
                to="tenant_grants.project",
                help_text="Destination project (when using project/bank workflow).",
            ),
        ),
        migrations.AddField(
            model_name="interfundtransfer",
            name="from_bank_account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="interfund_transfers_out",
                to="tenant_finance.bankaccount",
                help_text="Source bank (GL cash account derived from this record).",
            ),
        ),
        migrations.AddField(
            model_name="interfundtransfer",
            name="to_bank_account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="interfund_transfers_in",
                to="tenant_finance.bankaccount",
                help_text="Destination bank (GL cash account derived from this record).",
            ),
        ),
    ]
