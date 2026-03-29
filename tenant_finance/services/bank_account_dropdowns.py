"""
Shared rules for bank/cash dropdowns (receipts, payments, grants): GL under 1200 — Bank Accounts.

Filter: type = ASSET, parent = control account 1200 (by code), is_active, allow_posting=True.
No dependency on AccountCategory or account name/label text. Ordered by GL code ascending.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tenant_finance.models import BankAccount, ChartAccount


def chart_parent_bank_accounts_1200(using: str):
    """The 1200 — Bank Accounts control account, or None."""
    from tenant_finance.models import ChartAccount

    return ChartAccount.objects.using(using).filter(code="1200").first()


def _chart_gl_ids_blocked_when_all_bank_books_inactive(using: str, gl_ids: list[int]) -> set[int]:
    """
    GL account ids that have at least one BankAccount master row and none are active.
    Those GLs must not appear in dropdowns for new cash/bank transactions.
    """
    if not gl_ids:
        return set()
    from tenant_finance.models import BankAccount

    has_book = set(
        BankAccount.objects.using(using)
        .filter(account_id__in=gl_ids)
        .values_list("account_id", flat=True)
        .distinct()
    )
    has_active = set(
        BankAccount.objects.using(using)
        .filter(account_id__in=gl_ids, is_active=True)
        .values_list("account_id", flat=True)
        .distinct()
    )
    return has_book - has_active


def chart_accounts_bank_under_parent_1200(using: str) -> list:
    """
    Active asset posting GL accounts directly under 1200 — Bank Accounts (allow_posting=True).
    Ordered by code ascending.
    """
    from tenant_finance.models import ChartAccount

    parent = chart_parent_bank_accounts_1200(using)
    if not parent:
        return []
    return list(
        ChartAccount.objects.using(using)
        .filter(
            parent_id=parent.pk,
            is_active=True,
            type=ChartAccount.Type.ASSET,
            allow_posting=True,
        )
        .exclude(code="1200")
        .select_related("parent")
        .order_by("code")
    )


def bank_cash_posting_chart_accounts(using: str) -> list:
    """
    Chart GL rows for payment voucher bank/cash lines (same as receipts' GL side).

    If a GL has BankAccount master row(s), it is listed only when at least one book is active.
    GLs without a BankAccount master row remain available (legacy / GL-only posting).
    """
    gl_list = chart_accounts_bank_under_parent_1200(using)
    if not gl_list:
        return []
    blocked = _chart_gl_ids_blocked_when_all_bank_books_inactive(using, [a.pk for a in gl_list])
    return [gl for gl in gl_list if gl.pk not in blocked]


def chart_gl_usable_for_new_bank_transaction(using: str, chart_account_id: int) -> bool:
    """True if this bank/cash GL may be selected for a new receipt, payment, or transfer."""
    from tenant_finance.models import BankAccount, ChartAccount

    gl = ChartAccount.objects.using(using).select_related("parent").filter(pk=chart_account_id).first()
    if not gl or not deposit_gl_is_valid_bank_under_1200(using, gl):
        return False
    books = BankAccount.objects.using(using).filter(account_id=gl.pk)
    if not books.exists():
        return True
    return books.filter(is_active=True).exists()


def valid_bank_account_books_under_1200(using: str) -> list:
    """
    Active BankAccount rows whose linked GL is a posting account under 1200 — Bank Accounts.
    Ordered by GL code ascending.
    """
    from tenant_finance.models import BankAccount

    gl_list = bank_cash_posting_chart_accounts(using)
    gl_ids = [a.pk for a in gl_list]
    if not gl_ids:
        return []
    return list(
        BankAccount.objects.using(using)
        .select_related("currency", "account", "account__parent")
        .filter(is_active=True, account_id__in=gl_ids)
        .order_by("account__code", "id")
    )


def deposit_gl_is_valid_bank_under_1200(using: str, dep_gl) -> bool:
    """True if GL can be used as deposit/payment bank account per 1200 rules (no category check)."""
    from tenant_finance.models import ChartAccount

    if not dep_gl or not getattr(dep_gl, "is_active", False):
        return False
    if (dep_gl.code or "").strip() == "1200":
        return False
    parent_code = (dep_gl.parent.code if dep_gl.parent_id else "").strip()
    if parent_code != "1200":
        return False
    if dep_gl.type != ChartAccount.Type.ASSET:
        return False
    if not getattr(dep_gl, "allow_posting", True):
        return False
    return True


def receipt_register_deposit_dropdown_rows(using: str) -> list[dict]:
    """
    Legacy receipt register forms: one option per posting GL under 1200 (same as payment voucher).
    When a BankAccount master exists for the GL, show bank name/number; otherwise GL code — name.
    """
    from decimal import Decimal

    from django.db.models import Sum

    from tenant_finance.models import BankAccount, JournalEntry, JournalLine

    gl_list = bank_cash_posting_chart_accounts(using)
    if not gl_list:
        return []
    acc_ids = [gl.pk for gl in gl_list]
    bal_rows = (
        JournalLine.objects.using(using)
        .filter(account_id__in=acc_ids, entry__status=JournalEntry.Status.POSTED)
        .values("account_id")
        .annotate(b=Sum("debit") - Sum("credit"))
    )
    by_acc = {r["account_id"]: (r.get("b") or Decimal("0")) for r in bal_rows}
    out: list[dict] = []
    for gl in gl_list:
        jbal = by_acc.get(gl.pk, Decimal("0"))
        books = list(
            BankAccount.objects.using(using)
            .filter(account_id=gl.pk, is_active=True)
            .select_related("currency")
            .order_by("id")
        )
        if books:
            for b in books:
                ob = b.opening_balance or Decimal("0")
                out.append(
                    {
                        "value": str(gl.pk),
                        "label": f"{b.bank_name} - {b.account_number} ({gl.code})",
                        "balance": ob + jbal,
                        "currency_code": (b.currency.code if b.currency else "") or "",
                    }
                )
        else:
            out.append(
                {
                    "value": str(gl.pk),
                    "label": f"{gl.code} — {gl.name}",
                    "balance": jbal,
                    "currency_code": "",
                }
            )
    return out


def resolve_deposit_chart_and_bank_for_receipt(using: str, raw_id: str):
    """
    Resolve receipt "deposit" selection to (ChartAccount, BankAccount | None).

    Accepts ChartAccount id (same as payment voucher lines) or legacy BankAccount id
    for backward compatibility.
    """
    from tenant_finance.models import BankAccount, ChartAccount

    s = (raw_id or "").strip()
    if not s.isdigit():
        return None, None
    pk = int(s)

    gl = ChartAccount.objects.using(using).select_related("parent").filter(pk=pk).first()
    if gl and deposit_gl_is_valid_bank_under_1200(using, gl):
        books = BankAccount.objects.using(using).filter(account_id=gl.pk)
        if books.exists() and not books.filter(is_active=True).exists():
            return None, None
        ba = (
            BankAccount.objects.using(using)
            .filter(account_id=gl.pk, is_active=True)
            .order_by("-is_default_operating", "id")
            .first()
        )
        return gl, ba

    ba = (
        BankAccount.objects.using(using)
        .select_related("account", "account__parent")
        .filter(pk=pk, is_active=True)
        .first()
    )
    if ba and ba.account_id:
        dep_gl = ba.account
        if deposit_gl_is_valid_bank_under_1200(using, dep_gl):
            return dep_gl, ba
    return None, None
