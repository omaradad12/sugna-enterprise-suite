from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0004_bank_accounts"),
        ("tenant_grants", "0006_grantassignment"),
    ]

    operations = [
        migrations.AddField(
            model_name="grant",
            name="bank_account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="tenant_finance.bankaccount",
                null=True,
                blank=True,
                help_text="Primary bank account where donor funds are received for this grant.",
            ),
        ),
    ]

