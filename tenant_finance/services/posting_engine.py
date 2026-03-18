from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PostingResolution:
    rule_id: int | None
    debit_account_id: int
    credit_account_id: int
    apply_dimension: str


def _as_decimal(v) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _matches_conditions(conditions: dict, ctx: dict) -> bool:
    if not conditions:
        return True

    # Exact matches
    for key in ("project_id", "grant_id", "donor_id", "cost_center_id", "payment_method", "currency"):
        if key in conditions and conditions[key] not in (None, "", []):
            if ctx.get(key) != conditions[key]:
                return False

    # Amount window
    min_amt = _as_decimal(conditions.get("min_amount"))
    max_amt = _as_decimal(conditions.get("max_amount"))
    amt = _as_decimal(ctx.get("amount")) or Decimal("0")
    if min_amt is not None and amt < min_amt:
        return False
    if max_amt is not None and amt > max_amt:
        return False

    return True


def resolve_posting(
    *,
    using: str,
    transaction_type: str,
    amount: Decimal,
    project_id: int | None = None,
    grant_id: int | None = None,
    donor_id: int | None = None,
    cost_center_id: int | None = None,
    payment_method: str | None = None,
    currency: str | None = None,
) -> PostingResolution:
    """
    Resolve a PostingRule (or DefaultAccountMapping fallback) for a transaction.

    Ensures double-entry validity and blocks invalid mappings.
    """
    from tenant_finance.models import ChartAccount, DefaultAccountMapping, PostingRule

    ctx = {
        "project_id": project_id,
        "grant_id": grant_id,
        "donor_id": donor_id,
        "cost_center_id": cost_center_id,
        "payment_method": (payment_method or "").strip() or None,
        "currency": (currency or "").strip() or None,
        "amount": amount,
    }

    rules = list(
        PostingRule.objects.using(using)
        .select_related("debit_account", "credit_account")
        .filter(transaction_type=transaction_type, status=PostingRule.Status.ACTIVE)
        .order_by("priority", "name")
    )

    chosen = None
    for r in rules:
        cond = r.conditions if isinstance(r.conditions, dict) else {}
        if _matches_conditions(cond, ctx):
            chosen = r
            break

    if chosen:
        debit = chosen.debit_account
        credit = chosen.credit_account
        if not debit or not credit:
            raise ValueError("Posting rule is missing debit/credit accounts.")
        if debit.id == credit.id:
            raise ValueError("Posting rule debit and credit accounts cannot be the same.")
        if not debit.is_active or not debit.is_leaf():
            raise ValueError("Posting rule debit account must be an active posting (leaf) account.")
        if not credit.is_active or not credit.is_leaf():
            raise ValueError("Posting rule credit account must be an active posting (leaf) account.")
        return PostingResolution(
            rule_id=chosen.id,
            debit_account_id=debit.id,
            credit_account_id=credit.id,
            apply_dimension=chosen.apply_dimension or PostingRule.Dimension.NONE,
        )

    # Fallback to default mapping
    mapping = (
        DefaultAccountMapping.objects.using(using)
        .select_related("default_debit_account", "default_credit_account")
        .filter(transaction_type=transaction_type, status=DefaultAccountMapping.Status.ACTIVE)
        .order_by("name")
        .first()
    )
    if not mapping or not mapping.default_debit_account_id or not mapping.default_credit_account_id:
        raise ValueError("No posting rule or default account mapping is configured for this transaction type.")

    debit = ChartAccount.objects.using(using).get(pk=mapping.default_debit_account_id)
    credit = ChartAccount.objects.using(using).get(pk=mapping.default_credit_account_id)
    if debit.id == credit.id:
        raise ValueError("Default mapping debit and credit accounts cannot be the same.")
    if not debit.is_active or not debit.is_leaf():
        raise ValueError("Default mapping debit account must be an active posting (leaf) account.")
    if not credit.is_active or not credit.is_leaf():
        raise ValueError("Default mapping credit account must be an active posting (leaf) account.")

    return PostingResolution(
        rule_id=None,
        debit_account_id=debit.id,
        credit_account_id=credit.id,
        apply_dimension=mapping.apply_dimension or DefaultAccountMapping.Dimension.NONE,
    )

