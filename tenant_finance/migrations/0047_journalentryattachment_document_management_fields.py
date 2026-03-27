from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0046_payment_voucher_ngo_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="journalentryattachment",
            name="donor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="journal_attachments",
                to="tenant_grants.donor",
            ),
        ),
        migrations.AddField(
            model_name="journalentryattachment",
            name="grant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="journal_attachments",
                to="tenant_grants.grant",
            ),
        ),
        migrations.AddField(
            model_name="journalentryattachment",
            name="linked_record_id",
            field=models.PositiveBigIntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="journalentryattachment",
            name="linked_record_type",
            field=models.CharField(blank=True, db_index=True, max_length=80),
        ),
        migrations.AddField(
            model_name="journalentryattachment",
            name="module",
            field=models.CharField(blank=True, db_index=True, max_length=50),
        ),
        migrations.AddField(
            model_name="journalentryattachment",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="journal_attachments",
                to="tenant_grants.project",
            ),
        ),
        migrations.AddField(
            model_name="journalentryattachment",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("pending_approval", "Pending approval"),
                    ("posted", "Posted"),
                    ("reversed", "Reversed"),
                    ("archived", "Archived"),
                ],
                db_index=True,
                default="draft",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="journalentryattachment",
            name="storage_provider",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="journalentryattachment",
            name="submodule",
            field=models.CharField(blank=True, db_index=True, max_length=50),
        ),
        migrations.AddField(
            model_name="journalentryattachment",
            name="tenant",
            field=models.CharField(blank=True, db_index=True, max_length=120),
        ),
        migrations.AddField(
            model_name="journalentryattachment",
            name="uploaded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="journal_attachments_uploaded",
                to="tenant_users.tenantuser",
            ),
        ),
        migrations.AddField(
            model_name="journalentryattachment",
            name="voucher_number",
            field=models.CharField(blank=True, db_index=True, max_length=120),
        ),
    ]

