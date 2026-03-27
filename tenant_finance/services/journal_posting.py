"""
Centralized GL posting from source transactions (vouchers, transfers, posting engine).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from django.db import transaction
from django.utils import timezone


@dataclass(frozen=True)
class PostedJournalResult:
    entry_id: int
    reference: str


def assert_balanced_line_amounts(
    *,
    line_amounts: Sequence[tuple[Decimal, Decimal]],
) -> None:
    td = tc = Decimal("0")
    for d, c in line_amounts:
        td += d or Decimal("0")
        tc += c or Decimal("0")
    if td != tc:
        raise ValueError(f"Journal is out of balance: debits {td} ≠ credits {tc}.")
    if td <= 0:
        raise ValueError("Journal total amount must be greater than zero.")


def sync_source_pointer(*, entry, using: str) -> None:
    """Default source_id to journal id when unset; preserve external source_id (voucher, interfund, etc.)."""
    from tenant_finance.models import JournalEntry

    if not entry.pk:
        return
    updates: dict[str, object] = {}
    if getattr(entry, "source_id", None) is None:
        updates["source_id"] = entry.pk
    ref = (entry.reference or "").strip()
    if ref and not (entry.source_document_no or "").strip():
        updates["source_document_no"] = ref
    if updates:
        JournalEntry.objects.using(using).filter(pk=entry.pk).update(**updates)
        for k, v in updates.items():
            setattr(entry, k, v)


def apply_posting_user_metadata(*, entry, user, using: str) -> None:
    from tenant_finance.models import JournalEntry

    now = timezone.now()
    JournalEntry.objects.using(using).filter(pk=entry.pk).update(
        posted_at=now,
        posted_by_id=getattr(user, "id", None),
    )
    entry.posted_at = now
    entry.posted_by = user


def post_payment_voucher(*, using: str, entry, user) -> None:
    """Ensure ERP source pointer + posted_by after PV is posted (idempotent)."""
    sync_source_pointer(entry=entry, using=using)
    if getattr(entry, "posted_by_id", None) is None and getattr(user, "id", None):
        apply_posting_user_metadata(entry=entry, user=user, using=using)


def post_receipt_voucher(
    *,
    using: str,
    user,
    entry_date,
    memo: str,
    grant,
    deposit_chart_account,
    income_chart_account,
    amount: Decimal,
    description: str,
    status: str,
    external_reference_no: str = "",
    receipt_method: str = "",
    received_from: str = "",
    receipt_stream: str = "",
):
    """
    Create receipt voucher journal + lines (draft or posted).
    """
    from tenant_finance.models import JournalEntry, JournalLine

    assert_balanced_line_amounts(
        line_amounts=[(amount, Decimal("0")), (Decimal("0"), amount)]
    )

    with transaction.atomic(using=using):
        rs = (receipt_stream or "").strip().lower()
        valid_rs = {c[0] for c in JournalEntry.ReceiptStream.choices}
        entry = JournalEntry.objects.using(using).create(
            entry_date=entry_date,
            memo=memo,
            grant=grant,
            status=JournalEntry.Status.DRAFT,
            created_by=user,
            payment_method=(receipt_method or "").strip(),
            payee_name=(received_from or "").strip(),
            source=JournalEntry.SourceType.RECEIPT_VOUCHER,
            source_type=JournalEntry.SourceType.RECEIPT_VOUCHER,
            journal_type="receipt_voucher",
            is_system_generated=True,
            receipt_stream=rs if rs in valid_rs else "",
        )
        reference = f"RV-{entry.id:05d}"
        entry.reference = reference
        entry.source_document_no = (external_reference_no or "").strip() or reference
        entry.source_id = entry.pk
        entry.save(using=using, update_fields=["reference", "source_document_no", "source_id"])

        JournalLine.objects.using(using).create(
            entry=entry,
            account=deposit_chart_account,
            description=description,
            debit=amount,
            credit=Decimal("0"),
        )
        JournalLine.objects.using(using).create(
            entry=entry,
            account=income_chart_account,
            description=description,
            debit=Decimal("0"),
            credit=amount,
        )

        if status == JournalEntry.Status.POSTED:
            if grant is not None:
                from tenant_grants.services.receipt_grant_validation import (
                    assert_grant_receipt_posting_allowed,
                )

                assert_grant_receipt_posting_allowed(
                    using=using, grant=grant, receipt_amount=amount
                )
            entry.status = JournalEntry.Status.POSTED
            entry.approved_by_id = getattr(user, "id", None)
            entry.save(using=using)
            apply_posting_user_metadata(entry=entry, user=user, using=using)
        else:
            entry.status = status
            entry.save(using=using, update_fields=["status"])

    return entry


def post_cash_transfer(
    *,
    using: str,
    user,
    entry_date,
    amount: Decimal,
    description: str,
    from_account,
    to_account,
    grant=None,
    payment_method: str = "",
    currency=None,
    cost_center=None,
):
    """Post cash movement between two GL accounts (Dr To, Cr From)."""
    from tenant_finance.models import JournalEntry
    from tenant_finance.services.posting_workflow import post_transaction_to_journal

    if from_account.pk == to_account.pk:
        raise ValueError("From and To accounts must be different.")

    res = post_transaction_to_journal(
        using=using,
        transaction_type="cash_transfer",
        entry_date=entry_date,
        amount=amount,
        description=description,
        user=user,
        grant=grant,
        cost_center=cost_center,
        payment_method=payment_method or "cash",
        currency=currency,
        action="post",
        explicit_debit_account_id=to_account.pk,
        explicit_credit_account_id=from_account.pk,
    )
    return JournalEntry.objects.using(using).get(pk=res.entry_id)


def post_bank_transfer(
    *,
    using: str,
    user,
    entry_date,
    amount: Decimal,
    description: str,
    from_account,
    to_account,
    grant=None,
    payment_method: str = "",
    currency=None,
    cost_center=None,
):
    """Post bank-to-bank GL transfer (Dr To, Cr From)."""
    from tenant_finance.models import JournalEntry
    from tenant_finance.services.posting_workflow import post_transaction_to_journal

    if from_account.pk == to_account.pk:
        raise ValueError("From and To accounts must be different.")

    res = post_transaction_to_journal(
        using=using,
        transaction_type="bank_transfer",
        entry_date=entry_date,
        amount=amount,
        description=description,
        user=user,
        grant=grant,
        cost_center=cost_center,
        payment_method=payment_method or "bank_transfer",
        currency=currency,
        action="post",
        explicit_debit_account_id=to_account.pk,
        explicit_credit_account_id=from_account.pk,
    )
    return JournalEntry.objects.using(using).get(pk=res.entry_id)


def _interfund_balance_sheet_types():
    from tenant_finance.models import ChartAccount

    return (
        ChartAccount.Type.ASSET,
        ChartAccount.Type.LIABILITY,
        ChartAccount.Type.EQUITY,
    )


def assert_interfund_accounts_ngo_compliant(
    *,
    using: str,
    rule,
    from_acc,
    to_acc,
) -> None:
    """
    NGO / humanitarian fund accounting: reallocate balance-sheet fund balances only.
    Income and expense accounts must not be used. Rule must define an active clearing account.
    """
    from tenant_finance.models import ChartAccount

    bs = _interfund_balance_sheet_types()
    clr = getattr(rule, "transfer_account", None)
    if not clr:
        raise ValueError(
            "Inter-fund rule has no clearing / transfer account. Configure it under Financial Setup → Inter-fund transfer rules."
        )
    clr = ChartAccount.objects.using(using).filter(pk=clr.pk).first()
    if not clr or not clr.is_active:
        raise ValueError(
            "The clearing account on this inter-fund rule is missing or inactive. Update Financial Setup."
        )
    if clr.type not in bs:
        raise ValueError(
            "Clearing account must be a balance sheet account (asset, liability, or equity), not income or expense."
        )
    if not from_acc.is_active or not to_acc.is_active:
        raise ValueError("Source and destination fund GL accounts must be active.")
    if from_acc.type not in bs or to_acc.type not in bs:
        raise ValueError(
            "Inter-fund transfers must post only to balance sheet fund accounts. "
            "Income and expense accounts cannot be used for fund reallocation."
        )


def post_fund_transfer(
    *,
    using: str,
    user,
    transfer,
):
    from tenant_finance.models import ChartAccount, InterFundTransfer, InterFundTransferRule, JournalEntry, JournalLine

    if transfer.status != InterFundTransfer.Status.APPROVED:
        raise ValueError("Only approved inter-fund transfers can be posted to the GL.")
    if transfer.posted_journal_id:
        raise ValueError("This transfer is already posted.")

    rule = (
        InterFundTransferRule.objects.using(using)
        .select_related("transfer_account")
        .filter(pk=transfer.rule_id)
        .first()
    )
    if not rule:
        raise ValueError("Inter-fund rule not found for this transfer.")

    from_acc = (
        ChartAccount.objects.using(using)
        .filter(code__iexact=(transfer.from_fund_code or "").strip())
        .first()
    )
    to_acc = (
        ChartAccount.objects.using(using)
        .filter(code__iexact=(transfer.to_fund_code or "").strip())
        .first()
    )
    if not from_acc or not to_acc:
        raise ValueError(
            "Could not resolve chart accounts for fund codes. "
            "Ensure GL account codes match from/to fund codes."
        )
    assert_interfund_accounts_ngo_compliant(using=using, rule=rule, from_acc=from_acc, to_acc=to_acc)

    amount = transfer.amount
    assert_balanced_line_amounts(
        line_amounts=[(amount, Decimal("0")), (Decimal("0"), amount)]
    )
    memo = (
        (getattr(transfer, "description", None) or transfer.reason or "").strip()
        or f"Inter-fund transfer {(getattr(transfer, 'transfer_no', None) or '').strip() or transfer.id}"
    )
    doc_no = (getattr(transfer, "transfer_no", None) or "").strip() or f"IFT-{transfer.id}"
    gl_date = getattr(transfer, "planned_posting_date", None) or transfer.transfer_date

    with transaction.atomic(using=using):
        entry = JournalEntry.objects.using(using).create(
            entry_date=gl_date,
            memo=memo,
            reference=doc_no,
            grant=None,
            currency_id=getattr(transfer, "currency_id", None),
            status=JournalEntry.Status.DRAFT,
            created_by=user,
            source=JournalEntry.SourceType.INTER_FUND_TRANSFER,
            source_type=JournalEntry.SourceType.INTER_FUND_TRANSFER,
            journal_type="inter_fund_transfer",
            is_system_generated=True,
            source_id=transfer.id,
            source_document_no=doc_no,
        )
        JournalLine.objects.using(using).create(
            entry=entry,
            account=to_acc,
            description=memo,
            debit=amount,
            credit=Decimal("0"),
        )
        JournalLine.objects.using(using).create(
            entry=entry,
            account=from_acc,
            description=memo,
            debit=Decimal("0"),
            credit=amount,
        )
        entry.status = JournalEntry.Status.POSTED
        entry.save(using=using)
        sync_source_pointer(entry=entry, using=using)
        apply_posting_user_metadata(entry=entry, user=user, using=using)
        posting_d = gl_date
        InterFundTransfer.objects.using(using).filter(pk=transfer.pk).update(
            posted_journal_id=entry.pk,
            status=InterFundTransfer.Status.POSTED,
            posting_date=posting_d,
        )

    return entry


def reverse_interfund_transfer(
    *,
    using: str,
    user,
    transfer,
    reversal_reason: str,
):
    """
    Post a reversing journal (Dr source, Cr destination) and mark transfer reversed.
    """
    from tenant_finance.models import ChartAccount, InterFundTransfer, InterFundTransferRule, JournalEntry, JournalLine

    if transfer.status != InterFundTransfer.Status.POSTED:
        raise ValueError("Only posted inter-fund transfers can be reversed.")
    if not transfer.posted_journal_id:
        raise ValueError("Posted journal is missing for this transfer.")
    if getattr(transfer, "reversal_journal_id", None):
        raise ValueError("This transfer has already been reversed.")

    from_acc = (
        ChartAccount.objects.using(using)
        .filter(code__iexact=(transfer.from_fund_code or "").strip())
        .first()
    )
    to_acc = (
        ChartAccount.objects.using(using)
        .filter(code__iexact=(transfer.to_fund_code or "").strip())
        .first()
    )
    if not from_acc or not to_acc:
        raise ValueError("Could not resolve chart accounts for reversal.")

    rule = (
        InterFundTransferRule.objects.using(using)
        .select_related("transfer_account")
        .filter(pk=transfer.rule_id)
        .first()
    )
    if rule:
        assert_interfund_accounts_ngo_compliant(using=using, rule=rule, from_acc=from_acc, to_acc=to_acc)

    amount = transfer.amount
    memo = (reversal_reason or "").strip() or f"Reversal of {getattr(transfer, 'transfer_no', '') or transfer.id}"

    with transaction.atomic(using=using):
        entry = JournalEntry.objects.using(using).create(
            entry_date=timezone.now().date(),
            memo=memo,
            reference=f"REV-{(getattr(transfer, 'transfer_no', None) or transfer.id)}",
            grant=None,
            currency_id=getattr(transfer, "currency_id", None),
            status=JournalEntry.Status.DRAFT,
            created_by=user,
            source=JournalEntry.SourceType.REVERSAL,
            source_type=JournalEntry.SourceType.REVERSAL,
            journal_type="reversal",
            is_system_generated=True,
            source_id=transfer.id,
            source_document_no=(getattr(transfer, "transfer_no", None) or f"IFT-{transfer.id}") + "-REV",
            reversed_by_id=transfer.posted_journal_id,
        )
        # Reverse original: original was Dr To, Cr From → reversal Dr From, Cr To
        JournalLine.objects.using(using).create(
            entry=entry,
            account=from_acc,
            description=memo,
            debit=amount,
            credit=Decimal("0"),
        )
        JournalLine.objects.using(using).create(
            entry=entry,
            account=to_acc,
            description=memo,
            debit=Decimal("0"),
            credit=amount,
        )
        entry.status = JournalEntry.Status.POSTED
        entry.save(using=using)
        sync_source_pointer(entry=entry, using=using)
        apply_posting_user_metadata(entry=entry, user=user, using=using)
        now = timezone.now()
        InterFundTransfer.objects.using(using).filter(pk=transfer.pk).update(
            status=InterFundTransfer.Status.REVERSED,
            reversal_journal_id=entry.pk,
            reversed_by_id=getattr(user, "pk", None),
            reversed_at=now,
        )

    return entry
