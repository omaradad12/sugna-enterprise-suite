# Generated manually for Funds & Donors

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def default_created_at():
    return timezone.now()


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0002_grantapproval"),
    ]

    operations = [
        migrations.AddField(
            model_name="donor",
            name="donor_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("institution", "Institution"),
                    ("government", "Government"),
                    ("private", "Private"),
                ],
                default="institution",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="donor",
            name="phone",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="donor",
            name="address",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="donor",
            name="contact_person",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="donor",
            name="agreement_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="donor",
            name="created_at",
            field=models.DateTimeField(blank=True, default=default_created_at, null=True),
        ),
        migrations.CreateModel(
            name="FundingSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("funding_type", models.CharField(choices=[("grant", "Grant"), ("donation", "Donation"), ("contribution", "Contribution")], default="grant", max_length=20)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("donor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="funding_sources", to="tenant_grants.donor")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="DonorAgreement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("signed_date", models.DateField(blank=True, null=True)),
                ("funding_limit", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("terms_summary", models.TextField(blank=True)),
                ("file", models.FileField(blank=True, null=True, upload_to="grants/agreements/%Y/%m/")),
                ("original_filename", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("donor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="agreements", to="tenant_grants.donor")),
            ],
            options={"ordering": ["-signed_date", "-created_at"]},
        ),
        migrations.CreateModel(
            name="DonorRestriction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("restriction_type", models.CharField(choices=[("budget_line", "Budget line restriction"), ("procurement", "Procurement rules"), ("reporting", "Reporting requirement"), ("other", "Other")], default="other", max_length=20)),
                ("description", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("donor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="restrictions", to="tenant_grants.donor")),
                ("grant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="donor_restrictions", to="tenant_grants.grant")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ReportingRequirement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("format_description", models.CharField(blank=True, max_length=255)),
                ("frequency", models.CharField(blank=True, choices=[("monthly", "Monthly"), ("quarterly", "Quarterly"), ("annual", "Annual"), ("ad_hoc", "Ad hoc")], default="quarterly", max_length=20)),
                ("template_notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("donor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reporting_requirements", to="tenant_grants.donor")),
            ],
            options={"ordering": ["donor", "name"]},
        ),
        migrations.CreateModel(
            name="GrantAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("percentage", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("donor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="grant_allocations", to="tenant_grants.donor")),
                ("grant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocations", to="tenant_grants.grant")),
            ],
            options={"ordering": ["grant", "donor"], "unique_together": {("grant", "donor")}},
        ),
        migrations.CreateModel(
            name="ReportingDeadline",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("deadline_date", models.DateField()),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("submitted", "Submitted"), ("overdue", "Overdue")], db_index=True, default="pending", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("donor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="reporting_deadlines", to="tenant_grants.donor")),
                ("grant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="reporting_deadlines", to="tenant_grants.grant")),
                ("requirement", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="deadlines", to="tenant_grants.reportingrequirement")),
            ],
            options={"ordering": ["deadline_date", "id"]},
        ),
    ]
