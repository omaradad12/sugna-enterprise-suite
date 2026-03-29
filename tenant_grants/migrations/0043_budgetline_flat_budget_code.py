# Flatten budget structure: budget_code field, drop hierarchy flags.

from django.db import migrations, models
import django.db.models.deletion


def forwards_remove_headings(apps, schema_editor):
    BudgetLine = apps.get_model("tenant_grants", "BudgetLine")
    BudgetLine.objects.filter(is_heading=True).delete()


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0042_require_grant_project_budgetline_fks"),
    ]

    operations = [
        migrations.RunPython(forwards_remove_headings, backwards_noop),
        migrations.RemoveConstraint(
            model_name="budgetline",
            name="uniq_budgetline_grant_code",
        ),
        migrations.RenameField(
            model_name="budgetline",
            old_name="budget_line_code",
            new_name="budget_code",
        ),
        migrations.RemoveField(
            model_name="budgetline",
            name="is_heading",
        ),
        migrations.RemoveField(
            model_name="budgetline",
            name="is_posting",
        ),
        migrations.AddConstraint(
            model_name="budgetline",
            constraint=models.UniqueConstraint(
                fields=("grant", "budget_code"),
                name="uniq_budgetline_grant_budget_code",
            ),
        ),
    ]
