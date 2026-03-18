from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0028_budget_override_requests"),
        ("tenant_grants", "0023_project_grant_period_extensions"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectdimensionmapping",
            name="status",
            field=models.CharField(
                blank=True,
                choices=[("active", "Active"), ("inactive", "Inactive")],
                db_index=True,
                default="active",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="projectdimensionmapping",
            name="active_from",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="projectdimensionmapping",
            name="active_to",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="projectdimensionmapping",
            name="budget_line",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional default budget line for postings on this project.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenant_grants.budgetline",
            ),
        ),
        migrations.AddField(
            model_name="projectdimensionmapping",
            name="default_debit_account",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional default debit account (fallback when posting rules are not configured).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenant_finance.chartaccount",
            ),
        ),
        migrations.AddField(
            model_name="projectdimensionmapping",
            name="default_credit_account",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional default credit account (fallback when posting rules are not configured).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="tenant_finance.chartaccount",
            ),
        ),
    ]

