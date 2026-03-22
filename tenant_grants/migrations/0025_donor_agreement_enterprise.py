# Donor Agreement enterprise fields, links, attachments, and indexes.

import django.db.models.deletion
from django.db import migrations, models


def backfill_agreement_codes_and_status(apps, schema_editor):
    DonorAgreement = apps.get_model("tenant_grants", "DonorAgreement")
    db_alias = schema_editor.connection.alias
    qs = DonorAgreement.objects.using(db_alias).all().order_by("pk")
    used = {x for x in qs.values_list("agreement_code", flat=True) if x}
    for a in qs:
        code = f"DAG-{a.pk:05d}"
        n = 0
        while code in used or DonorAgreement.objects.using(db_alias).filter(agreement_code=code).exclude(pk=a.pk).exists():
            n += 1
            code = f"DAG-{a.pk:05d}-{n}"
        used.add(code)
        st = "active" if getattr(a, "signed_date", None) else "draft"
        DonorAgreement.objects.using(db_alias).filter(pk=a.pk).update(
            agreement_code=code,
            status=st,
        )


def noop_reverse(apps, schema_editor):
    pass


def _drop_orphan_agreement_code_unique(apps, schema_editor):
    """Clear partial unique/index from a failed retry (PostgreSQL)."""
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as c:
        c.execute(
            'DROP INDEX IF EXISTS "tenant_grants_donoragreement_agreement_code_05b13ac3_like"'
        )
        for constraint in (
            "tenant_grants_donoragreement_agreement_code_05b13ac3_uniq",
            "tenant_grants_donoragreement_agreement_code_key",
        ):
            c.execute(
                f'ALTER TABLE tenant_grants_donoragreement DROP CONSTRAINT IF EXISTS "{constraint}"'
            )


def _finalize_agreement_code_unique_forwards(apps, schema_editor):
    """
    Set agreement_code NOT NULL + UNIQUE + pattern index on PostgreSQL using
    idempotent DDL. Django's AlterField on PG can raise DuplicateTable for the
    varchar_pattern_ops (_like) index when retrying a partially applied migration.
    """
    if schema_editor.connection.vendor == "postgresql":
        table = "tenant_grants_donoragreement"
        column = "agreement_code"
        like_idx = f"{table}_{column}_05b13ac3_like"
        uniq = f"{table}_{column}_05b13ac3_uniq"
        with schema_editor.connection.cursor() as c:
            c.execute(f'DROP INDEX IF EXISTS "{like_idx}"')
            c.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{uniq}"')
            c.execute(
                f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_{column}_key"
            )
            c.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")
            c.execute(f'ALTER TABLE {table} ADD CONSTRAINT "{uniq}" UNIQUE ({column})')
            c.execute(
                f'CREATE INDEX "{like_idx}" ON {table} ({column} varchar_pattern_ops)'
            )
        return

    model = apps.get_model("tenant_grants", "DonorAgreement")
    old_field = model._meta.get_field("agreement_code")
    new_field = models.CharField(
        max_length=40,
        unique=True,
        help_text="Unique reference (e.g. DAG-2025-00001).",
    )
    new_field.set_attributes_from_name("agreement_code")
    schema_editor.alter_field(model, old_field, new_field)


