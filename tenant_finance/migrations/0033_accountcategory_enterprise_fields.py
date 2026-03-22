# Generated manually — enterprise AccountCategory fields

import django.db.models.deletion
from django.db import migrations, models


def populate_category_type_and_balance(apps, schema_editor):
    """
    Must use the same DB as the migration (tenant aliases), not ``default``.
    """
    db = schema_editor.connection.alias
    AccountCategory = apps.get_model("tenant_finance", "AccountCategory")
    # Known NGO seed codes -> (category_type, normal_balance)
    code_map = {
        "CASH": ("asset", "debit"),
        "BANK": ("asset", "debit"),
        "RECEIVABLE": ("asset", "debit"),
        "ADVANCE": ("asset", "debit"),
        "INVENTORY": ("asset", "debit"),
        "FIXED_ASSETS": ("asset", "debit"),
        "PAYABLE": ("liability", "credit"),
        "ACCRUED_LIAB": ("liability", "credit"),
        "FUND_BAL": ("equity", "credit"),
        "REVENUE": ("income", "credit"),
        "PROGRAM_EXP": ("expense", "debit"),
        "STAFF_COSTS": ("expense", "debit"),
        "OPER_EXP": ("expense", "debit"),
        "FINANCE_COSTS": ("expense", "debit"),
        # Top-level defaults (if created by new seed)
        "ASSETS": ("asset", "debit"),
        "LIABILITIES": ("liability", "credit"),
        "EQUITY": ("equity", "credit"),
        "INCOME": ("income", "credit"),
        "EXPENSES": ("expense", "debit"),
    }
    for obj in AccountCategory.objects.using(db).all():
        code = (obj.code or "").strip().upper()
        st = obj.statement_type or ""
        if code in code_map:
            ct, nb = code_map[code]
        elif st == "balance_sheet":
            ct, nb = "asset", "debit"
        elif st == "income_expenditure":
            ct, nb = "expense", "debit"
        elif st == "cash_flow":
            ct, nb = "asset", "debit"
        else:
            ct, nb = "asset", "debit"
        obj.category_type = ct
        obj.normal_balance = nb
        obj.save(using=db, update_fields=["category_type", "normal_balance"])


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0032_grantcomplianceevent_grantcompliancerule_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountcategory",
            name="category_type",
            field=models.CharField(
                choices=[
                    ("asset", "Asset"),
                    ("liability", "Liability"),
                    ("equity", "Equity"),
                    ("income", "Income"),
                    ("expense", "Expense"),
                ],
                default="asset",
                help_text="Account class; must align with statement type (Balance Sheet vs Income & Expenditure).",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="accountcategory",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="accountcategory",
            name="is_system",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Protected NGO default categories; critical fields cannot be edited.",
            ),
        ),
        migrations.AddField(
            model_name="accountcategory",
            name="normal_balance",
            field=models.CharField(
                choices=[("debit", "Debit"), ("credit", "Credit")],
                default="debit",
                help_text="Debit for Assets & Expenses; Credit for Liabilities, Equity, and Income.",
                max_length=10,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="accountcategory",
            name="parent_category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="child_categories",
                to="tenant_finance.accountcategory",
            ),
        ),
        migrations.RunPython(populate_category_type_and_balance, migrations.RunPython.noop),
    ]
