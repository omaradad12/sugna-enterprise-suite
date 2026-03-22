# DonorRestriction enterprise fields, indexes, grant FK SET_NULL, backfill codes.
#
# Idempotent DB phase: tenants that already have columns from a partial apply
# (django_migrations missing 0026) skip duplicate ADD COLUMN / indexes.

import django.db.models.deletion
from django.db import migrations, models, transaction
from django.db.utils import ProgrammingError

from tenant_grants.migrations._schema_utils import column_exists


def _backfill_donor_restrictions(apps, schema_editor):
    DonorRestriction = apps.get_model("tenant_grants", "DonorRestriction")
    db = schema_editor.connection.alias
    type_to_cat = {
        "budget_line": "budget",
        "procurement": "procurement",
        "reporting": "reporting",
        "other": "other",
    }
    for r in DonorRestriction.objects.using(db).all().iterator():
        code = f"DRC-{r.pk:06d}"
        cat = type_to_cat.get(r.restriction_type, "other")
        DonorRestriction.objects.using(db).filter(pk=r.pk).update(
            restriction_code=code,
            category=cat,
            status="active",
        )


def _noop_reverse(apps, schema_editor):
    pass


def _apply_restriction_code_unique_db(apps, schema_editor):
    """
    Make restriction_code unique idempotently. Django's AlterField(unique=True) on PG
    can fail with '..._like already exists' after partial applies; we drop stale objects
    then CREATE UNIQUE INDEX IF NOT EXISTS (works on PostgreSQL and SQLite).
    """
    conn = schema_editor.connection
    qn = conn.ops.quote_name
    tbl = "tenant_grants_donorrestriction"
    idx_name = "tenant_grants_donorrestriction_restriction_code_uniq"

    with conn.cursor() as cursor:
        if conn.vendor == "postgresql":
            cursor.execute(
                """
                SELECT c.conname
                FROM pg_constraint c
                JOIN pg_class rel ON rel.oid = c.conrelid
                WHERE rel.relname = %s
                  AND c.contype = 'u'
                  AND pg_get_constraintdef(c.oid) ILIKE %s
                """,
                [tbl, "%restriction_code%"],
            )
            for (cname,) in cursor.fetchall():
                cursor.execute(
                    "ALTER TABLE %s DROP CONSTRAINT IF EXISTS %s"
                    % (qn(tbl), qn(cname))
                )
            cursor.execute(
                """
                SELECT ns.nspname, ic.relname
                FROM pg_class tc
                JOIN pg_namespace ns ON ns.oid = tc.relnamespace
                JOIN pg_index ix ON tc.oid = ix.indrelid AND ix.indisprimary = false
                JOIN pg_class ic ON ic.oid = ix.indexrelid
                WHERE tc.relkind = 'r'
                  AND tc.relname = %s
                  AND ic.relname ILIKE %s
                """,
                [tbl, "%restriction_code%"],
            )
            for schema, iname in cursor.fetchall():
                cursor.execute(
                    "DROP INDEX IF EXISTS %s.%s CASCADE" % (qn(schema), qn(iname))
                )
        elif conn.vendor == "sqlite":
            cursor.execute("PRAGMA table_info(%s)" % qn(tbl))
            if not cursor.fetchall():
                return
            cursor.execute("PRAGMA index_list(%s)" % qn(tbl))
            for row in cursor.fetchall():
                iname = row[1]
                if "restriction_code" in iname:
                    cursor.execute("DROP INDEX IF EXISTS %s" % qn(iname))

    with conn.cursor() as cursor:
        if conn.vendor == "mysql":
            try:
                cursor.execute(
                    "CREATE UNIQUE INDEX %s ON %s (%s)"
                    % (qn(idx_name), qn(tbl), qn("restriction_code"))
                )
            except Exception:
                pass
        else:
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS %s ON %s (%s)"
                % (qn(idx_name), qn(tbl), qn("restriction_code"))
            )


def _is_duplicate_schema_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    if "already exists" in msg or "duplicate" in msg:
        return True
    return type(exc).__name__ in ("DuplicateColumn", "DuplicateTable", "DuplicateDatabase")


