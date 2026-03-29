"""
Funding modality GL mapping: completeness checks, NGO default templates, and helpers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tenant_grants.models import FundingSource


def required_component_types(fs: FundingSource) -> list[str]:
    """Component types that must have a complete FundingSourceComponentAccountMap row."""
    from tenant_grants.models import FundingSourcePaymentStructure

    FS = fs.__class__.ModalityType
    PS = FundingSourcePaymentStructure.ComponentType

    if fs.modality_type == FS.MIXED_MODALITY:
        rows = list(fs.payment_structure.order_by("sort_order", "id").values_list("component_type", flat=True))
        out: list[str] = []
        seen: set[str] = set()
        for ct in rows:
            if ct and ct not in seen:
                seen.add(ct)
                out.append(ct)
        return out

    single_map = {
        FS.ADVANCE: PS.ADVANCE,
        FS.INSTALMENT: PS.INSTALMENT,
        FS.REIMBURSEMENT: PS.REIMBURSEMENT,
        FS.MILESTONE_BASED: PS.MILESTONE_BASED,
        FS.COST_SHARE: PS.REIMBURSEMENT,
    }
    if fs.modality_type in single_map:
        return [single_map[fs.modality_type]]
    if fs.modality_type == FS.ADVANCE_WITH_RETENTION:
        return [PS.ADVANCE, PS.RETENTION]
    return [PS.ADVANCE]


def funding_modality_mapping_issues(using: str, fs: FundingSource) -> list[str]:
    """Human-readable list of missing GL mapping pieces (empty if complete)."""
    from tenant_grants.models import FundingSourceComponentAccountMap, FundingSourcePaymentStructure

    PS = FundingSourcePaymentStructure.ComponentType
    required = required_component_types(fs)
    if fs.modality_type == fs.__class__.ModalityType.MIXED_MODALITY and not required:
        return [
            "Mixed modality requires a payment structure (components totalling 100%) before GL mapping can be validated."
        ]

    maps_by_ct = {
        m.component_type: m
        for m in FundingSourceComponentAccountMap.objects.using(using)
        .filter(funding_source_id=fs.pk)
        .select_related(
            "receivable_account",
            "income_account",
            "deferred_income_account",
            "retention_account",
        )
    }
    issues: list[str] = []
    for ct in required:
        row = maps_by_ct.get(ct)
        label = dict(FundingSourcePaymentStructure.ComponentType.choices).get(ct, ct)
        if row is None:
            issues.append(f"{label}: GL mapping row is missing.")
            continue
        if not row.receivable_account_id:
            issues.append(f"{label}: Receivable account (GL) is required.")
        if not row.income_account_id:
            issues.append(f"{label}: Grant income account (GL) is required.")
        if not row.deferred_income_account_id:
            issues.append(f"{label}: Advance liability / deferred income account (GL) is required.")
        if not (row.bank_account_type or "").strip():
            issues.append(f"{label}: Bank account type (operating / project / restricted / petty cash) is required.")
        if ct == PS.RETENTION and not row.retention_account_id:
            issues.append(f"{label}: Retention account (GL) is required.")
    return issues


def funding_modality_is_ready_for_use(using: str, fs: FundingSource) -> bool:
    return len(funding_modality_mapping_issues(using, fs)) == 0


def ensure_ngo_default_chart_accounts_for_funding_templates(using: str) -> None:
    """
    Minimal NGO COA nodes used by default templates (idempotent get_or_create).
    """
    from tenant_finance.models import ChartAccount

    parent_liab, _ = ChartAccount.objects.using(using).get_or_create(
        code="2000",
        defaults={
            "name": "Current liabilities",
            "type": ChartAccount.Type.LIABILITY,
            "statement_type": ChartAccount.StatementType.BALANCE_SHEET,
            "is_active": True,
            "parent": None,
        },
    )
    parent_liab.name = "Current liabilities"
    parent_liab.type = ChartAccount.Type.LIABILITY
    parent_liab.statement_type = ChartAccount.StatementType.BALANCE_SHEET
    parent_liab.is_active = True
    parent_liab.parent = None
    parent_liab.save(using=using)

    deferred, _ = ChartAccount.objects.using(using).get_or_create(
        code="2110",
        defaults={
            "name": "Grants received in advance",
            "type": ChartAccount.Type.LIABILITY,
            "statement_type": ChartAccount.StatementType.BALANCE_SHEET,
            "is_active": True,
            "parent": parent_liab,
        },
    )
    deferred.name = "Grants received in advance"
    deferred.type = ChartAccount.Type.LIABILITY
    deferred.statement_type = ChartAccount.StatementType.BALANCE_SHEET
    deferred.is_active = True
    deferred.parent = parent_liab
    deferred.save(using=using)

    parent_ar, _ = ChartAccount.objects.using(using).get_or_create(
        code="1300",
        defaults={
            "name": "Receivables",
            "type": ChartAccount.Type.ASSET,
            "statement_type": ChartAccount.StatementType.BALANCE_SHEET,
            "is_active": True,
            "parent": None,
        },
    )
    parent_ar.name = "Receivables"
    parent_ar.type = ChartAccount.Type.ASSET
    parent_ar.statement_type = ChartAccount.StatementType.BALANCE_SHEET
    parent_ar.is_active = True
    parent_ar.parent = None
    parent_ar.save(using=using)

    recv, _ = ChartAccount.objects.using(using).get_or_create(
        code="1310",
        defaults={
            "name": "Donor / grant receivable",
            "type": ChartAccount.Type.ASSET,
            "statement_type": ChartAccount.StatementType.BALANCE_SHEET,
            "is_active": True,
            "parent": parent_ar,
        },
    )
    recv.name = "Donor / grant receivable"
    recv.type = ChartAccount.Type.ASSET
    recv.statement_type = ChartAccount.StatementType.BALANCE_SHEET
    recv.is_active = True
    recv.parent = parent_ar
    recv.save(using=using)

    ret, _ = ChartAccount.objects.using(using).get_or_create(
        code="1360",
        defaults={
            "name": "Grant retention held",
            "type": ChartAccount.Type.ASSET,
            "statement_type": ChartAccount.StatementType.BALANCE_SHEET,
            "is_active": True,
            "parent": parent_ar,
        },
    )
    ret.name = "Grant retention held"
    ret.type = ChartAccount.Type.ASSET
    ret.statement_type = ChartAccount.StatementType.BALANCE_SHEET
    ret.is_active = True
    ret.parent = parent_ar
    ret.save(using=using)


def resolve_default_ngo_chart_accounts(using: str) -> dict:
    """Resolve default GL accounts by NGO template codes / heuristics."""
    from tenant_finance.models import BankAccount, ChartAccount
    from tenant_finance.receivable_accounts import receivable_accounts_q

    out: dict = {"receivable": None, "income": None, "deferred": None, "retention": None}

    recv = (
        ChartAccount.objects.using(using)
        .filter(code="1310", is_active=True, allow_posting=True)
        .first()
    )
    if not recv:
        recv = (
            ChartAccount.objects.using(using)
            .filter(receivable_accounts_q(), is_active=True, allow_posting=True)
            .order_by("code")
            .first()
        )
    out["receivable"] = recv

    for code in ("4130", "4120", "4110", "4100"):
        inc = (
            ChartAccount.objects.using(using)
            .filter(code=code, is_active=True, allow_posting=True)
            .first()
        )
        if inc:
            out["income"] = inc
            break
    if not out["income"]:
        out["income"] = (
            ChartAccount.objects.using(using)
            .filter(
                type=ChartAccount.Type.INCOME,
                is_active=True,
                allow_posting=True,
                statement_type=ChartAccount.StatementType.INCOME_EXPENDITURE,
            )
            .order_by("code")
            .first()
        )

    deferred = (
        ChartAccount.objects.using(using)
        .filter(code="2110", type=ChartAccount.Type.LIABILITY, is_active=True, allow_posting=True)
        .first()
    )
    if not deferred:
        deferred = (
            ChartAccount.objects.using(using)
            .filter(
                type=ChartAccount.Type.LIABILITY,
                name__icontains="advance",
                is_active=True,
                allow_posting=True,
            )
            .order_by("code")
            .first()
        )
    out["deferred"] = deferred

    ret = (
        ChartAccount.objects.using(using)
        .filter(code="1360", is_active=True, allow_posting=True)
        .first()
    )
    if not ret:
        ret = (
            ChartAccount.objects.using(using)
            .filter(
                type__in=(ChartAccount.Type.ASSET, ChartAccount.Type.LIABILITY),
                name__icontains="retention",
                is_active=True,
                allow_posting=True,
            )
            .order_by("code")
            .first()
        )
    out["retention"] = ret

    out["default_bank_account_type"] = BankAccount.AccountType.OPERATING
    return out


def ensure_modality_default_ngo_gl_mapping(using: str, fs: FundingSource) -> int:
    """
    Apply the NGO default GL template (also seeds minimal COA nodes via apply_default_ngo_gl_mapping_to_funding_source).
    Returns number of component map rows written (0 if prerequisites missing).
    """
    return apply_default_ngo_gl_mapping_to_funding_source(using, fs)


def funding_modality_mapping_summary_rows(using: str, fs: FundingSource) -> list[dict]:
    """
    Read-only rows for UI: component, receivable, deferred grant income, grant income, bank book type, retention.
    """
    from tenant_grants.models import FundingSourceComponentAccountMap, FundingSourcePaymentStructure

    PS = FundingSourcePaymentStructure.ComponentType
    qs = (
        FundingSourceComponentAccountMap.objects.using(using)
        .filter(funding_source_id=fs.pk)
        .select_related("receivable_account", "income_account", "deferred_income_account", "retention_account")
        .order_by("component_type")
    )

    def _fmt(acc) -> str:
        if not acc:
            return "—"
        return f"{acc.code} — {acc.name}"

    rows: list[dict] = []
    for m in qs:
        label = dict(PS.choices).get(m.component_type, m.component_type)
        rows.append(
            {
                "component": label,
                "receivable": _fmt(m.receivable_account),
                "deferred_income": _fmt(m.deferred_income_account),
                "grant_income": _fmt(m.income_account),
                "bank_account_type": (m.bank_account_type or "").strip() or "—",
                "retention": _fmt(m.retention_account) if m.retention_account_id else "—",
            }
        )
    return rows


def ensure_funding_modality_gl_mapping_autofill(using: str, fs: FundingSource) -> bool:
    """
    Idempotent: seed default bank/income COA (same as receipt workflows) and apply
    FundingSourceComponentAccountMap rows for this modality's required components.

    Returns True if ``funding_modality_is_ready_for_use`` passes after autofill.
    """
    from tenant_portal.views import _ensure_default_receipt_and_income_accounts

    _ensure_default_receipt_and_income_accounts(using)
    apply_default_ngo_gl_mapping_to_funding_source(using, fs)
    return funding_modality_is_ready_for_use(using, fs)


def apply_default_ngo_gl_mapping_to_funding_source(using: str, fs: FundingSource) -> int:
    """
    Populate FundingSourceComponentAccountMap rows for this modality using NGO template accounts.
    Creates minimal COA nodes if missing. Returns number of map rows written.
    """
    from tenant_grants.models import FundingSourceComponentAccountMap, FundingSourcePaymentStructure

    ensure_ngo_default_chart_accounts_for_funding_templates(using)
    accounts = resolve_default_ngo_chart_accounts(using)
    recv, inc, defr, ret = accounts["receivable"], accounts["income"], accounts["deferred"], accounts["retention"]
    if not recv or not inc or not defr:
        return 0

    PS = FundingSourcePaymentStructure.ComponentType
    bank_t = accounts.get("default_bank_account_type") or ""

    required = required_component_types(fs)
    if not required:
        return 0

    n = 0
    for ct in required:
        retention_acc = (ret or recv) if ct == PS.RETENTION else None
        defaults = {
            "receivable_account": recv,
            "income_account": inc,
            "deferred_income_account": defr,
            "retention_account": retention_acc,
            "bank_account_type": bank_t,
        }
        FundingSourceComponentAccountMap.objects.using(using).update_or_create(
            funding_source_id=fs.pk,
            component_type=ct,
            defaults=defaults,
        )
        n += 1
    return n
