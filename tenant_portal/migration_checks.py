"""
Detect whether required migrations are applied on a tenant database alias.
"""

from __future__ import annotations

import logging

from django.db import connections

logger = logging.getLogger(__name__)
from django.db.migrations.recorder import MigrationRecorder

# AccountCategory enterprise fields (is_system, category_type, etc.)
TENANT_FINANCE_ACCOUNT_CATEGORY_0033 = (
    "tenant_finance",
    "0033_accountcategory_enterprise_fields",
)

# ReportingDeadline.project_id and related enterprise fields
TENANT_GRANTS_REPORTING_DEADLINE_0028 = (
    "tenant_grants",
    "0028_reporting_deadline_enterprise",
)

# JournalLine.project_budget_line / workplan_activity (NGO activity-based budgeting)
TENANT_FINANCE_JOURNALLINE_0044 = (
    "tenant_finance",
    "0044_journalline_project_budget_workplan",
)

# ChartAccount.allow_posting (bank dropdowns, GL validation)
TENANT_FINANCE_CHARTACCOUNT_0055 = (
    "tenant_finance",
    "0055_chartaccount_allow_posting",
)

# Project.program_category_code (program dimension vs FundingType enum)
TENANT_GRANTS_PROJECT_0039 = (
    "tenant_grants",
    "0039_project_program_category_code",
)

# BudgetLine.project_id, flat budget_code, drop hierarchy (chains 0041→0042→0043)
TENANT_GRANTS_BUDGETLINE_0043 = (
    "tenant_grants",
    "0043_budgetline_flat_budget_code",
)

# DocumentPolicyConfig + file_sha256 / retention (Document Management policy)
TENANT_DOCUMENTS_POLICY_0002 = (
    "tenant_documents",
    "0002_documentpolicyconfig_document_file_sha256_and_more",
)


def migration_applied(using: str, app_label: str, migration_name: str) -> bool:
    """True if django_migrations records this migration on the given DB alias."""
    try:
        recorder = MigrationRecorder(connections[using])
        return (app_label, migration_name) in recorder.applied_migrations()
    except Exception:
        return False


def tenant_finance_account_categories_ready(using: str) -> bool:
    return migration_applied(using, *TENANT_FINANCE_ACCOUNT_CATEGORY_0033)


def tenant_grants_reporting_deadlines_ready(using: str) -> bool:
    return migration_applied(using, *TENANT_GRANTS_REPORTING_DEADLINE_0028)


def tenant_finance_journalline_project_budget_ready(using: str) -> bool:
    return migration_applied(using, *TENANT_FINANCE_JOURNALLINE_0044)


def tenant_finance_chartaccount_allow_posting_ready(using: str) -> bool:
    return migration_applied(using, *TENANT_FINANCE_CHARTACCOUNT_0055)


def tenant_grants_project_program_category_ready(using: str) -> bool:
    return migration_applied(using, *TENANT_GRANTS_PROJECT_0039)


def tenant_grants_budgetline_schema_ready(using: str) -> bool:
    return migration_applied(using, *TENANT_GRANTS_BUDGETLINE_0043)


def tenant_documents_policy_ready(using: str) -> bool:
    return migration_applied(using, *TENANT_DOCUMENTS_POLICY_0002)


def apply_all_migrations_for_alias(using: str) -> bool:
    """
    Run `manage.py migrate` for the given database alias only.

    Used when TENANT_AUTO_MIGRATE is enabled so tenant schemas catch up after pulls.
    Returns True if the command completed without raising.
    """
    from django.core.management import call_command

    try:
        call_command("migrate", database=using, interactive=False, verbosity=0)
        logger.info("Applied pending migrations for database alias %s", using)
        return True
    except Exception:
        logger.exception("Failed to migrate database alias %s", using)
        return False


def ensure_account_category_schema(using: str, *, auto_migrate: bool) -> bool:
    """
    Return True if AccountCategory enterprise schema is ready.
    If auto_migrate and not ready, run migrate on `using` once and re-check.
    """
    if tenant_finance_account_categories_ready(using):
        return True
    if auto_migrate:
        apply_all_migrations_for_alias(using)
        return tenant_finance_account_categories_ready(using)
    return False


def ensure_reporting_deadline_schema(using: str, *, auto_migrate: bool) -> bool:
    """
    Return True if ReportingDeadline enterprise columns (e.g. project_id) exist.
    If auto_migrate and not ready, run migrate on `using` once and re-check.
    """
    if tenant_grants_reporting_deadlines_ready(using):
        return True
    if auto_migrate:
        apply_all_migrations_for_alias(using)
        return tenant_grants_reporting_deadlines_ready(using)
    return False


def ensure_journalline_project_budget_schema(using: str, *, auto_migrate: bool) -> bool:
    """
    Return True if JournalLine has project_budget_line / workplan_activity columns.
    If auto_migrate and not ready, run migrate on `using` once and re-check.
    """
    if tenant_finance_journalline_project_budget_ready(using):
        return True
    if auto_migrate:
        apply_all_migrations_for_alias(using)
        return tenant_finance_journalline_project_budget_ready(using)
    return False


def ensure_tenant_grants_project_program_category_schema(using: str, *, auto_migrate: bool) -> bool:
    """
    Return True if Project has program_category_code (tenant_grants.0039).
    """
    if tenant_grants_project_program_category_ready(using):
        return True
    if auto_migrate:
        apply_all_migrations_for_alias(using)
        return tenant_grants_project_program_category_ready(using)
    return False


def ensure_tenant_grants_budgetline_schema(using: str, *, auto_migrate: bool) -> bool:
    """
    Return True if BudgetLine has project_id and flat budget_code schema (tenant_grants.0043).
    """
    if tenant_grants_budgetline_schema_ready(using):
        return True
    if auto_migrate:
        apply_all_migrations_for_alias(using)
        return tenant_grants_budgetline_schema_ready(using)
    return False


def ensure_chartaccount_allow_posting_schema(using: str, *, auto_migrate: bool) -> bool:
    """
    Return True if ChartAccount has allow_posting (tenant_finance.0055).
    If auto_migrate and not ready, run migrate on `using` once and re-check.
    """
    if tenant_finance_chartaccount_allow_posting_ready(using):
        return True
    if auto_migrate:
        apply_all_migrations_for_alias(using)
        return tenant_finance_chartaccount_allow_posting_ready(using)
    return False


def ensure_document_policy_schema(using: str, *, auto_migrate: bool) -> bool:
    """
    Return True if DocumentPolicyConfig and related Document fields exist.
    If auto_migrate and not ready, run migrate on `using` once and re-check.
    """
    if tenant_documents_policy_ready(using):
        return True
    if auto_migrate:
        apply_all_migrations_for_alias(using)
        return tenant_documents_policy_ready(using)
    return False