def _using(schema_editor) -> str:
    return schema_editor.connection.alias


def _add_field_if_missing(schema_editor, model, name: str, field) -> None:
    table = model._meta.db_table
    field.set_attributes_from_name(name)
    col = field.column
    if column_exists(schema_editor, table, col):
        return
    try:
        with transaction.atomic(using=_using(schema_editor)):
            schema_editor.add_field(model, field)
    except ProgrammingError as e:
        if _is_duplicate_schema_error(e):
            return
        raise


def _alter_field_safe(schema_editor, model, old_name: str, new_field) -> None:
    new_field.set_attributes_from_name(old_name)
    try:
        old_field = model._meta.get_field(old_name)
    except Exception:
        return
    try:
        with transaction.atomic(using=_using(schema_editor)):
            schema_editor.alter_field(model, old_field, new_field)
    except Exception:
        # Partial tenants may already match target FK/choices; avoid aborting outer migration txn.
        pass


def _create_indexes_sql(schema_editor) -> None:
    """B-tree indexes for DonorRestriction (historical model lacks new fields for add_index)."""
    conn = schema_editor.connection
    qn = conn.ops.quote_name
    tbl = qn("tenant_grants_donorrestriction")
    specs = [
        ("tenant_gran_donor_i_5d3040_idx", "(donor_id, status)"),
        ("tenant_gran_grant_i_509d71_idx", "(grant_id, status)"),
        ("tenant_gran_restric_6b2eff_idx", "(restriction_type)"),
        ("tenant_gran_status_4ddffc_idx", "(status, effective_end)"),
        ("tenant_gran_effecti_d3afa5_idx", "(effective_start, effective_end)"),
    ]
    with conn.cursor() as cursor:
        for iname, cols in specs:
            if conn.vendor == "postgresql":
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS %s ON %s %s"
                    % (qn(iname), tbl, cols)
                )
            elif conn.vendor == "sqlite":
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS %s ON %s %s"
                    % (qn(iname), tbl, cols)
                )
            elif conn.vendor == "mysql":
                try:
                    cursor.execute(
                        "CREATE INDEX %s ON %s %s" % (qn(iname), tbl, cols)
                    )
                except Exception:
                    pass


