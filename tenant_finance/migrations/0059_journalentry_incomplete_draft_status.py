# Add incomplete_draft to JournalEntry.status choices (staging for imported PVs).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0058_journalentry_project_duplicate_detection"),
    ]

    operations = [
        migrations.AlterField(
            model_name="journalentry",
            name="status",
            field=models.CharField(
                choices=[
                    ("incomplete_draft", "Incomplete draft"),
                    ("draft", "Draft"),
                    ("pending_approval", "Pending Approval"),
                    ("approved", "Approved"),
                    ("posted", "Posted"),
                    ("reversed", "Reversed"),
                ],
                db_index=True,
                default="draft",
                max_length=20,
            ),
        ),
    ]
