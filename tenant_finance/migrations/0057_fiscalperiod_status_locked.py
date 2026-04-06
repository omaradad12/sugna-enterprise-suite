# Add LOCKED accounting period status (posting blocked like closed).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0056_journalline_account_nullable_for_drafts"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fiscalperiod",
            name="status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("open", "Open"),
                    ("soft_closed", "Soft closed"),
                    ("hard_closed", "Hard closed"),
                    ("locked", "Locked"),
                ],
                db_index=True,
                default="open",
                max_length=20,
            ),
        ),
    ]