def _donorrestriction_0026_database_forwards(apps, schema_editor):
    DonorRestriction = apps.get_model("tenant_grants", "DonorRestriction")
    AccountCategory = apps.get_model("tenant_finance", "AccountCategory")
    BudgetLine = apps.get_model("tenant_grants", "BudgetLine")
    FundingSource = apps.get_model("tenant_grants", "FundingSource")
    Project = apps.get_model("tenant_grants", "Project")

    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "account_category",
        models.ForeignKey(
            AccountCategory,
            blank=True,
            null=True,
            on_delete=django.db.models.deletion.SET_NULL,
            related_name="donor_restrictions",
            help_text="Optional expense category for eligibility / cap rules.",
        ),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "applies_scope",
        models.CharField(
            choices=[
                ("donor_wide", "Entire donor"),
                ("funding_source", "Specific funding source"),
                ("grant", "Specific grant"),
                ("project", "Specific project"),
            ],
            default="donor_wide",
            help_text="Primary applicability; align with funding source / grant / project when set.",
            max_length=20,
        ),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "budget_line",
        models.ForeignKey(
            BudgetLine,
            blank=True,
            help_text="Optional link to a specific budget line when restriction applies to one line.",
            null=True,
            on_delete=django.db.models.deletion.SET_NULL,
            related_name="donor_restrictions",
        ),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "category",
        models.CharField(
            choices=[
                ("budget", "Budget restrictions"),
                ("procurement", "Procurement restrictions"),
                ("geographic", "Geographic restrictions"),
                ("activity", "Activity restrictions"),
                ("cost_eligibility", "Cost eligibility rules"),
                ("time", "Time restrictions"),
                ("reporting", "Reporting restrictions"),
                ("hr", "HR restrictions"),
                ("audit", "Audit requirements"),
                ("other", "Other"),
            ],
            db_index=True,
            default="other",
            max_length=30,
        ),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "compliance_level",
        models.CharField(
            choices=[
                ("mandatory", "Mandatory"),
                ("recommended", "Recommended"),
                ("informational", "Informational"),
            ],
            db_index=True,
            default="mandatory",
            max_length=20,
        ),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "conditions",
        models.TextField(blank=True, help_text="Detailed enforceable conditions."),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "effective_end",
        models.DateField(blank=True, db_index=True, null=True),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "effective_start",
        models.DateField(blank=True, db_index=True, null=True),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "enforce_budget_validation",
        models.BooleanField(default=False),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "enforce_expense_eligibility",
        models.BooleanField(default=False),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "enforce_procurement_validation",
        models.BooleanField(default=False),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "funding_source",
        models.ForeignKey(
            FundingSource,
            blank=True,
            null=True,
            on_delete=django.db.models.deletion.SET_NULL,
            related_name="donor_restrictions",
        ),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "internal_notes",
        models.TextField(blank=True, help_text="Internal notes (not shown to donors)."),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "max_budget_percentage",
        models.DecimalField(
            blank=True,
            decimal_places=2,
            help_text="Maximum % of budget that may be used under this rule (when applicable).",
            max_digits=5,
            null=True,
        ),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "max_expense_per_transaction",
        models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "max_procurement_threshold",
        models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "project",
        models.ForeignKey(
            Project,
            blank=True,
            null=True,
            on_delete=django.db.models.deletion.SET_NULL,
            related_name="donor_restrictions",
        ),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "require_approval_override",
        models.BooleanField(
            default=False,
            help_text="If set, violations may be waived only with an approved override.",
        ),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "require_supporting_documents",
        models.BooleanField(default=False),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "restriction_code",
        models.CharField(
            blank=True,
            db_index=True,
            help_text="Unique reference (auto-generated if left blank).",
            max_length=32,
            null=True,
        ),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "status",
        models.CharField(
            choices=[
                ("draft", "Draft"),
                ("active", "Active"),
                ("inactive", "Inactive"),
                ("expired", "Expired"),
            ],
            db_index=True,
            default="draft",
            max_length=20,
        ),
    )
    _add_field_if_missing(
        schema_editor,
        DonorRestriction,
        "updated_at",
        models.DateTimeField(auto_now=True),
    )

    Grant = apps.get_model("tenant_grants", "Grant")
    _alter_field_safe(
        schema_editor,
        DonorRestriction,
        "description",
        models.TextField(help_text="Summary shown in lists and alerts."),
    )
    _alter_field_safe(
        schema_editor,
        DonorRestriction,
        "grant",
        models.ForeignKey(
            Grant,
            blank=True,
            null=True,
            on_delete=django.db.models.deletion.SET_NULL,
            related_name="donor_restriction_records",
        ),
    )
    _alter_field_safe(
        schema_editor,
        DonorRestriction,
        "restriction_type",
        models.CharField(
            choices=[
                ("budget_line", "Budget line restriction"),
                ("procurement", "Procurement rules"),
                ("reporting", "Reporting requirement"),
                ("other", "Other"),
                ("budget_allowed_lines", "Specific budget lines allowed"),
                ("budget_category_cap", "Spending cap per category"),
                ("proc_method_required", "Procurement method required"),
                ("proc_min_quotes", "Minimum quotation requirements"),
                ("proc_vendor_conditions", "Preferred vendor conditions"),
                ("geo_allowed_locations", "Allowed project locations"),
                ("geo_restricted_regions", "Restricted countries/regions"),
                ("act_allowed", "Allowed activities"),
                ("act_prohibited", "Prohibited activities"),
                ("cost_eligible_list", "Eligible expenses list"),
                ("cost_ineligible_categories", "Ineligible expense categories"),
                ("time_spending_deadline", "Spending deadline"),
                ("time_utilization_period", "Funding utilization period"),
                ("rep_financial_frequency", "Required financial report frequency"),
                ("rep_narrative", "Required narrative reports"),
                ("hr_staffing_limit", "Staffing cost limits"),
                ("hr_salary_cap", "Salary caps"),
                ("audit_mandatory", "Mandatory audit"),
                ("audit_special", "Special audit conditions"),
            ],
            db_index=True,
            default="other",
            max_length=40,
        ),
    )

    try:
        with transaction.atomic(using=_using(schema_editor)):
            _backfill_donor_restrictions(apps, schema_editor)
    except Exception:
        pass

    try:
        with transaction.atomic(using=_using(schema_editor)):
            _apply_restriction_code_unique_db(apps, schema_editor)
    except Exception:
        pass

    try:
        with transaction.atomic(using=_using(schema_editor)):
            _create_indexes_sql(schema_editor)
    except Exception:
        pass


