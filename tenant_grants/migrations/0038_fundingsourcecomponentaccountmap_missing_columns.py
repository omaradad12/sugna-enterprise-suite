from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tenant_finance", "0050_journalentry_receipt_stream"),
        ("tenant_grants", "0037_modality_component_account_map"),
    ]

    operations = [
        migrations.AddField(
            model_name="fundingsourcecomponentaccountmap",
            name="deferred_income_account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="funding_modality_deferred_income_maps",
                to="tenant_finance.chartaccount",
            ),
        ),
        migrations.AddField(
            model_name="fundingsourcecomponentaccountmap",
            name="retention_account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="funding_modality_retention_maps",
                to="tenant_finance.chartaccount",
            ),
        ),
    ]
