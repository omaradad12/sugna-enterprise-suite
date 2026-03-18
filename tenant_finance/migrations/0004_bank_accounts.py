from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0003_core_accounting_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="BankAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("bank_name", models.CharField(max_length=120)),
                ("account_name", models.CharField(max_length=150)),
                ("account_number", models.CharField(max_length=60, unique=True)),
                ("branch", models.CharField(max_length=120, blank=True)),
                ("description", models.CharField(max_length=255, blank=True)),
                ("office", models.CharField(max_length=120, blank=True)),
                ("opening_balance", models.DecimalField(max_digits=14, decimal_places=2, default=0)),
                ("opening_balance_date", models.DateField(null=True, blank=True)),
                ("is_active", models.BooleanField(default=True, db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("account", models.ForeignKey(on_delete=models.PROTECT, to="tenant_finance.chartaccount")),
                ("currency", models.ForeignKey(on_delete=models.PROTECT, to="tenant_finance.currency")),
            ],
            options={
                "ordering": ["bank_name", "account_name"],
            },
        ),
    ]

