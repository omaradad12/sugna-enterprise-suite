# Payment voucher NGO: exchange rate, due date, attachment category

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0045_grant_financial_report_proxies"),
    ]

    operations = [
        migrations.AddField(
            model_name="journalentry",
            name="exchange_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=8,
                help_text="Functional currency exchange rate when voucher currency differs from base (optional).",
                max_digits=18,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="journalentry",
            name="payment_due_date",
            field=models.DateField(
                blank=True,
                help_text="Expected payment date for payables / cash planning (optional).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="journalentryattachment",
            name="document_category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("invoice", "Invoice"),
                    ("receipt", "Receipt"),
                    ("approval_memo", "Approval memo"),
                    ("other", "Other"),
                ],
                db_index=True,
                help_text="NGO source document type for audit and donor reporting.",
                max_length=32,
            ),
        ),
    ]
