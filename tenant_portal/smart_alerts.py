"""
Smart Alerts and Financial Warnings service.
Builds a unified list of alerts from Cash & Bank, Budget, Payables, Receivables, and Audit & Risk.
Alerts are computed from current data (no persistence); used in notification bell, dashboards, and Financial Alerts page.
"""

from decimal import Decimal
from django.db.models import Sum
from django.utils import timezone
from django.urls import reverse


# Priority levels for UI: critical (red), warning (orange), information (green)
PRIORITY_CRITICAL = "critical"
PRIORITY_WARNING = "warning"
PRIORITY_INFO = "information"

# Categories for grouping
CATEGORY_CASH_BANK = "cash_bank"
CATEGORY_BUDGET = "budget"
CATEGORY_PAYABLES = "payables"
CATEGORY_RECEIVABLES = "receivables"
CATEGORY_AUDIT_RISK = "audit_risk"
CATEGORY_PROJECTS = "projects"

# Petty cash threshold below which we raise an alert (configurable)
PETTY_CASH_THRESHOLD = Decimal("500")
# Budget "nearing limit" threshold (percent)
BUDGET_NEARING_PCT = Decimal("80")


def get_smart_alerts(tenant_db: str) -> list[dict]:
    """
    Return a list of alert dicts, each with:
    - category, priority, title, message, link_url, link_label (optional)
    """
    alerts = []
    today = timezone.now().date()

    try:
        _cash_bank_alerts(tenant_db, today, alerts)
        _budget_alerts(tenant_db, alerts)
        _payables_alerts(tenant_db, today, alerts)
        _receivables_alerts(tenant_db, today, alerts)
        _audit_risk_alerts(tenant_db, alerts)
    except Exception:
        # Avoid breaking layout if any query fails (e.g. missing app/migration)
        pass

    # Sort: critical first, then warning, then info; then by category
    priority_order = {PRIORITY_CRITICAL: 0, PRIORITY_WARNING: 1, PRIORITY_INFO: 2}
    alerts.sort(key=lambda a: (priority_order.get(a["priority"], 3), a["category"]))
    return alerts


def _add(
    alerts: list,
    category: str,
    priority: str,
    title: str,
    message: str,
    link_url: str,
    link_label: str = "",
    *,
    restrict_to_pm_admin: bool = False,
    project_ids: list | None = None,
):
    row = {
        "category": category,
        "priority": priority,
        "title": title,
        "message": message,
        "link_url": link_url,
        "link_label": link_label or title,
    }
    if restrict_to_pm_admin:
        row["restrict_to_pm_admin"] = True
        row["project_ids"] = list(project_ids or [])
    alerts.append(row)


def _project_end_alerts(tenant_db: str, today, alerts: list) -> None:
    from django.urls import reverse

    from tenant_grants.models import Project
    from tenant_grants.services.project_end_schedule import project_end_alert_state

    qs = (
        Project.objects.using(tenant_db)
        .exclude(status__in=[Project.Status.CLOSED, Project.Status.COMPLETED])
        .only("id", "code", "name", "status", "end_date", "original_end_date", "revised_end_date", "start_date")
    )
    list_url = reverse("tenant_portal:grants_projects_list")
    max_project_alerts = 48
    n_proj_alerts = 0
    for p in qs.iterator(chunk_size=100):
        if n_proj_alerts >= max_project_alerts:
            break
        state = project_end_alert_state(p, today)
        if not state:
            continue
        code = p.code or ""
        name = (p.name or "").strip() or code
        if state == "ending_soon":
            _add(
                alerts,
                CATEGORY_PROJECTS,
                PRIORITY_WARNING,
                f"Project {code} approaching end",
                f"Project {code} – {name} is approaching end date. Please review closure or extension.",
                list_url + (f"?q={code}" if code else ""),
                "Project list",
                restrict_to_pm_admin=True,
                project_ids=[p.pk],
            )
            n_proj_alerts += 1
        elif state == "on_end":
            _add(
                alerts,
                CATEGORY_PROJECTS,
                PRIORITY_WARNING,
                f"Project {code} ends today",
                f"Project {code} – {name} reaches its effective end date today. Review closure or extension.",
                list_url + (f"?q={code}" if code else ""),
                "Project list",
                restrict_to_pm_admin=True,
                project_ids=[p.pk],
            )
            n_proj_alerts += 1
        else:
            _add(
                alerts,
                CATEGORY_PROJECTS,
                PRIORITY_CRITICAL,
                f"Project {code} past end date",
                f"Project {code} has passed the end date. Posting transactions should be restricted unless extension approved (revised end date).",
                list_url + (f"?q={code}" if code else ""),
                "Project list",
                restrict_to_pm_admin=True,
                project_ids=[p.pk],
            )
            n_proj_alerts += 1


