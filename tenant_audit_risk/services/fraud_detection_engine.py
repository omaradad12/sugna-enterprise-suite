"""
Fraud Detection Engine: evaluates transactions and creates risk assessments and alerts.
Runs on JournalEntry (and optionally SupplierInvoice) create/post.
"""
from __future__ import annotations

from decimal import Decimal
from django.utils import timezone

# Risk level bands (0-100)
RISK_LOW_MAX = 30
RISK_MEDIUM_MAX = 60
RISK_HIGH_MAX = 80
# Score >= RISK_HIGH triggers alert; >= 81 is Critical
DEFAULT_ALERT_THRESHOLD = 61
# Auto-open investigation when score >= this (optional)
DEFAULT_INVESTIGATION_THRESHOLD = 81
# Points per indicator (max 100 total)
POINTS_DUPLICATE_REF = 25
POINTS_DUPLICATE_PAYMENT = 25
POINTS_SAME_USER_APPROVE = 20
POINTS_OVER_THRESHOLD = 15
POINTS_BACKDATED = 15
POINTS_OUTSIDE_PROJECT_PERIOD = 15
POINTS_OVER_BUDGET = 20
POINTS_VENDOR_NEW = 15
POINTS_MISSING_DOCS = 15
POINTS_ROUND_NUMBER = 10
POINTS_LATE_POSTING = 10
# Vendor "new" = created within this many days before payment
VENDOR_NEW_DAYS = 7
# Round number: amount is multiple of this (e.g. 10000)
ROUND_NUMBER_STEP = Decimal("10000")
# Late posting: hour >= 22 or hour < 6, or weekend
LATE_HOUR_START = 22
LATE_HOUR_END = 6


def _get_level(score: int) -> str:
    if score <= RISK_LOW_MAX:
        return "low"
    if score <= RISK_MEDIUM_MAX:
        return "medium"
    if score <= RISK_HIGH_MAX:
        return "high"
    return "critical"


