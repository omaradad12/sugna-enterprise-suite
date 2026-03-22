# Inter-fund transfer operational fields + inter_fund_transfer journal source type

from django.db import migrations, models
import django.db.models.deletion


def forwards_interfund_journal_source(apps, schema_editor):
    JournalEntry = apps.get_model("tenant_finance", "JournalEntry")
    InterFundTransfer = apps.get_model("tenant_finance", "InterFundTransfer")
    db = schema_editor.connection.alias
    je_ids = (
        InterFundTransfer.objects.using(db)
        .exclude(posted_journal_id__isnull=True)
        .values_list("posted_journal_id", flat=True)
    )
    je_ids = list({int(x) for x in je_ids if x})
    if je_ids:
        JournalEntry.objects.using(db).filter(pk__in=je_ids).update(
            source="inter_fund_transfer",
            source_type="inter_fund_transfer",
            journal_type="inter_fund_transfer",
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0023_project_grant_period_extensions"),
        ("tenant_finance", "0035_interfund_transfer_enterprise"),
    ]

    operations = [
        migrations.AddField(
            model_name="interfundtransfer",
            name="reference_no",
            field=models.CharField(blank=True, help_text="External reference (PO, bank ref, etc.).", max_length=120),
        ),
        migrations.AddField(
            model_name="interfundtransfer",
            name="donor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="interfund_transfers",
                to="tenant_grants.donor",
            ),
        ),
        migrations.AddField(
            model_name="interfundtransfer",
            name="attachment",
            field=models.FileField(
                blank=True,
                max_length=255,
                null=True,
                upload_to="finance/interfund_attachments/%Y/%m/",
            ),
        ),
        migrations.AddField(
            model_name="interfundtransfer",
            name="planned_posting_date",
            field=models.DateField(
                blank=True,
                help_text="Intended GL posting date (validated when posting to the ledger).",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="journalentry",
            name="source_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("manual", "Manual journal"),
                    ("payment_voucher", "Payment voucher"),
                    ("receipt_voucher", "Receipt voucher"),
                    ("cash_transfer", "Cash transfer"),
                    ("bank_transfer", "Bank transfer"),
                    ("fund_transfer", "Fund transfer"),
                    ("inter_fund_transfer", "Inter-fund transfer"),
                    ("posting_engine", "Posting rule / engine"),
                    ("reversal", "Reversal"),
                    ("opening_balance", "Opening balance"),
                    ("other", "Other"),
                ],
                db_index=True,
                help_text="Type of source transaction that generated this journal.",
                max_length=40,
            ),
        ),
        migrations.RunPython(forwards_interfund_journal_source, noop_reverse),
    ]