def _cash_bank_alerts(tenant_db: str, today, alerts: list):
    from tenant_finance.models import BankAccount, ChartAccount, JournalEntry, JournalLine

    bank_accounts = list(
        BankAccount.objects.using(tenant_db).filter(is_active=True).select_related("account")
    )
    if not bank_accounts:
        return
    cash_account_ids = [ba.account_id for ba in bank_accounts if ba.account_id]
    if not cash_account_ids:
        return

    bal_rows = (
        JournalLine.objects.using(tenant_db)
        .filter(
            account_id__in=cash_account_ids,
            entry__status=JournalEntry.Status.POSTED,
        )
        .values("account_id")
        .annotate(bal=Sum("debit") - Sum("credit"))
    )
    by_account = {r["account_id"]: r.get("bal") or Decimal("0") for r in bal_rows}

    total_cash = Decimal("0")
    petty_balance = Decimal("0")
    for ba in bank_accounts:
        bal = by_account.get(ba.account_id, Decimal("0"))
        name = (ba.account_name or "").lower()
        if "petty" in name:
            petty_balance += bal
        else:
            total_cash += bal

    # Bank reconciliation pending: treat all active bank accounts as needing reconciliation (placeholder)
    if bank_accounts:
        _add(
            alerts,
            CATEGORY_CASH_BANK,
            PRIORITY_WARNING,
            "Bank reconciliation pending",
            f"{len(bank_accounts)} bank/cash account(s) may need reconciliation.",
            reverse("tenant_portal:cash_bank_accounts"),
            "Bank accounts",
        )

    if total_cash + petty_balance < Decimal("0"):
        _add(
            alerts,
            CATEGORY_CASH_BANK,
            PRIORITY_CRITICAL,
            "Negative cash balance",
            "Total cash and bank balance is negative.",
            reverse("tenant_portal:finance_cash_position"),
            "Cash position",
        )
    elif petty_balance < PETTY_CASH_THRESHOLD and petty_balance >= Decimal("0"):
        _add(
            alerts,
            CATEGORY_CASH_BANK,
            PRIORITY_WARNING,
            "Petty cash below threshold",
            f"Petty cash balance ({petty_balance}) is below {PETTY_CASH_THRESHOLD}.",
            reverse("tenant_portal:cash_bank_accounts"),
            "Bank accounts",
        )


def _budget_alerts(tenant_db: str, alerts: list):
    from tenant_finance.models import ChartAccount, JournalLine
    from tenant_grants.models import BudgetLine, Grant

    budgets_by_grant = {
        r["grant_id"]: r["total"] or Decimal("0")
        for r in BudgetLine.objects.using(tenant_db).values("grant_id").annotate(total=Sum("amount"))
    }
    spend_by_grant = {
        r["entry__grant_id"]: r["spent"] or Decimal("0")
        for r in JournalLine.objects.using(tenant_db)
        .filter(account__type=ChartAccount.Type.EXPENSE, entry__grant_id__isnull=False)
        .values("entry__grant_id")
        .annotate(spent=Sum("debit"))
    }

    for g in Grant.objects.using(tenant_db).filter(status=Grant.Status.ACTIVE):
        budget = budgets_by_grant.get(g.id, Decimal("0"))
        spent = spend_by_grant.get(g.id, Decimal("0"))
        ceiling = budget if budget > 0 else Decimal(str(g.award_amount or 0))
        if ceiling <= 0:
            continue
        pct = (spent / ceiling) * Decimal("100")
        if spent > ceiling:
            _add(
                alerts,
                CATEGORY_BUDGET,
                PRIORITY_CRITICAL,
                "Budget exceeded",
                f"{g.code}: spent {spent} exceeds budget {ceiling}.",
                reverse("tenant_portal:finance_budget_vs_actual"),
                "Budget vs actual",
            )
        elif pct >= BUDGET_NEARING_PCT:
            _add(
                alerts,
                CATEGORY_BUDGET,
                PRIORITY_WARNING,
                "Budget nearing limit",
                f"{g.code}: {pct:.1f}% utilized.",
                reverse("tenant_portal:finance_budget_vs_actual"),
                "Budget vs actual",
            )


def _payables_alerts(tenant_db: str, today, alerts: list):
    from tenant_finance.models import JournalEntry
    from tenant_grants.models import GrantApproval, SupplierInvoice

    # Overdue vendor invoices (approved or pending_approval, due_date < today)
    overdue_invoices = SupplierInvoice.objects.using(tenant_db).filter(
        due_date__lt=today,
        status__in=[SupplierInvoice.Status.APPROVED, SupplierInvoice.Status.PENDING_APPROVAL],
    ).count()
    if overdue_invoices:
        _add(
            alerts,
            CATEGORY_PAYABLES,
            PRIORITY_CRITICAL if overdue_invoices > 5 else PRIORITY_WARNING,
            "Overdue vendor invoice",
            f"{overdue_invoices} supplier invoice(s) past due date.",
            reverse("tenant_portal:grants_procurement_po_list"),
            "Procurement",
        )

    # Pending payment approval: journal entries pending approval
    pending_journals = JournalEntry.objects.using(tenant_db).filter(
        status=JournalEntry.Status.PENDING_APPROVAL,
    ).count()
    if pending_journals:
        _add(
            alerts,
            CATEGORY_PAYABLES,
            PRIORITY_WARNING,
            "Pending payment approval",
            f"{pending_journals} journal(s) awaiting approval.",
            reverse("tenant_portal:finance_journal_approval"),
            "Journal approval",
        )
    pending_approvals = GrantApproval.objects.using(tenant_db).filter(status=GrantApproval.Status.PENDING).count()
    if pending_approvals:
        _add(
            alerts,
            CATEGORY_PAYABLES,
            PRIORITY_INFO,
            "Pending payment approval",
            f"{pending_approvals} grant approval(s) pending.",
            reverse("tenant_portal:finance_pending_approvals"),
            "Pending approvals",
        )


