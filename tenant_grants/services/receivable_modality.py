"""
Funding modality and tranche rules for grant receivables.

Receivable creation (claimable cap) rules:
- **Advance** instalments: unlocked tranche value counts when ``due_date`` is set and not after today,
  and the row trigger is met (contract signing / expense report / audit flags on the Grant).
- **Retention**: tranche value counts only when ``Grant.final_report_approved`` is True and the trigger is met.
- **Reimbursement** (grant-level modality): no tranche sum; use ``eligible_receivable_amount`` (e.g. tied to
  posted eligible expenses). **Reimbursement** rows under **mixed** modality still add to the tranche cap
  when their trigger is met.
- **Effective eligible** = min(manual ``eligible_receivable_amount``, tranche_unlocked_cap) when a tranche
  cap applies; outstanding receivables use this cap (see ``tenant_finance.services.receivables_register``).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tenant_grants.models import Grant


def _tranche_line_value(tr, ceiling: Decimal) -> Decimal:
    from tenant_grants.models import GrantTranche

    if tr.amount is not None and tr.amount > 0:
        return min(tr.amount, ceiling)
    if tr.percentage is not None and tr.percentage > 0:
        return (ceiling * (tr.percentage / Decimal("100"))).quantize(Decimal("0.01"))
    return Decimal("0")


def _trigger_met(tr, grant: Grant, today: date) -> bool:
    from tenant_grants.models import GrantTranche

    if tr.trigger_condition == GrantTranche.TriggerCondition.CONTRACT_SIGNING:
        sd = grant.signed_date
        return bool(sd and sd <= today)
    if tr.trigger_condition == GrantTranche.TriggerCondition.EXPENSE_REPORT_APPROVAL:
        return bool(grant.expense_report_approved)
    if tr.trigger_condition == GrantTranche.TriggerCondition.AUDIT_APPROVAL:
        return bool(grant.audit_approved)
    if tr.trigger_condition == GrantTranche.TriggerCondition.MILESTONE_COMPLETED:
        return bool(grant.expense_report_approved and grant.audit_approved)
    return False


def tranche_unlocked_cap(grant: Grant, today: date | None = None) -> Decimal | None:
    """
    Sum of tranche values that are "unlocked" by due date, retention/final report, and triggers.
    Returns None when tranche rules do not apply (use manual eligible only).
    """
    from django.utils import timezone

    from tenant_grants.models import Grant, GrantTranche

    today = today or timezone.localdate()

    fm = (grant.funding_method or "").strip()
    if fm == Grant.FundingMethod.REIMBURSEMENT:
        return None

    tranches = list(grant.tranches.order_by("sort_order", "tranche_no"))
    if not tranches:
        return None

    ceiling = grant.grant_ceiling or grant.award_amount or Decimal("0")
    if ceiling <= 0:
        return Decimal("0")

    advance_family = (
        GrantTranche.PaymentType.ADVANCE,
        GrantTranche.PaymentType.INSTALMENT,
        GrantTranche.PaymentType.MILESTONE_BASED,
    )
    total = Decimal("0")
    for tr in tranches:
        if tr.payment_type in advance_family:
            if tr.due_date and tr.due_date > today:
                continue
            if not _trigger_met(tr, grant, today):
                continue
            total += _tranche_line_value(tr, ceiling)
        elif tr.payment_type == GrantTranche.PaymentType.RETENTION:
            if not grant.final_report_approved:
                continue
            if not _trigger_met(tr, grant, today):
                continue
            total += _tranche_line_value(tr, ceiling)
        elif tr.payment_type == GrantTranche.PaymentType.REIMBURSEMENT:
            if not _trigger_met(tr, grant, today):
                continue
            total += _tranche_line_value(tr, ceiling)

    return min(total, ceiling)


def effective_eligible_for_claimable(grant: Grant, today: date | None = None) -> Decimal:
    """
    Eligible amount used for remaining claimable and outstanding receivable caps.
    Applies min(manual eligible, tranche cap) when tranche_unlocked_cap returns a value.
    """
    from decimal import Decimal

    from django.utils import timezone

    today = today or timezone.localdate()

    manual = grant.eligible_receivable_amount
    if manual is None or manual < 0:
        manual = Decimal("0")
    cap = tranche_unlocked_cap(grant, today)
    if cap is None:
        return manual
    return min(manual, cap)
