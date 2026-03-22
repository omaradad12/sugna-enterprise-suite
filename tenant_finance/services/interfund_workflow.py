"""
Inter-fund transfer state transitions (draft → submitted → approved → posted).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tenant_finance.models import InterFundTransfer


def apply_interfund_action(
    *,
    transfer: "InterFundTransfer",
    action: str,
    tenant_db: str,
    user,
    reversal_reason: str = "",
) -> str:
    """
    Apply a workflow action. Returns a success message.
    Raises ValueError on business rule violations.
    """
    from tenant_finance.models import InterFundTransfer
    from tenant_finance.services.interfund_validation import validate_transfer_instance
    from tenant_finance.services.journal_posting import post_fund_transfer, reverse_interfund_transfer

    action = (action or "").strip().lower()
    # Refresh status from DB to avoid stale concurrent updates
    row = (
        InterFundTransfer.objects.using(tenant_db)
        .filter(pk=transfer.pk)
        .values_list("status", "posted_journal_id")
        .first()
    )
    if not row:
        raise ValueError("Transfer not found.")
    st, posted_id = row
    transfer.status = st
    transfer.posted_journal_id = posted_id

    if action == "submit":
        if st != InterFundTransfer.Status.DRAFT:
            raise ValueError("Only draft transfers can be submitted.")
        fd = getattr(transfer, "planned_posting_date", None) or transfer.transfer_date
        validate_transfer_instance(
            transfer,
            tenant_db=tenant_db,
            require_fiscal_open=True,
            fiscal_period_date=fd,
        )
        InterFundTransfer.objects.using(tenant_db).filter(pk=transfer.pk).update(
            status=InterFundTransfer.Status.SUBMITTED
        )
        return "Transfer submitted for approval."

    if action == "approve":
        if st != InterFundTransfer.Status.SUBMITTED:
            raise ValueError("Only submitted transfers can be approved.")
        fd = getattr(transfer, "planned_posting_date", None) or transfer.transfer_date
        validate_transfer_instance(
            transfer,
            tenant_db=tenant_db,
            require_fiscal_open=True,
            fiscal_period_date=fd,
        )
        InterFundTransfer.objects.using(tenant_db).filter(pk=transfer.pk).update(
            status=InterFundTransfer.Status.APPROVED,
            approved_by_id=getattr(user, "pk", None),
        )
        return "Transfer approved."

    if action == "reject":
        if st not in (
            InterFundTransfer.Status.DRAFT,
            InterFundTransfer.Status.SUBMITTED,
            InterFundTransfer.Status.APPROVED,
        ):
            raise ValueError("This transfer cannot be rejected in its current state.")
        if posted_id:
            raise ValueError("Posted transfers cannot be rejected; reverse instead.")
        InterFundTransfer.objects.using(tenant_db).filter(pk=transfer.pk).update(
            status=InterFundTransfer.Status.REJECTED,
            approved_by_id=None,
        )
        return "Transfer rejected."

    if action == "post_gl":
        if st != InterFundTransfer.Status.APPROVED:
            raise ValueError("Only approved transfers can be posted to the GL.")
        fd = getattr(transfer, "planned_posting_date", None) or transfer.transfer_date
        validate_transfer_instance(
            transfer,
            tenant_db=tenant_db,
            require_fiscal_open=True,
            fiscal_period_date=fd,
        )
        post_fund_transfer(using=tenant_db, user=user, transfer=transfer)
        return "Posted to general ledger."

    if action == "reverse":
        reason = (reversal_reason or "").strip()
        if not reason:
            raise ValueError("A reversal reason is required.")
        reverse_interfund_transfer(
            using=tenant_db,
            user=user,
            transfer=transfer,
            reversal_reason=reason,
        )
        return "Transfer reversed in the general ledger."

    raise ValueError("Unknown action.")
