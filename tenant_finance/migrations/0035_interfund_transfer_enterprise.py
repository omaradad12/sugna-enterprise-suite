# Enterprise inter-fund transfer fields + workflow status values

from django.db import migrations, models
import django.db.models.deletion


def forwards_status_and_numbers(apps, schema_editor):
    from django.db.models import Q

    InterFundTransfer = apps.get_model("tenant_finance", "InterFundTransfer")
    db = schema_editor.connection.alias
    InterFundTransfer.objects.using(db).filter(status="pending_approval").update(status="submitted")
    qs = InterFundTransfer.objects.using(db).filter(Q(transfer_no__isnull=True) | Q(transfer_no=""))
    for row in qs.iterator():
        td = getattr(row, "transfer_date", None)
        y = td.year if td else row.id
        no = f"IFT-{y}-{row.id:06d}"
        InterFundTransfer.objects.using(db).filter(pk=row.pk).update(transfer_no=no)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0034_journalentry_posting_metadata"),
        ("tenant_grants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="interfundtransfer",
            name="transfer_no",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Auto-assigned transfer number (e.g. IFT-2025-000042).",
                max_length=40,
                null=True,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name="interfundtransfer",
            name="posting_date",
            field=models.DateField(blank=True, help_text="GL posting date (set when posted).", null=True),
        ),
        migrations.AddField(
            model_name="interfundtransfer",
            name="description",
            field=models.TextField(blank=True, help_text="Business description / memo for the transfer."),
        ),
        migrations.AddField(
            model_name="interfundtransfer",
            name="currency",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="interfund_transfers",
                to="tenant_finance.currency",
            ),
        ),
        migrations.AddField(
            model_name="interfundtransfer",
            name="from_grant",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional: source fund as grant/project (enforces active/closed rules).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="interfund_transfers_out",
                to="tenant_grants.grant",
            ),
        ),
        migrations.AddField(
            model_name="interfundtransfer",
            name="to_grant",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional: destination fund as grant/project.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="interfund_transfers_in",
                to="tenant_grants.grant",
            ),
        ),
        migrations.AddField(
            model_name="interfundtransfer",
            name="reversal_journal",
            field=models.ForeignKey(
                blank=True,
                help_text="Reversal journal when a posted transfer was reversed.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="interfund_transfer_reversals",
                to="tenant_finance.journalentry",
            ),
        ),
        migrations.AlterField(
            model_name="interfundtransfer",
            name="reason",
            field=models.TextField(blank=True, help_text="Legacy / extended notes (kept for compatibility)."),
        ),
        migrations.AlterField(
            model_name="interfundtransfer",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("submitted", "Submitted"),
                    ("approved", "Approved"),
                    ("posted", "Posted"),
                    ("rejected", "Rejected"),
                    ("reversed", "Reversed"),
                ],
                db_index=True,
                default="draft",
                max_length=30,
            ),
        ),
        migrations.RunPython(forwards_status_and_numbers, noop_reverse),
    ]
