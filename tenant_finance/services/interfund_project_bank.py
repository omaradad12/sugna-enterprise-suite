"""
Resolve inter-fund transfers from project + bank account selections (NGO project-to-project / bank-to-bank).

Grants link projects to bank accounts; chart accounts for posting come from BankAccount.account.
"""
from __future__ import annotations

from typing import Any

from tenant_finance.services.interfund_validation import assert_project_active_for_transfer

def banks_for_project(*, tenant_db: str, project_id: int) -> list[dict[str, Any]]:
    """Distinct active bank accounts linked via active grants on this project."""
    from tenant_grants.models import Grant

    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    qs = (
        Grant.objects.using(tenant_db)
        .filter(
            project_id=project_id,
            status=Grant.Status.ACTIVE,
            bank_account__isnull=False,
            bank_account__is_active=True,
        )
        .select_related("bank_account", "bank_account__currency")
        .order_by("code")
    )
    for g in qs:
        ba = g.bank_account
        if not ba or ba.id in seen:
            continue
        seen.add(ba.id)
        cur = ba.currency
        out.append(
            {
                "id": ba.id,
                "label": f"{ba.bank_name} — {ba.account_name} ({ba.account_number})",
                "currency_id": ba.currency_id,
                "currency_code": cur.code if cur else "",
            }
        )
    return out


def resolve_grant_for_project_bank(
    *, tenant_db: str, project_id: int, bank_account_id: int
):
    """Pick one active grant that ties the project to this bank (deterministic)."""
    from tenant_grants.models import Grant

    return (
        Grant.objects.using(tenant_db)
        .filter(
            project_id=project_id,
            bank_account_id=bank_account_id,
            status=Grant.Status.ACTIVE,
        )
        .select_related("donor", "project")
        .order_by("code")
        .first()
    )


def build_payload_from_projects_and_banks(
    *,
    tenant_db: str,
    from_project_id: int,
    to_project_id: int,
    from_bank_account_id: int,
    to_bank_account_id: int,
) -> dict[str, Any]:
    """
    Resolve GL fund codes (bank cash accounts), grants, donor, currency.
    Raises ValueError on business rules.
    """
    from tenant_finance.models import BankAccount
    from tenant_finance.models import InterFundTransferRule
    from tenant_grants.models import Project

    if from_project_id == to_project_id:
        raise ValueError("Source and destination project must be different.")
    if from_bank_account_id == to_bank_account_id:
        raise ValueError("Source and destination bank account must be different.")

    fp = Project.objects.using(tenant_db).filter(pk=from_project_id).first()
    tp = Project.objects.using(tenant_db).filter(pk=to_project_id).first()
    if not fp or not tp:
        raise ValueError("Invalid project selection.")
    assert_project_active_for_transfer(fp, role="Source")
    assert_project_active_for_transfer(tp, role="Destination")

    fb = (
        BankAccount.objects.using(tenant_db)
        .select_related("account", "currency")
        .filter(pk=from_bank_account_id)
        .first()
    )
    tb = (
        BankAccount.objects.using(tenant_db)
        .select_related("account", "currency")
        .filter(pk=to_bank_account_id)
        .first()
    )
    if not fb or not tb:
        raise ValueError("Invalid bank account selection.")
    if not fb.is_active or not tb.is_active:
        raise ValueError("Both bank accounts must be active.")
    if fb.currency_id != tb.currency_id:
        raise ValueError("Source and destination banks must use the same currency for this transfer.")

    from_grant = resolve_grant_for_project_bank(
        tenant_db=tenant_db, project_id=from_project_id, bank_account_id=from_bank_account_id
    )
    to_grant = resolve_grant_for_project_bank(
        tenant_db=tenant_db, project_id=to_project_id, bank_account_id=to_bank_account_id
    )
    if not from_grant:
        raise ValueError(
            "No active grant links the source project to the selected bank account. "
            "Assign the bank account on a grant for this project."
        )
    if not to_grant:
        raise ValueError(
            "No active grant links the destination project to the selected bank account. "
            "Assign the bank account on a grant for this project."
        )

    from_code = (fb.account.code or "").strip()
    to_code = (tb.account.code or "").strip()
    if not from_code or not to_code:
        raise ValueError("Bank accounts must have linked GL account codes.")

    donor_id = from_grant.donor_id
    currency_id = fb.currency_id

    ft = InterFundTransferRule.FundType.PROJECT

    return {
        "from_fund_type": ft,
        "to_fund_type": ft,
        "from_fund_code": from_code,
        "to_fund_code": to_code,
        "from_grant": from_grant,
        "to_grant": to_grant,
        "donor_id": donor_id,
        "currency_id": currency_id,
        "from_project": fp,
        "to_project": tp,
        "from_bank_account": fb,
        "to_bank_account": tb,
    }


def projects_payload(*, tenant_db: str) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Projects and banks grouped by project id (string keys for JSON)."""
    from tenant_grants.models import Project

    projects = list(
        Project.objects.using(tenant_db)
        .filter(status=Project.Status.ACTIVE, is_active=True)
        .order_by("code")
    )
    project_rows = [{"id": p.id, "label": f"{p.code} — {p.name}"} for p in projects]
    banks_by_project: dict[str, list[dict[str, Any]]] = {}
    for p in projects:
        banks_by_project[str(p.id)] = banks_for_project(tenant_db=tenant_db, project_id=p.id)
    return project_rows, banks_by_project
