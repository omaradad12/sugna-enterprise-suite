# Journal workflow audit: submitted by/at, approved at (enterprise NGO)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0040_adjusting_journal_ngo"),
        ("tenant_users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="journalentry",
            name="submitted_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="When the journal was submitted for approval (draft → pending approval).",
            ),
        ),
        migrations.AddField(
            model_name="journalentry",
            name="submitted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="journal_entries_submitted",
                to="tenant_users.tenantuser",
            ),
        ),
        migrations.AddField(
            model_name="journalentry",
            name="approved_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="When the journal was approved (pending approval → approved).",
            ),
        ),
    ]
