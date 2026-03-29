# Generated manually for payee autocomplete linkage on payment vouchers.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0052_sector_dimension_values"),
    ]

    operations = [
        migrations.AddField(
            model_name="journalentry",
            name="payee_ref_id",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="PK of Supplier, TenantUser, or Donor when payee_ref_type references master data.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="journalentry",
            name="payee_ref_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("supplier", "Supplier / vendor"),
                    ("employee", "Staff / employee"),
                    ("donor", "Donor (master)"),
                    ("history", "Previously used payee"),
                    ("manual", "Manual / new"),
                ],
                default="",
                help_text="When set with payee_ref_id (where applicable), payee_name matches master data.",
                max_length=20,
            ),
        ),
    ]
