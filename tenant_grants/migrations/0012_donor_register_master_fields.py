# Donor Register master: code, short_name, category, country, website, currency,
# default_restriction_type, default_reporting_frequency, status, notes, updated_at.

import re
from django.db import migrations, models


def backfill_donor_code(apps, schema_editor):
    Donor = apps.get_model("tenant_grants", "Donor")
    db_alias = schema_editor.connection.alias
    used = set()
    for d in Donor.objects.using(db_alias).all():
        base = re.sub(r"[^A-Za-z0-9]+", "-", (d.name or "").strip()).strip("-") or "DONOR"
        base = (base[:40] or "DONOR").upper()
        code = base
        n = 0
        while code in used or Donor.objects.using(db_alias).filter(code=code).exists():
            n += 1
            code = f"{base}-{n}"
        used.add(code)
        d.code = code
        d.status = "active"
        d.save(update_fields=["code", "status"], using=db_alias)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0011_grant_tracking_pipeline_project_manager"),
    ]

    operations = [
        migrations.AddField(
            model_name="donor",
            name="code",
            field=models.CharField(max_length=50, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="donor",
            name="short_name",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="donor",
            name="donor_category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("bilateral", "Bilateral"),
                    ("multilateral", "Multilateral"),
                    ("foundation", "Foundation"),
                    ("corporate", "Corporate"),
                    ("ngo", "NGO"),
                    ("individual", "Individual"),
                    ("other", "Other"),
                ],
                default="other",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="donor",
            name="country",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="donor",
            name="website",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="donor",
            name="preferred_currency",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name="donor",
            name="default_restriction_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("budget_line", "Budget line restriction"),
                    ("procurement", "Procurement rules"),
                    ("reporting", "Reporting requirement"),
                    ("other", "Other"),
                ],
                default="other",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="donor",
            name="default_reporting_frequency",
            field=models.CharField(
                blank=True,
                choices=[
                    ("monthly", "Monthly"),
                    ("quarterly", "Quarterly"),
                    ("annual", "Annual"),
                    ("ad_hoc", "Ad hoc"),
                ],
                default="quarterly",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="donor",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("inactive", "Inactive"),
                    ("archived", "Archived"),
                ],
                default="active",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="donor",
            name="notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="donor",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.RunPython(backfill_donor_code, noop_reverse),
        migrations.AlterField(
            model_name="donor",
            name="code",
            field=models.CharField(max_length=50, unique=True),
        ),
        migrations.AlterField(
            model_name="donor",
            name="donor_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("institution", "Institution"),
                    ("government", "Government"),
                    ("private", "Private"),
                    ("foundation", "Foundation"),
                    ("corporate", "Corporate"),
                    ("other", "Other"),
                ],
                default="institution",
                max_length=20,
            ),
        ),
    ]
