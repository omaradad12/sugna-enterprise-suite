"""
Bank / cash GL orientation for payments and receipts.

Payment (money out): debit expense (or payable), credit bank — never debit the bank for a
standard payment (corrections use reversal or manual journals).

Receipt (money in): debit bank, credit income / receivable — never credit the bank for a
standard receipt.
"""
from __future__ import annotations

from decimal import Decimal


def normalize_voucher_debit_credit_accounts(
    *,
    using: str,
    transaction_type: str,
    debit_account,
    credit_account,
):
    """
    If posting rules map bank to the wrong side, swap legs for payment_voucher / receipt_voucher.

    Transfers use explicit Dr/Cr in posting_workflow and must not pass through this.
    """
    from tenant_finance.models import BankAccount

    tx = (transaction_type or "").strip().lower()
    if tx not in {"payment_voucher", "receipt_voucher"}:
        return debit_account, credit_account

    d_bank = BankAccount.objects.using(using).filter(account_id=debit_account.pk).exists()
    c_bank = BankAccount.objects.using(using).filter(account_id=credit_account.pk).exists()

    if tx == "payment_voucher":
        # Expect: Dr expense/payable, Cr bank. If bank is on the debit side, swap.
        if d_bank and not c_bank:
            return credit_account, debit_account
    elif tx == "receipt_voucher":
        # Expect: Dr bank, Cr income/receivable. If bank is on the credit side, swap.
        if c_bank and not d_bank:
            return credit_account, debit_account

    return debit_account, credit_account


def assert_bank_line_orientation_on_post_to_gl(entry, using: str) -> None:
    """
    Enforce bank line orientation when a journal is posted (status -> POSTED).

    Skips reversals, manual journals, and non-voucher types (transfers, inter-fund, etc.).
    """
    from django.core.exceptions import ValidationError
    from django.utils.translation import gettext as _

    from tenant_finance.models import BankAccount, JournalEntry, JournalLine

    if not entry.pk:
        return

    st = (entry.source_type or "").strip()
    jt = (entry.journal_type or "").strip().lower()

    if st == JournalEntry.SourceType.REVERSAL or jt == "reversal":
        return
    if st == JournalEntry.SourceType.MANUAL:
        return

    bank_ids = set(BankAccount.objects.using(using).values_list("account_id", flat=True))
    if not bank_ids:
        return

    lines = list(
        JournalLine.objects.using(using)
        .filter(entry_id=entry.pk)
        .only("account_id", "debit", "credit")
    )
    if not lines:
        return

    if st == JournalEntry.SourceType.PAYMENT_VOUCHER and jt == "payment_voucher":
        for ln in lines:
            if ln.account_id not in bank_ids:
                continue
            if (ln.debit or Decimal("0")) > Decimal("0"):
                raise ValidationError(
                    {
                        "status": _(
                            "Payment vouchers must record money out as a credit to the bank/cash account "
                            "(debit expense or payable, credit bank). Do not debit the bank for payments; "
                            "use a reversal entry or an adjusting journal to correct the general ledger."
                        )
                    }
                )
        return

    if st == JournalEntry.SourceType.RECEIPT_VOUCHER or jt == "receipt_voucher":
        for ln in lines:
            if ln.account_id not in bank_ids:
                continue
            if (ln.credit or Decimal("0")) > Decimal("0"):
                raise ValidationError(
                    {
                        "status": _(
                            "Receipt vouchers must record money in as a debit to the bank/cash account "
                            "(debit bank, credit income or receivable). Do not credit the bank for receipts."
                        )
                    }
                )
        return
