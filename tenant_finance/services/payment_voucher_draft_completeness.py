"""
Payment voucher draft completeness: Incomplete draft vs Draft for imported / partial saves.

Used by Draft Entry hub, Excel import, payment voucher revision, and submit-for-approval validation.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils.translation import gettext_lazy as _


def _pv_lines(entry: Any, using: str) -> list:
    from tenant_finance.models import JournalLine

    return list(
        JournalLine.objects.using(using)
        .filter(entry_id=entry.pk)
        .select_related("account")
    )


def list_missing_payment_voucher_expense_fields(*, using: str, entry: Any) -> list[str]:
    """
    Human-readable missing field labels for an expense payment voucher (PV-…) in draft-like status.
    """
    from tenant_finance.models import ChartAccount, JournalEntry

    out: list[str] = []
    ref = (entry.reference or "").strip().upper()
    if not ref.startswith("PV-"):
        return out
    st = (entry.source_type or "").strip()
    jt = (entry.journal_type or "").strip().lower()
    if st != JournalEntry.SourceType.PAYMENT_VOUCHER and jt != "payment_voucher":
        return out

    if not getattr(entry, "entry_date", None):
        out.append(str(_("Payment date")))

    if not (entry.memo or "").strip():
        out.append(str(_("Description")))

    if not (entry.payee_name or "").strip():
        out.append(str(_("Payee")))

    if not (entry.payment_method or "").strip():
        out.append(str(_("Payment method")))

    if not getattr(entry, "project_id", None):
        out.append(str(_("Project")))

    if not getattr(entry, "grant_id", None):
        out.append(str(_("Grant")))

    lines = _pv_lines(entry, using)
    expense_line = None
    bank_line = None
    total_dr = Decimal("0")
    total_cr = Decimal("0")
    for ln in lines:
        if not ln.account_id:
            continue
        d = ln.debit or Decimal("0")
        c = ln.credit or Decimal("0")
        total_dr += d
        total_cr += c
        if d > 0 and ln.account and ln.account.type == ChartAccount.Type.EXPENSE:
            expense_line = ln
        if c > 0 and ln.account and ln.account.type == ChartAccount.Type.ASSET:
            bank_line = ln

    if not lines or len(lines) < 2:
        out.append(str(_("Payment details breakdown")))
    elif total_dr != total_cr or total_dr <= 0:
        out.append(str(_("Payment details breakdown")))
    elif not expense_line:
        out.append(str(_("Expense account")))
    elif not bank_line:
        out.append(str(_("Payment account")))

    if entry.grant_id and expense_line and not getattr(expense_line, "project_budget_line_id", None):
        out.append(str(_("Budget code")))

    return out


def payment_voucher_draft_is_complete(*, using: str, entry: Any) -> bool:
    return len(list_missing_payment_voucher_expense_fields(using=using, entry=entry)) == 0


def payment_voucher_hub_row_display(*, using: str, entry: Any) -> dict[str, Any]:
    """Labels for Draft Entry hub table (amount, bank, expense from lines)."""
    from decimal import Decimal

    from tenant_finance.models import ChartAccount

    lines = _pv_lines(entry, using)
    exp = next((ln for ln in lines if (ln.debit or Decimal("0")) > 0 and ln.account_id), None)
    bank = next(
        (
            ln
            for ln in lines
            if (ln.credit or Decimal("0")) > 0
            and ln.account
            and ln.account.type == ChartAccount.Type.ASSET
        ),
        None,
    )
    if not bank:
        bank = next((ln for ln in lines if (ln.credit or Decimal("0")) > 0 and ln.account_id), None)
    amt = exp.debit if exp else Decimal("0")
    missing = list_missing_payment_voucher_expense_fields(using=using, entry=entry)
    st = entry.status
    from tenant_finance.models import JournalEntry

    if st == JournalEntry.Status.INCOMPLETE_DRAFT:
        status_key = "incomplete"
        status_label = str(_("Incomplete draft"))
    elif st == JournalEntry.Status.DRAFT:
        status_key = "draft"
        status_label = str(_("Draft"))
    elif st == JournalEntry.Status.PENDING_APPROVAL:
        status_key = "pending"
        status_label = str(_("Pending approval"))
    elif st == JournalEntry.Status.APPROVED:
        status_key = "approved"
        status_label = str(_("Approved"))
    else:
        status_key = "other"
        status_label = entry.get_status_display()

    return {
        "entry": entry,
        "amount": amt,
        "amount_display": amt,
        "payment_account": (
            f"{bank.account.code} — {bank.account.name}" if bank and bank.account else "—"
        ),
        "expense_account": (
            f"{exp.account.code} — {exp.account.name}" if exp and exp.account else "—"
        ),
        "missing": missing,
        "missing_short": ", ".join(missing[:6]) + ("…" if len(missing) > 6 else ""),
        "status_key": status_key,
        "status_label": status_label,
    }


def refresh_payment_voucher_draft_status(*, using: str, entry: Any) -> str:
    """
    Set JournalEntry.status to DRAFT or INCOMPLETE_DRAFT when entry is still editable (draft-like).
    Returns the new status string.
    """
    from tenant_finance.models import JournalEntry

    if entry.status not in (
        JournalEntry.Status.DRAFT,
        JournalEntry.Status.INCOMPLETE_DRAFT,
    ):
        return entry.status

    if payment_voucher_draft_is_complete(using=using, entry=entry):
        new_st = JournalEntry.Status.DRAFT
    else:
        new_st = JournalEntry.Status.INCOMPLETE_DRAFT

    if entry.status != new_st:
        JournalEntry.objects.using(using).filter(pk=entry.pk).update(status=new_st)
        entry.status = new_st
    return new_st


def assert_payment_voucher_ready_for_approval_submission(*, using: str, entry: Any) -> None:
    """Raises ValueError if voucher cannot leave draft for approval."""
    from tenant_finance.services.journal_posting import assert_payment_voucher_ready_for_submission

    assert_payment_voucher_ready_for_submission(using=using, entry=entry)

    missing = list_missing_payment_voucher_expense_fields(using=using, entry=entry)
    if missing:
        raise ValueError(f"Cannot submit for approval — missing: {', '.join(missing)}")