def _receivables_alerts(tenant_db: str, today, alerts: list):
    from tenant_finance.models import ChartAccount, JournalLine
    from tenant_finance.receivable_accounts import receivable_accounts_q

    recv_ids = list(
        ChartAccount.objects.using(tenant_db).filter(receivable_accounts_q()).values_list("id", flat=True)
    )
    if not recv_ids:
        return
    from tenant_finance.models import JournalEntry
    recv_balance = (
        JournalLine.objects.using(tenant_db)
        .filter(
            account_id__in=recv_ids,
            entry__status=JournalEntry.Status.POSTED,
        )
        .aggregate(bal=Sum("debit") - Sum("credit"))
        .get("bal")
        or Decimal("0")
    )
    if recv_balance > 0:
        # Receivable aging: entries older than 90 days (simplified: just flag outstanding)
        from datetime import timedelta
        cutoff = today - timedelta(days=90)
        old_lines = (
            JournalLine.objects.using(tenant_db)
            .filter(
                account_id__in=recv_ids,
                entry__status=JournalEntry.Status.POSTED,
                entry__entry_date__lt=cutoff,
            )
            .aggregate(t=Sum("debit") - Sum("credit"))
            .get("t")
            or Decimal("0")
        )
        if old_lines and old_lines > Decimal("0"):
            _add(
                alerts,
                CATEGORY_RECEIVABLES,
                PRIORITY_WARNING,
                "Receivable aging",
                f"Outstanding receivables include amounts over 90 days old.",
                reverse("tenant_portal:recv_outstanding_receivables"),
                "Outstanding receivables",
            )
        else:
            _add(
                alerts,
                CATEGORY_RECEIVABLES,
                PRIORITY_INFO,
                "Outstanding receivables",
                f"Total outstanding: {recv_balance:,.2f}.",
                reverse("tenant_portal:recv_outstanding_receivables"),
                "Outstanding receivables",
            )


def _audit_risk_alerts(tenant_db: str, alerts: list):
    try:
        from tenant_audit_risk.models import RiskAlert, TransactionRiskAssessment
    except ImportError:
        return

    # Duplicate receipt / payment alerts (open)
    dup_count = RiskAlert.objects.using(tenant_db).filter(
        alert_type=RiskAlert.AlertType.DUPLICATE_PAYMENT,
        status=RiskAlert.Status.OPEN,
    ).count()
    if dup_count:
        _add(
            alerts,
            CATEGORY_AUDIT_RISK,
            PRIORITY_CRITICAL,
            "Duplicate receipt numbers",
            f"{dup_count} duplicate payment/receipt alert(s) require review.",
            reverse("tenant_portal:audit_risk_duplicate_payments"),
            "Duplicate payments",
        )

    # Suspicious transactions (high/critical risk)
    suspicious = TransactionRiskAssessment.objects.using(tenant_db).filter(
        risk_level__in=[TransactionRiskAssessment.RiskLevel.HIGH, TransactionRiskAssessment.RiskLevel.CRITICAL],
        investigation_status=TransactionRiskAssessment.InvestigationStatus.DETECTED,
    ).count()
    if suspicious:
        _add(
            alerts,
            CATEGORY_AUDIT_RISK,
            PRIORITY_CRITICAL if suspicious > 3 else PRIORITY_WARNING,
            "Suspicious transactions",
            f"{suspicious} high/critical risk transaction(s) detected.",
            reverse("tenant_portal:audit_risk_high_risk"),
            "High risk transactions",
        )

    # Missing supporting documents: posted journal entries with no attachments (sample, limit check)
    from tenant_finance.models import JournalEntry, JournalEntryAttachment
    from django.db.models import Count, Q
    entries_with_attachments = set(
        JournalEntryAttachment.objects.using(tenant_db).values_list("entry_id", flat=True).distinct()
    )
    missing_docs = (
        JournalEntry.objects.using(tenant_db)
        .filter(status=JournalEntry.Status.POSTED)
        .exclude(id__in=entries_with_attachments)
        .count()
    )
    if missing_docs > 10:  # Only alert if material count
        _add(
            alerts,
            CATEGORY_AUDIT_RISK,
            PRIORITY_WARNING,
            "Missing supporting documents",
            f"{missing_docs} posted journal entries have no attachments.",
            reverse("tenant_portal:finance_audit_trail"),
            "Audit trail",
        )