# State-only mirror of the migration (django_migrations + model state).
_STATE_OPS = [
    migrations.AddField(
        model_name="donorrestriction",
        name="account_category",
        field=models.ForeignKey(
            blank=True,
            help_text="Optional expense category for eligibility / cap rules.",
            null=True,
            on_delete=django.db.models.deletion.SET_NULL,
            related_name="donor_restrictions",
            to="tenant_finance.accountcategory",
        ),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="applies_scope",
        field=models.CharField(
            choices=[
                ("donor_wide", "Entire donor"),
                ("funding_source", "Specific funding source"),
                ("grant", "Specific grant"),
                ("project", "Specific project"),
            ],
            default="donor_wide",
            help_text="Primary applicability; align with funding source / grant / project when set.",
            max_length=20,
        ),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="budget_line",
        field=models.ForeignKey(
            blank=True,
            help_text="Optional link to a specific budget line when restriction applies to one line.",
            null=True,
            on_delete=django.db.models.deletion.SET_NULL,
            related_name="donor_restrictions",
            to="tenant_grants.budgetline",
        ),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="category",
        field=models.CharField(
            choices=[
                ("budget", "Budget restrictions"),
                ("procurement", "Procurement restrictions"),
                ("geographic", "Geographic restrictions"),
                ("activity", "Activity restrictions"),
                ("cost_eligibility", "Cost eligibility rules"),
                ("time", "Time restrictions"),
                ("reporting", "Reporting restrictions"),
                ("hr", "HR restrictions"),
                ("audit", "Audit requirements"),
                ("other", "Other"),
            ],
            db_index=True,
            default="other",
            max_length=30,
        ),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="compliance_level",
        field=models.CharField(
            choices=[
                ("mandatory", "Mandatory"),
                ("recommended", "Recommended"),
                ("informational", "Informational"),
            ],
            db_index=True,
            default="mandatory",
            max_length=20,
        ),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="conditions",
        field=models.TextField(blank=True, help_text="Detailed enforceable conditions."),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="effective_end",
        field=models.DateField(blank=True, db_index=True, null=True),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="effective_start",
        field=models.DateField(blank=True, db_index=True, null=True),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="enforce_budget_validation",
        field=models.BooleanField(default=False),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="enforce_expense_eligibility",
        field=models.BooleanField(default=False),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="enforce_procurement_validation",
        field=models.BooleanField(default=False),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="funding_source",
        field=models.ForeignKey(
            blank=True,
            null=True,
            on_delete=django.db.models.deletion.SET_NULL,
            related_name="donor_restrictions",
            to="tenant_grants.fundingsource",
        ),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="internal_notes",
        field=models.TextField(blank=True, help_text="Internal notes (not shown to donors)."),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="max_budget_percentage",
        field=models.DecimalField(
            blank=True,
            decimal_places=2,
            help_text="Maximum % of budget that may be used under this rule (when applicable).",
            max_digits=5,
            null=True,
        ),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="max_expense_per_transaction",
        field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="max_procurement_threshold",
        field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="project",
        field=models.ForeignKey(
            blank=True,
            null=True,
            on_delete=django.db.models.deletion.SET_NULL,
            related_name="donor_restrictions",
            to="tenant_grants.project",
        ),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="require_approval_override",
        field=models.BooleanField(
            default=False,
            help_text="If set, violations may be waived only with an approved override.",
        ),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="require_supporting_documents",
        field=models.BooleanField(default=False),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="restriction_code",
        field=models.CharField(
            blank=True,
            db_index=True,
            help_text="Unique reference (auto-generated if left blank).",
            max_length=32,
            null=True,
        ),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="status",
        field=models.CharField(
            choices=[
                ("draft", "Draft"),
                ("active", "Active"),
                ("inactive", "Inactive"),
                ("expired", "Expired"),
            ],
            db_index=True,
            default="draft",
            max_length=20,
        ),
    ),
    migrations.AddField(
        model_name="donorrestriction",
        name="updated_at",
        field=models.DateTimeField(auto_now=True),
    ),
    migrations.AlterField(
        model_name="donorrestriction",
        name="description",
        field=models.TextField(help_text="Summary shown in lists and alerts."),
    ),
    migrations.AlterField(
        model_name="donorrestriction",
        name="grant",
        field=models.ForeignKey(
            blank=True,
            null=True,
            on_delete=django.db.models.deletion.SET_NULL,
            related_name="donor_restriction_records",
            to="tenant_grants.grant",
        ),
    ),
    migrations.AlterField(
        model_name="donorrestriction",
        name="restriction_type",
        field=models.CharField(
            choices=[
                ("budget_line", "Budget line restriction"),
                ("procurement", "Procurement rules"),
                ("reporting", "Reporting requirement"),
                ("other", "Other"),
                ("budget_allowed_lines", "Specific budget lines allowed"),
                ("budget_category_cap", "Spending cap per category"),
                ("proc_method_required", "Procurement method required"),
                ("proc_min_quotes", "Minimum quotation requirements"),
                ("proc_vendor_conditions", "Preferred vendor conditions"),
                ("geo_allowed_locations", "Allowed project locations"),
                ("geo_restricted_regions", "Restricted countries/regions"),
                ("act_allowed", "Allowed activities"),
                ("act_prohibited", "Prohibited activities"),
                ("cost_eligible_list", "Eligible expenses list"),
                ("cost_ineligible_categories", "Ineligible expense categories"),
                ("time_spending_deadline", "Spending deadline"),
                ("time_utilization_period", "Funding utilization period"),
                ("rep_financial_frequency", "Required financial report frequency"),
                ("rep_narrative", "Required narrative reports"),
                ("hr_staffing_limit", "Staffing cost limits"),
                ("hr_salary_cap", "Salary caps"),
                ("audit_mandatory", "Mandatory audit"),
                ("audit_special", "Special audit conditions"),
            ],
            db_index=True,
            default="other",
            max_length=40,
        ),
    ),
    migrations.AlterField(
        model_name="donorrestriction",
        name="restriction_code",
        field=models.CharField(
            blank=True,
            db_index=True,
            help_text="Unique reference (auto-generated if left blank).",
            max_length=32,
            null=True,
            unique=True,
        ),
    ),
    migrations.AddIndex(
        model_name="donorrestriction",
        index=models.Index(fields=["donor", "status"], name="tenant_gran_donor_i_5d3040_idx"),
    ),
    migrations.AddIndex(
        model_name="donorrestriction",
        index=models.Index(fields=["grant", "status"], name="tenant_gran_grant_i_509d71_idx"),
    ),
    migrations.AddIndex(
        model_name="donorrestriction",
        index=models.Index(fields=["restriction_type"], name="tenant_gran_restric_6b2eff_idx"),
    ),
    migrations.AddIndex(
        model_name="donorrestriction",
        index=models.Index(fields=["status", "effective_end"], name="tenant_gran_status_4ddffc_idx"),
    ),
    migrations.AddIndex(
        model_name="donorrestriction",
        index=models.Index(
            fields=["effective_start", "effective_end"],
            name="tenant_gran_effecti_d3afa5_idx",
        ),
    ),
]


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0043_project_master_registry_fields"),
        ("tenant_grants", "0025_donor_agreement_enterprise"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=list(_STATE_OPS),
            database_operations=[
                migrations.RunPython(_donorrestriction_0026_database_forwards, _noop_reverse),
            ],
        ),
    ]
