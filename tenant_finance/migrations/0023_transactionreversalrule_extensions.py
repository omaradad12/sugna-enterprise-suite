from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0022_audittrailsetting_user_activity_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="transactionreversalrule",
            name="prevent_edit_after_posting",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "If enabled, posted vouchers cannot be edited; they must be corrected via reversal entries."
                ),
            ),
        ),
        migrations.AddField(
            model_name="transactionreversalrule",
            name="prevent_delete_after_approval",
            field=models.BooleanField(
                default=True,
                help_text="If enabled, approved or posted vouchers cannot be deleted.",
            ),
        ),
        migrations.AddField(
            model_name="transactionreversalrule",
            name="require_reversal_approval",
            field=models.BooleanField(
                default=True,
                help_text="If enabled, reversal journals must be approved before posting.",
            ),
        ),
        migrations.AddField(
            model_name="transactionreversalrule",
            name="authorized_roles_for_reversal",
            field=models.CharField(
                max_length=255,
                blank=True,
                help_text=(
                    "Comma-separated role or permission codes allowed to perform reversals "
                    "(e.g. finance_manager,system_admin)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="transactionreversalrule",
            name="prevent_reversal_if_period_closed",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "If enabled, reversals are blocked when the accounting period is closed."
                ),
            ),
        ),
        migrations.AddField(
            model_name="transactionreversalrule",
            name="prevent_cross_period_reversal",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "If enabled, reversals cannot move amounts across fiscal periods unless explicitly authorized."
                ),
            ),
        ),
        migrations.AddField(
            model_name="transactionreversalrule",
            name="authorized_roles_for_cross_period_reversal",
            field=models.CharField(
                max_length=255,
                blank=True,
                help_text=(
                    "Comma-separated role or permission codes allowed to perform cross-fiscal-period reversals."
                ),
            ),
        ),
    ]

