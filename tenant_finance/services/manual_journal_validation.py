"""
Validation rules for manual general journal entries (balanced lines, posting accounts, open periods).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils.translation import gettext as _


def _dec(x: Any) -> Decimal:
    try:
        return Decimal(str(x or "0").replace(",", ""))
    except Exception:
        return Decimal("0")


def validate_manual_journal_lines(
    *,
    tenant_db: str,
    lines: list[dict],
    require_line_description: bool = True,
) -> list[str]:
    """
    Line-level rules: min 2 lines, at least one debit and one credit, balanced, posting accounts only.
    Each line dict: account_id, description, debit, credit.
    """
    from tenant_finance.models import ChartAccount

    errors: list[str] = []
    if len(lines) < 2:
        errors.append(str(_("A journal must have at least two lines with accounts.")))
        return errors

    total_debit = Decimal("0")
    total_credit = Decimal("0")
    has_positive_debit = False
    has_positive_credit = False

    for idx, line in enumerate(lines, start=1):
        account_id = line.get("account_id")
        debit = _dec(line.get("debit"))
        credit = _dec(line.get("credit"))
        desc = (line.get("description") or "").strip() if line.get("description") is not None else ""

        if not account_id:
            errors.append(str(_("Line %(n)s: account is required.") % {"n": idx}))
            continue

        if debit > 0 and credit > 0:
            errors.append(str(_("Line %(n)s: enter either a debit or a credit, not both.") % {"n": idx}))
            continue
        if debit <= 0 and credit <= 0:
            errors.append(
                str(_("Line %(n)s: amount must be greater than zero on the debit or credit side.") % {"n": idx})
            )
            continue
        if debit < 0 or credit < 0:
            errors.append(str(_("Line %(n)s: negative amounts are not allowed.") % {"n": idx}))
            continue

        if require_line_description and not desc:
            errors.append(str(_("Line %(n)s: line description is required.") % {"n": idx}))

        account = (
            ChartAccount.objects.using(tenant_db)
            .filter(pk=account_id)
            .first()
        )
        if not account:
            errors.append(str(_("Line %(n)s: account not found.") % {"n": idx}))
            continue
        if not account.is_active:
            errors.append(
                str(_("Line %(n)s: account %(code)s is inactive and cannot be posted to.") % {"n": idx, "code": account.code})
            )
        if not account.allow_posting:
            errors.append(
                str(
                    _(
                        "Line %(n)s: account %(code)s — %(name)s is a summary or header account "
                        "(posting is not allowed). Select a detail account under this header."
                    )
                    % {"n": idx, "code": account.code, "name": account.name}
                )
            )
        code = (account.code or "").strip()
        if code == "1200":
            errors.append(
                str(
                    _(
                        "Line %(n)s: account 1200 (Bank Accounts) is a parent header — post to a specific bank account under it."
                    )
                    % {"n": idx}
                )
            )

        if debit > 0:
            has_positive_debit = True
        if credit > 0:
            has_positive_credit = True
        total_debit += debit
        total_credit += credit

    if not has_positive_debit or not has_positive_credit:
        errors.append(str(_("The journal must include at least one debit line and one credit line.")))

    if total_debit != total_credit:
        errors.append(
            str(
                _("Total debit (%(d)s) must equal total credit (%(c)s).")
                % {"d": total_debit, "c": total_credit}
            )
        )

    return errors


def validate_manual_journal_header(
    *,
    tenant_db: str,
    entry_date,
    posting_date,
    memo: str,
    accounting_period_id: str | None,
) -> list[str]:
    """Header rules: dates, memo, accounting period matches posting date and is open."""
    from tenant_finance.models import FiscalPeriod
    from tenant_finance.services.period_control import get_open_period_for_date

    errors: list[str] = []
    if not entry_date:
        errors.append(str(_("Journal date is required.")))
    if not posting_date:
        errors.append(str(_("Posting date is required.")))
    memo_s = (memo or "").strip()
    if not memo_s:
        errors.append(str(_("Description (memo) is required.")))

    if entry_date:
        try:
            get_open_period_for_date(using=tenant_db, dt=entry_date)
        except ValueError as exc:
            errors.append(str(exc))

    ap_raw = (accounting_period_id or "").strip()
    if not ap_raw.isdigit():
        errors.append(str(_("Accounting period is required.")))
    else:
        fp = (
            FiscalPeriod.objects.using(tenant_db)
            .select_related("fiscal_year")
            .filter(pk=int(ap_raw))
            .first()
        )
        if not fp:
            errors.append(str(_("Invalid accounting period.")))
        elif posting_date and (posting_date < fp.start_date or posting_date > fp.end_date):
            errors.append(str(_("Posting date must fall within the selected accounting period.")))
        elif posting_date and fp:
            try:
                ctrl = get_open_period_for_date(using=tenant_db, dt=posting_date)
                if ctrl.accounting_period_id != fp.id:
                    errors.append(
                        str(
                            _(
                                "The open fiscal calendar for this posting date does not match the selected accounting period."
                            )
                        )
                    )
            except ValueError as exc:
                errors.append(str(exc))

    return errors


def validate_journal_entry_lines_from_model(
    *,
    tenant_db: str,
    entry,
) -> list[str]:
    """Build line dicts from a JournalEntry and validate (submit/post)."""
    from tenant_finance.models import JournalLine

    lines = []
    for ln in JournalLine.objects.using(tenant_db).filter(entry_id=entry.pk).order_by("id"):
        lines.append(
            {
                "account_id": ln.account_id,
                "description": ln.description or "",
                "debit": ln.debit,
                "credit": ln.credit,
            }
        )
    return validate_manual_journal_lines(tenant_db=tenant_db, lines=lines, require_line_description=True)


def map_journal_type_to_source_type(journal_type: str) -> str:
    """Map manual journal_type form value to JournalEntry.SourceType."""
    from tenant_finance.models import JournalEntry

    jt = (journal_type or "").strip().lower()
    if jt == "opening_balance":
        return JournalEntry.SourceType.OPENING_BALANCE
    return JournalEntry.SourceType.MANUAL
