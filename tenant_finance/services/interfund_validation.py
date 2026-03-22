"""
Business validation for inter-fund transfers (accounting periods, grants, compliance).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from tenant_finance.models import InterFundTransfer


def assert_project_active_for_transfer(project, *, role: str) -> None:
    from tenant_grants.models import Project

    if not project:
        raise ValueError(f"{role}: project is required.")
    if project.status != Project.Status.ACTIVE:
        raise ValueError(f"{role} project must be active.")
    if not getattr(project, "is_active", True):
        raise ValueError(f"{role} project is not available for transfers.")


def assert_bank_accounts_valid_for_interfund(*, transfer: "InterFundTransfer", tenant_db: str) -> None:
    """When project/bank workflow is used, re-check bank state at submit/post time."""
    from tenant_finance.models import BankAccount

    fid = getattr(transfer, "from_bank_account_id", None)
    tid = getattr(transfer, "to_bank_account_id", None)
    if not fid or not tid:
        return
    fb = BankAccount.objects.using(tenant_db).filter(pk=fid).select_related("currency").first()
    tb = BankAccount.objects.using(tenant_db).filter(pk=tid).select_related("currency").first()
    if not fb or not tb:
        raise ValueError("Bank account configuration is invalid for this transfer.")
    if not fb.is_active or not tb.is_active:
        raise ValueError("Bank accounts must remain active.")
    if fb.currency_id != tb.currency_id:
        raise ValueError("Source and destination banks must use the same currency.")


def assert_open_accounting_period_for_date(entry_date: date, tenant_db: str, user=None) -> None:
    """Uses Financial Setup calendar and the same open / soft-close rules as GL posting."""
    from tenant_finance.services.accounting_periods import assert_can_post

    assert_can_post(using=tenant_db, dt=entry_date, user=user)


def assert_open_fiscal_period_for_date(entry_date: date, tenant_db: str, user=None) -> None:
    """Deprecated name; prefer assert_open_accounting_period_for_date."""
    assert_open_accounting_period_for_date(entry_date, tenant_db, user=user)


def _grant_effective_end(g) -> Optional[date]:
    if not g:
        return None
    return g.revised_end_date or g.original_end_date or g.end_date


def assert_grant_active_for_transfer(
    grant,
    transfer_date: date,
    *,
    tenant_db: str,
    role: str,
) -> None:
    """Ensure grant is active and not closed for operational transfers."""
    from tenant_grants.models import Grant

    if not grant:
        return
    if grant.status == Grant.Status.CLOSED:
        raise ValueError(f"{role} fund/project is closed; inter-fund transfers are not allowed.")
    if grant.status != Grant.Status.ACTIVE:
        raise ValueError(f"{role} fund/project must be active to transfer.")
    end = _grant_effective_end(grant)
    if grant.start_date and transfer_date < grant.start_date:
        raise ValueError(f"{role} fund: transfer date is before the grant start date.")
    if end and transfer_date > end:
        raise ValueError(f"{role} fund: transfer date is after the grant end date.")


def assert_grant_compliance_period(
    grant,
    transfer_date: date,
    *,
    tenant_db: str,
    role: str,
) -> None:
    """Apply donor/grant compliance period rules (restricted funds)."""
    from tenant_finance.models import GrantComplianceRule

    if not grant:
        return
    qs = (
        GrantComplianceRule.objects.using(tenant_db)
        .filter(status=GrantComplianceRule.Status.ACTIVE)
        .filter(effective_from__lte=transfer_date, effective_to__gte=transfer_date)
    )
    rule = qs.filter(grant=grant).order_by("-effective_from").first()
    if not rule and grant.donor_id:
        rule = qs.filter(donor_id=grant.donor_id, grant__isnull=True).order_by("-effective_from").first()
    if not rule:
        return
    if not rule.allow_posting_outside_grant_period:
        if grant.start_date and transfer_date < grant.start_date:
            raise ValueError(
                f"{role}: grant compliance requires transfer date on or after grant start ({grant.start_date})."
            )
        end = _grant_effective_end(grant)
        if end and transfer_date > end:
            raise ValueError(
                f"{role}: grant compliance requires transfer date on or before grant end ({end})."
            )


def validate_interfund_transfer_core(
    *,
    from_fund_code: str,
    to_fund_code: str,
    amount: Decimal,
    transfer_date: date,
    tenant_db: str,
    user_id: Optional[int] = None,
    from_grant=None,
    to_grant=None,
    require_fiscal_open: bool = True,
    fiscal_period_date: Optional[date] = None,
) -> None:
    """fiscal_period_date: when set, used for open accounting period check (e.g. planned GL posting date)."""
    if (from_fund_code or "").strip().lower() == (to_fund_code or "").strip().lower():
        raise ValueError("From fund and to fund cannot be the same.")
    if amount is None or amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    user = None
    if user_id:
        from tenant_users.models import TenantUser

        user = TenantUser.objects.using(tenant_db).filter(pk=user_id).first()
    if require_fiscal_open:
        assert_open_accounting_period_for_date(fiscal_period_date or transfer_date, tenant_db, user=user)
    assert_grant_active_for_transfer(from_grant, transfer_date, tenant_db=tenant_db, role="Source")
    assert_grant_active_for_transfer(to_grant, transfer_date, tenant_db=tenant_db, role="Destination")
    assert_grant_compliance_period(from_grant, transfer_date, tenant_db=tenant_db, role="Source fund")
    assert_grant_compliance_period(to_grant, transfer_date, tenant_db=tenant_db, role="Destination fund")


def validate_transfer_instance(
    transfer: "InterFundTransfer",
    *,
    tenant_db: str,
    user_id: Optional[int] = None,
    require_fiscal_open: bool = True,
    fiscal_period_date: Optional[date] = None,
) -> None:
    """Pass fiscal_period_date when posting to GL (open accounting period for planned posting date)."""
    fp = getattr(transfer, "from_project", None)
    tp = getattr(transfer, "to_project", None)
    if fp and tp:
        assert_project_active_for_transfer(fp, role="Source")
        assert_project_active_for_transfer(tp, role="Destination")
    assert_bank_accounts_valid_for_interfund(transfer=transfer, tenant_db=tenant_db)
    validate_interfund_transfer_core(
        from_fund_code=transfer.from_fund_code,
        to_fund_code=transfer.to_fund_code,
        amount=transfer.amount,
        transfer_date=transfer.transfer_date,
        tenant_db=tenant_db,
        user_id=user_id,
        from_grant=getattr(transfer, "from_grant", None),
        to_grant=getattr(transfer, "to_grant", None),
        require_fiscal_open=require_fiscal_open,
        fiscal_period_date=fiscal_period_date,
    )
