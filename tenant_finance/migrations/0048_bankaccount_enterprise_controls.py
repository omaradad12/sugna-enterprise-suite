from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0047_journalentryattachment_document_management_fields"),
        ("tenant_grants", "0030_budgetline_code_required"),
    ]

    operations = [
        migrations.AddField(
            model_name="bankaccount",
            name="account_type",
            field=models.CharField(
                choices=[
                    ("operating", "Operating"),
                    ("project", "Project"),
                    ("restricted", "Restricted"),
                    ("petty_cash", "Petty Cash"),
                ],
                db_index=True,
                default="operating",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="bankaccount",
            name="linked_grant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="linked_bank_accounts",
                related_query_name="linked_bank_account",
                to="tenant_grants.grant",
            ),
        ),
        migrations.AddField(
            model_name="bankaccount",
            name="is_default_operating",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="bankaccount",
            name="linked_project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="linked_bank_accounts",
                related_query_name="linked_bank_account",
                to="tenant_grants.project",
            ),
        ),
        migrations.AddConstraint(
            model_name="bankaccount",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default_operating", True)),
                fields=("is_default_operating",),
                name="uniq_single_default_operating_bank",
            ),
        ),
    ]

