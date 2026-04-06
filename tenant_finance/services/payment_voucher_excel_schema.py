"""
Payment voucher draft Excel import — column definitions aligned with the Payment Entry form.

`PAYMENT_VOUCHER_EXCEL_COLUMNS` order and gettext strings must stay in sync with:
`tenant_portal/templates/tenant_portal/pay/payment_vouchers.html` (same labels as form fields).

Import normalizes headers via `_norm_header` (see `draft_entry_excel_import`); legacy machine keys
remain accepted for older files.
"""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

# One row per form field, same order as the Payment Entry form (top → bottom, section flow).
PAYMENT_VOUCHER_EXCEL_COLUMNS: tuple = (
    _("Payment date"),
    _("Payee"),
    _("Payment method"),
    _("Bank/Cash account"),
    _("Project"),
    _("Grant"),
    _("Budget code"),
    _("Expense account"),
    _("Amount"),
    _("Reference"),
    _("Description"),
    _("Supporting attachment"),
    _("Optional note"),
)

# Logical field keys used by the importer (stable English tokens).
PV_FIELD_ENTRY_DATE = "entry_date"
PV_FIELD_PAYEE = "payee"
PV_FIELD_PAYMENT_METHOD = "payment_method"
PV_FIELD_BANK_ACCOUNT = "bank_account"
PV_FIELD_PROJECT = "project"
PV_FIELD_GRANT = "grant"
PV_FIELD_BUDGET_CODE = "budget_code"
PV_FIELD_EXPENSE_ACCOUNT = "expense_account"
PV_FIELD_AMOUNT = "amount"
PV_FIELD_REFERENCE = "reference"
PV_FIELD_DESCRIPTION = "description"
PV_FIELD_SUPPORTING_ATTACHMENT = "supporting_attachment"
PV_FIELD_OPTIONAL_NOTE = "optional_note"

PAYMENT_VOUCHER_FIELD_ORDER: tuple[str, ...] = (
    PV_FIELD_ENTRY_DATE,
    PV_FIELD_PAYEE,
    PV_FIELD_PAYMENT_METHOD,
    PV_FIELD_BANK_ACCOUNT,
    PV_FIELD_PROJECT,
    PV_FIELD_GRANT,
    PV_FIELD_BUDGET_CODE,
    PV_FIELD_EXPENSE_ACCOUNT,
    PV_FIELD_AMOUNT,
    PV_FIELD_REFERENCE,
    PV_FIELD_DESCRIPTION,
    PV_FIELD_SUPPORTING_ATTACHMENT,
    PV_FIELD_OPTIONAL_NOTE,
)

# Extra normalized header aliases (ASCII slugs) accepted for backwards compatibility.
PAYMENT_VOUCHER_LEGACY_ALIASES: dict[str, tuple[str, ...]] = {
    PV_FIELD_ENTRY_DATE: ("entry_date", "payment_date", "voucher_date", "date", "journal_date"),
    PV_FIELD_PAYEE: ("payee", "payee_name"),
    PV_FIELD_PAYMENT_METHOD: ("payment_method", "method"),
    PV_FIELD_BANK_ACCOUNT: (
        "bankcash_account",
        "payment_account_id",
        "bank_gl_code",
        "bank_account_gl",
        "bank_account",
    ),
    PV_FIELD_PROJECT: ("project", "project_code", "project_id"),
    PV_FIELD_GRANT: ("grant", "grant_code", "grant_id"),
    PV_FIELD_BUDGET_CODE: ("budget_code", "budget_line_id", "budgetline_id", "budgetcode"),
    PV_FIELD_EXPENSE_ACCOUNT: ("expense_account", "expense_gl_code", "expense"),
    PV_FIELD_AMOUNT: ("amount", "total"),
    PV_FIELD_REFERENCE: ("reference", "reference_no", "external_reference"),
    PV_FIELD_DESCRIPTION: ("description", "memo", "purpose"),
    PV_FIELD_SUPPORTING_ATTACHMENT: ("supporting_attachment", "attach_invoice"),
    PV_FIELD_OPTIONAL_NOTE: ("optional_note", "budget_override_comment"),
}


def payment_voucher_excel_header_strings() -> list[str]:
    """Headers for the downloadable .xlsx (active locale)."""
    from django.utils.translation import gettext as _

    return [str(_(col)) for col in PAYMENT_VOUCHER_EXCEL_COLUMNS]
