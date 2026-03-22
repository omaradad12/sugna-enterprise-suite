# Generated manually for enterprise journal register / source tracking

from django.db import migrations, models
import django.db.models.deletion


def backfill_journal_metadata(apps, schema_editor):
    JournalEntry = apps.get_model("tenant_finance", "JournalEntry")
    db = schema_editor.connection.alias
    for je in JournalEntry.objects.using(db).iterator():
        ref = (je.reference or "").strip()
        src = (getattr(je, "source", None) or "").strip()
        uf = []
        if ref.upper().startswith("PV-"):
            if not je.source_type:
                je.source_type = "payment_voucher"
                uf.append("source_type")
            if not je.journal_type:
                je.journal_type = "payment_voucher"
                uf.append("journal_type")
            if not je.is_system_generated:
                je.is_system_generated = True
                uf.append("is_system_generated")
            if not je.source_document_no:
                je.source_document_no = ref
                uf.append("source_document_no")
            if not je.source:
                je.source = "payment_voucher"
                uf.append("source")
        elif ref.upper().startswith("RV-"):
            if not je.source_type:
                je.source_type = "receipt_voucher"
                uf.append("source_type")
            if not je.journal_type:
                je.journal_type = "receipt_voucher"
                uf.append("journal_type")
            if not je.is_system_generated:
                je.is_system_generated = True
                uf.append("is_system_generated")
            if not je.source_document_no:
                je.source_document_no = ref
                uf.append("source_document_no")
            if not je.source:
                je.source = "receipt_voucher"
                uf.append("source")
        elif src == "manual":
            if not je.source_type:
                je.source_type = "manual"
                uf.append("source_type")
        elif src == "reversal":
            if not je.source_type:
                je.source_type = "reversal"
                uf.append("source_type")
            if not je.journal_type:
                je.journal_type = "reversal"
                uf.append("journal_type")
            if not je.is_system_generated:
                je.is_system_generated = True
                uf.append("is_system_generated")
        if uf:
            je.save(using=db, update_fields=list(dict.fromkeys(uf)))


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0033_accountcategory_enterprise_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="journalentry",
            name="journal_type",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Manual: adjustment, accrual, correction, opening_balance, reversal. System: payment_voucher, receipt_voucher, cash_transfer, bank_transfer, fund_transfer, transaction.",
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="journalentry",
            name="is_system_generated",
            field=models.BooleanField(db_index=True, default=False, help_text="True when created from vouchers, transfers, or posting engine (not manual JE UI)."),
        ),
        migrations.AddField(
            model_name="journalentry",
            name="posted_by",
            field=models.ForeignKey(
                blank=True,
                help_text="User who posted the journal to the general ledger.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="journal_entries_posted",
                to="tenant_users.tenantuser",
            ),
        ),
        migrations.AddField(
            model_name="journalentry",
            name="source_document_no",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Business document number (PV-…, RV-…, transfer ref, etc.).",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="journalentry",
            name="source_id",
            field=models.PositiveBigIntegerField(
                blank=True,
                db_index=True,
                help_text="Primary key of the source document (voucher header, transfer record, etc.).",
                null=True,
            ),
        ),
        migrations.AddField(
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
        migrations.RunPython(backfill_journal_metadata, migrations.RunPython.noop),
    ]
