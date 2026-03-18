from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0001_initial"),
        ("tenant_grants", "0004_budget_templates"),
    ]

    operations = [
        migrations.AddField(
            model_name="budgetline",
            name="account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="budget_lines",
                to="tenant_finance.chartaccount",
            ),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="description",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]