def _drop_orphan_agreement_code_indexes_first(apps, schema_editor):
    """Run before any 0025 DDL so a half-applied tenant DB can retry."""
    _drop_orphan_agreement_code_unique(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0043_project_master_registry_fields"),
        ("tenant_grants", "0024_project_master_registry_fields"),
    ]

    operations = [
        migrations.RunPython(_drop_orphan_agreement_code_indexes_first, noop_reverse),
        migrations.AddField(
            model_name="donoragreement",
            name="agreement_code",
            field=models.CharField(
                help_text="Unique reference (e.g. DAG-2025-00001).",
                max_length=40,
                null=True,
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="agreement_type",
            field=models.CharField(
                choices=[
                    ("grant", "Grant agreement"),
                    ("framework", "Framework agreement"),
                    ("partnership", "Partnership agreement"),
                    ("contribution", "Contribution agreement"),
                    ("mou", "Memorandum of understanding"),
                ],
                db_index=True,
                default="grant",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="reference_number",
            field=models.CharField(
                blank=True,
                help_text="Donor or legal reference number.",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("active", "Active"),
                    ("expired", "Expired"),
                    ("closed", "Closed"),
                ],
                db_index=True,
                default="draft",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="funding_source",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="donor_agreements",
                to="tenant_grants.fundingsource",
            ),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="currency",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="donor_agreements",
                to="tenant_finance.currency",
            ),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="payment_terms_summary",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="installment_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="reporting_frequency",
            field=models.CharField(
                blank=True,
                choices=[
                    ("monthly", "Monthly"),
                    ("quarterly", "Quarterly"),
                    ("annually", "Annually"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="compliance_financial_reporting",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="compliance_narrative_reporting",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="compliance_audit_required",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="compliance_special_conditions",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="restricted_funding",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="restriction_summary",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="allow_multiple_grants",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="allow_multiple_projects",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="internal_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="donoragreement",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AlterField(
            model_name="donoragreement",
            name="end_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="donoragreement",
            name="signed_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="donoragreement",
            name="start_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(backfill_agreement_codes_and_status, noop_reverse),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="donoragreement",
                    name="agreement_code",
                    field=models.CharField(
                        help_text="Unique reference (e.g. DAG-2025-00001).",
                        max_length=40,
                        unique=True,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    _finalize_agreement_code_unique_forwards,
                    noop_reverse,
                ),
            ],
        ),
        migrations.AlterField(
            model_name="donoragreement",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddIndex(
            model_name="donoragreement",
            index=models.Index(fields=["donor", "status"], name="tenant_gran_donor_i_idx"),
        ),
        migrations.AddIndex(
            model_name="donoragreement",
            index=models.Index(fields=["signed_date"], name="tenant_gran_signed__idx"),
        ),
        migrations.AddIndex(
            model_name="donoragreement",
            index=models.Index(fields=["start_date"], name="tenant_gran_start_d_idx"),
        ),
        migrations.AddIndex(
            model_name="donoragreement",
            index=models.Index(fields=["end_date"], name="tenant_gran_end_dat_idx"),
        ),
        migrations.CreateModel(
            name="DonorAgreementGrant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "agreement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grant_links",
                        to="tenant_grants.donoragreement",
                    ),
                ),
                (
                    "grant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="donor_agreement_links",
                        to="tenant_grants.grant",
                    ),
                ),
            ],
            options={
                "ordering": ["agreement", "grant"],
            },
        ),
        migrations.CreateModel(
            name="DonorAgreementProject",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "agreement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="project_links",
                        to="tenant_grants.donoragreement",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="donor_agreement_links",
                        to="tenant_grants.project",
                    ),
                ),
            ],
            options={
                "ordering": ["agreement", "project"],
            },
        ),
        migrations.CreateModel(
            name="DonorAgreementAttachment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("amendment", "Amendment"),
                            ("supporting", "Supporting document"),
                            ("other", "Other"),
                        ],
                        default="supporting",
                        max_length=20,
                    ),
                ),
                (
                    "file",
                    models.FileField(upload_to="grants/agreement_attachments/%Y/%m/"),
                ),
                ("original_filename", models.CharField(blank=True, max_length=255)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "agreement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="tenant_grants.donoragreement",
                    ),
                ),
            ],
            options={
                "ordering": ["-uploaded_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="donoragreementgrant",
            constraint=models.UniqueConstraint(
                fields=("agreement", "grant"),
                name="uniq_donor_agreement_grant",
            ),
        ),
        migrations.AddConstraint(
            model_name="donoragreementproject",
            constraint=models.UniqueConstraint(
                fields=("agreement", "project"),
                name="uniq_donor_agreement_project",
            ),
        ),
    ]
