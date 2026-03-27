# Generated manually for receivable logic

from django.db import migrations, models
from django.db.models import F


def forwards_copy_award_to_ceiling(apps, schema_editor):
    from django.db import DatabaseError

    Grant = apps.get_model("tenant_grants", "Grant")
    try:
        Grant.objects.all().update(
            grant_ceiling=F("award_amount"),
            eligible_receivable_amount=F("award_amount"),
        )
    except DatabaseError:
        # Skip if tenant DB has no grant table yet; AddField will still add columns when table exists.
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0030_budgetline_code_required"),
    ]

    operations = [
        migrations.AddField(
            model_name="grant",
            name="grant_ceiling",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Maximum approved funding (total donor commitment).",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="grant",
            name="eligible_receivable_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Amount currently allowed to claim from the donor (eligible expenses, approved tranche, milestones, etc.).",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="grant",
            name="receivable_basis_note",
            field=models.TextField(
                blank=True,
                help_text="Optional: how eligibility is determined (e.g. eligible expenses, approved tranche, milestone).",
            ),
        ),
        migrations.RunPython(forwards_copy_award_to_ceiling, migrations.RunPython.noop),
    ]