def evaluate_journal_entry(entry_id: int, using: str) -> dict:
    """
    Evaluate a JournalEntry (after it is posted). Returns the assessment dict and
    creates/updates TransactionRiskAssessment, RiskAlert, and optionally InvestigationCase.
    """
    from django.db.models import Sum
    from tenant_finance.models import JournalEntry, JournalLine
    from tenant_audit_risk.models import (
        TransactionRiskAssessment,
        RiskAlert,
        InvestigationCase,
    )

    entry = (
        JournalEntry.objects.using(using)
        .filter(pk=entry_id)
        .select_related("grant", "grant__donor", "created_by", "approved_by")
        .first()
    )
    if not entry or entry.status != JournalEntry.Status.POSTED:
        return {"score": 0, "level": "low", "details": {}}

    details = {}
    score = 0

    # 1) Duplicate reference (same reference in same period)
    ref = (entry.reference or "").strip()
    if ref:
        same_ref = (
            JournalEntry.objects.using(using)
            .filter(reference=ref, status=JournalEntry.Status.POSTED)
            .exclude(pk=entry_id)
        )
        if same_ref.exists():
            details["duplicate_reference"] = POINTS_DUPLICATE_REF
            score += POINTS_DUPLICATE_REF

    # 2) Same user created and approved
    if entry.created_by_id and entry.approved_by_id and entry.created_by_id == entry.approved_by_id:
        details["same_user_approve"] = POINTS_SAME_USER_APPROVE
        score += POINTS_SAME_USER_APPROVE

    # 3) Backdated: entry_date before today or before posted_at date
    today = timezone.now().date()
    if entry.entry_date > today:
        details["future_dated"] = POINTS_BACKDATED
        score += POINTS_BACKDATED
    elif entry.posted_at and entry.entry_date < entry.posted_at.date():
        # Entry date is before posting date (backdated)
        details["backdated"] = POINTS_BACKDATED
        score += POINTS_BACKDATED

    # 4) Outside project period (if grant set)
    if entry.grant_id:
        g = entry.grant
        if g.start_date and entry.entry_date < g.start_date:
            details["before_grant_start"] = POINTS_OUTSIDE_PROJECT_PERIOD
            score += POINTS_OUTSIDE_PROJECT_PERIOD
        if g.end_date and entry.entry_date > g.end_date:
            details["after_grant_end"] = POINTS_OUTSIDE_PROJECT_PERIOD
            score += POINTS_OUTSIDE_PROJECT_PERIOD

    # 5) Missing supporting documents
    att_count = entry.attachments.using(using).count()
    if att_count == 0:
        details["missing_documents"] = POINTS_MISSING_DOCS
        score += POINTS_MISSING_DOCS

    # 6) Round-number payment (total debit/credit is round)
    lines = list(entry.lines.using(using).all())
    total_debit = sum((l.debit or Decimal("0")) for l in lines)
    total_credit = sum((l.credit or Decimal("0")) for l in lines)
    amount = total_debit if total_debit else total_credit
    if amount > 0 and amount % ROUND_NUMBER_STEP == 0:
        details["round_number"] = POINTS_ROUND_NUMBER
        score += POINTS_ROUND_NUMBER

    # 7) Late-night or weekend posting
    if entry.posted_at:
        h = entry.posted_at.hour
        is_weekend = entry.posted_at.weekday() >= 5
        if is_weekend or h >= LATE_HOUR_START or h < LATE_HOUR_END:
            details["late_posting"] = POINTS_LATE_POSTING
            score += POINTS_LATE_POSTING

    # 8) Duplicate payment: same amount, same day, same reference type (PV-)
    if ref.startswith("PV-") and amount > 0:
        dup_exists = (
            JournalEntry.objects.using(using)
            .filter(
                status=JournalEntry.Status.POSTED,
                reference__startswith="PV-",
                entry_date=entry.entry_date,
            )
            .exclude(pk=entry_id)
            .annotate(total_debit=Sum("lines__debit"))
            .filter(total_debit=amount)
            .exists()
        )
        if dup_exists:
            details["duplicate_payment"] = POINTS_DUPLICATE_PAYMENT
            score += POINTS_DUPLICATE_PAYMENT

    # 9) Over budget (simplified: check grant budget vs spent)
    if entry.grant_id and amount > 0:
        try:
            from tenant_grants.models import BudgetLine
            budget_total = (
                BudgetLine.objects.using(using)
                .filter(grant_id=entry.grant_id)
                .aggregate(s=Sum("amount"))
                .get("s") or Decimal("0")
            )
            spent = (
                JournalLine.objects.using(using)
                .filter(entry__grant_id=entry.grant_id, entry__status=JournalEntry.Status.POSTED)
                .aggregate(s=Sum("debit"))
                .get("s") or Decimal("0")
            )
            if budget_total > 0 and spent > budget_total:
                details["over_budget"] = POINTS_OVER_BUDGET
                score += POINTS_OVER_BUDGET
        except Exception:
            pass

    score = min(100, score)
    level = _get_level(score)

    # Save assessment
    tra, _ = TransactionRiskAssessment.objects.using(using).update_or_create(
        source_type="journalentry",
        source_id=entry_id,
        defaults={
            "risk_score": score,
            "risk_level": level,
            "details": details,
            "indicator_summary": ", ".join(details.keys()) or "none",
        },
    )

    # Create alert and optionally investigation if above threshold
    threshold = getattr(
        __import__("django.conf", fromlist=["settings"]).settings,
        "AUDIT_RISK_ALERT_THRESHOLD",
        DEFAULT_ALERT_THRESHOLD,
    )
    inv_threshold = getattr(
        __import__("django.conf", fromlist=["settings"]).settings,
        "AUDIT_RISK_INVESTIGATION_THRESHOLD",
        DEFAULT_INVESTIGATION_THRESHOLD,
    )
    auto_investigate = getattr(
        __import__("django.conf", fromlist=["settings"]).settings,
        "AUDIT_RISK_AUTO_INVESTIGATE",
        False,
    )

    if score >= threshold:
        severity = "critical" if score >= inv_threshold else "high" if score >= 61 else "medium"
        alert_type = "fraud"
        if "duplicate_payment" in details:
            alert_type = "duplicate_payment"
        elif "backdated" in details or "future_dated" in details:
            alert_type = "backdated"
        elif "over_budget" in details:
            alert_type = "budget_violation"
        elif "same_user_approve" in details:
            alert_type = "segregation_violation"

        alert = RiskAlert.objects.using(using).create(
            assessment=tra,
            alert_type=alert_type,
            severity=severity,
            title=f"Risk alert: {entry.reference or f'JE#{entry_id}'} (score {score})",
            description=tra.indicator_summary,
            status=RiskAlert.Status.OPEN,
        )
        if auto_investigate and score >= inv_threshold:
            case = InvestigationCase.objects.using(using).create(
                title=f"Investigation: {entry.reference or f'JE#{entry_id}'}",
                status=InvestigationCase.Status.OPEN,
                priority=InvestigationCase.Priority.HIGH if score < 90 else InvestigationCase.Priority.CRITICAL,
                summary=f"Auto-opened due to risk score {score}. Indicators: {tra.indicator_summary}.",
            )
            alert.investigation = case
            alert.save(using=using, update_fields=["investigation_id"])

    return {
        "score": score,
        "level": level,
        "details": details,
        "assessment_id": tra.id,
    }
