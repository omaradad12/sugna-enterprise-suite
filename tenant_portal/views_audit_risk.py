"""
Audit & Risk Management module views.
All views use tenant_portal layout with active_submenu='audit_risk'.
"""
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages

from tenant_portal.decorators import tenant_view


def _audit_risk_context(request: HttpRequest, active_item: str, **extra):
    """Base context for Audit & Risk pages."""
    ctx = {
        "tenant": request.tenant,
        "tenant_user": request.tenant_user,
        "active_submenu": "audit_risk",
        "active_item": active_item,
    }
    ctx.update(extra)
    return ctx


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_home_view(request: HttpRequest) -> HttpResponse:
    """Audit Dashboard: KPIs, trend, findings lifecycle, risk by grant."""
    from decimal import Decimal
    from django.db.models import Count, Sum
    from django.utils import timezone
    from tenant_audit_risk.models import RiskAlert, TransactionRiskAssessment, InvestigationCase, AuditFinding

    tenant_db = request.tenant_db
    # System alerts / risk KPIs
    fraud_alerts_count = RiskAlert.objects.using(tenant_db).filter(alert_type="fraud").count()
    high_risk_count = TransactionRiskAssessment.objects.using(tenant_db).filter(
        risk_level__in=["high", "critical"]
    ).count()
    open_investigations = InvestigationCase.objects.using(tenant_db).filter(
        status__in=["open", "in_progress"]
    ).count()
    control_violations = RiskAlert.objects.using(tenant_db).filter(
        alert_type="control_violation", status="open"
    ).count()
    # Findings lifecycle KPIs
    confirmed_findings_count = AuditFinding.objects.using(tenant_db).filter(
        finding_stage=AuditFinding.FindingStage.CONFIRMED
    ).count()
    realized_findings_count = AuditFinding.objects.using(tenant_db).filter(
        finding_stage=AuditFinding.FindingStage.REALIZED
    ).count()
    realized_qs = AuditFinding.objects.using(tenant_db).filter(finding_stage=AuditFinding.FindingStage.REALIZED)
    financial_loss_total = realized_qs.aggregate(s=Sum("financial_impact"))["s"] or Decimal("0")
    recovered_total = realized_qs.aggregate(s=Sum("recovered_amount"))["s"] or Decimal("0")
    outstanding_exposure_total = realized_qs.aggregate(s=Sum("unrecovered_amount"))["s"] or Decimal("0")
    # Recent alerts for trend (last 30 days)
    from datetime import timedelta
    from django.db.models.functions import TruncDate, TruncMonth
    since = timezone.now() - timedelta(days=30)
    alerts_by_day = (
        RiskAlert.objects.using(tenant_db)
        .filter(created_at__gte=since)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(n=Count("id"))
        .order_by("day")
    )
    trend_data = [{"day": str(r["day"]), "count": r["n"]} for r in alerts_by_day]
    # Risk investigation register KPIs (high/critical only)
    high_critical = TransactionRiskAssessment.objects.using(tenant_db).filter(
        risk_level__in=["high", "critical"]
    )
    risk_register_total = high_critical.count()
    risk_register_open = high_critical.filter(
        investigation_status__in=["detected", "under_review"]
    ).count()
    risk_register_under_review = high_critical.filter(
        investigation_status="under_review"
    ).count()
    risk_register_cleared = high_critical.filter(
        investigation_status="cleared"
    ).count()
    # Monthly risk trend (high/critical assessments by month, last 12 months)
    twelve_months_ago = timezone.now() - timedelta(days=365)
    monthly_risk = (
        high_critical.filter(assessed_at__gte=twelve_months_ago)
        .annotate(month=TruncMonth("assessed_at"))
        .values("month")
        .annotate(n=Count("id"))
        .order_by("month")
    )
    risk_trend_monthly = [{"month": str(r["month"])[:7], "count": r["n"]} for r in monthly_risk]
    # Risk by grant (from assessments linked to journalentry with grant)
    risk_by_grant = []
    try:
        from tenant_finance.models import JournalEntry
        je_ids = list(
            TransactionRiskAssessment.objects.using(tenant_db)
            .filter(source_type="journalentry", risk_level__in=["high", "critical"])
            .values_list("source_id", flat=True)[:100]
        )
        if je_ids:
            rows = (
                JournalEntry.objects.using(tenant_db)
                .filter(pk__in=je_ids)
                .values("grant__name")
                .annotate(count=Count("id"))
                .order_by("-count")[:10]
            )
            risk_by_grant = [{"name": r.get("grant__name") or "No grant", "count": r["count"]} for r in rows]
    except Exception:
        pass
    ctx = _audit_risk_context(
        request,
        "audit_risk_overview",
        fraud_alerts_count=fraud_alerts_count,
        high_risk_count=high_risk_count,
        open_investigations=open_investigations,
        control_violations=control_violations,
        risk_register_total=risk_register_total,
        risk_register_open=risk_register_open,
        risk_register_under_review=risk_register_under_review,
        risk_register_cleared=risk_register_cleared,
        risk_trend_monthly=risk_trend_monthly,
        confirmed_findings_count=confirmed_findings_count,
        realized_findings_count=realized_findings_count,
        financial_loss_total=financial_loss_total,
        recovered_total=recovered_total,
        outstanding_exposure_total=outstanding_exposure_total,
        trend_data=trend_data,
        risk_by_grant=risk_by_grant[:10],
    )
    return render(request, "tenant_portal/audit_risk/dashboard.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_screening_upload_view(request: HttpRequest) -> HttpResponse:
    """
    Audit Screening Upload: temporary upload of external documents for screening.
    Files are stored in temp storage only and deleted on Finish Screening, case close, or after max age.
    """
    from tenant_audit_risk.models import AuditScreeningSession, InvestigationCase, ScreeningUploadFile
    from tenant_audit_risk.services.screening_storage import (
        delete_session_files,
        save_upload_to_temp,
        get_session_total_size_mb,
    )

    tenant_db = request.tenant_db
    user_id = getattr(request.tenant_user, "id", None) if request.tenant_user else None
    max_file_mb = getattr(settings, "SCREENING_UPLOAD_MAX_FILE_SIZE_MB", 0)
    max_session_mb = getattr(settings, "SCREENING_UPLOAD_MAX_SESSION_SIZE_MB", 0)
    max_age_hours = getattr(settings, "SCREENING_UPLOAD_MAX_AGE_HOURS", 48)

    # POST: upload files or finish screening
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "finish_screening":
            session_id = request.POST.get("session_id")
            if not session_id:
                messages.warning(request, "No screening session selected.")
                return redirect("tenant_portal:audit_risk_screening_upload")
            session = get_object_or_404(
                AuditScreeningSession.objects.using(tenant_db),
                pk=session_id,
                status=AuditScreeningSession.Status.ACTIVE,
            )
            session.screening_summary = request.POST.get("screening_summary", "").strip()
            session.auditor_notes = request.POST.get("auditor_notes", "").strip()
            session.status = AuditScreeningSession.Status.FINISHED
            session.finished_at = timezone.now()
            session.save(using=tenant_db)
            deleted = delete_session_files(session.id)
            ScreeningUploadFile.objects.using(tenant_db).filter(session=session).delete()
            messages.success(
                request,
                f"Screening finished. Summary and notes have been saved. {deleted} temporary file(s) were removed and were not stored permanently.",
            )
            return redirect("tenant_portal:audit_risk_screening_upload")

        if action == "upload" or not action:
            session_id = request.POST.get("session_id")
            if session_id:
                session = get_object_or_404(
                    AuditScreeningSession.objects.using(tenant_db),
                    pk=session_id,
                    status=AuditScreeningSession.Status.ACTIVE,
                )
            else:
                session = AuditScreeningSession.objects.using(tenant_db).create(
                    auditor_user_id=user_id,
                    status=AuditScreeningSession.Status.ACTIVE,
                    expires_at=timezone.now() + timezone.timedelta(hours=max_age_hours),
                )
            files = request.FILES.getlist("screening_files")
            if not files:
                messages.warning(request, "Select one or more files to upload.")
                return redirect(reverse("tenant_portal:audit_risk_screening_upload") + f"?session_id={session.id}")
            current_mb = get_session_total_size_mb(session.id)
            for f in files:
                size_mb = f.size / (1024 * 1024)
                if max_file_mb > 0 and size_mb > max_file_mb:
                    messages.error(
                        request,
                        f"File {getattr(f, 'name', '')} exceeds the maximum size of {max_file_mb} MB per file.",
                    )
                    return redirect(reverse("tenant_portal:audit_risk_screening_upload") + f"?session_id={session.id}")
                if max_session_mb > 0 and (current_mb + size_mb) > max_session_mb:
                    messages.error(
                        request,
                        f"Session total would exceed the limit of {max_session_mb} MB. Upload smaller or fewer files.",
                    )
                    return redirect(reverse("tenant_portal:audit_risk_screening_upload") + f"?session_id={session.id}")
                rel_path = save_upload_to_temp(
                    session.id,
                    f,
                    original_name=getattr(f, "name", None),
                )
                ScreeningUploadFile.objects.using(tenant_db).create(
                    session=session,
                    temp_file_path=rel_path,
                    original_filename=getattr(f, "name", "") or "upload",
                    file_size=f.size,
                    content_type=getattr(f, "content_type", "") or "",
                )
                current_mb += size_mb
            messages.success(request, f"{len(files)} file(s) added to screening. They will be deleted when you finish screening or after {max_age_hours} hours.")
            return redirect(reverse("tenant_portal:audit_risk_screening_upload") + f"?session_id={session.id}")

        if action == "new_session":
            session = AuditScreeningSession.objects.using(tenant_db).create(
                auditor_user_id=user_id,
                status=AuditScreeningSession.Status.ACTIVE,
                expires_at=timezone.now() + timezone.timedelta(hours=max_age_hours),
            )
            return redirect(reverse("tenant_portal:audit_risk_screening_upload") + f"?session_id={session.id}")

    # GET: show session or list
    session_id = request.GET.get("session_id")
    session = None
    files = []
    if session_id:
        session = (
            AuditScreeningSession.objects.using(tenant_db)
            .filter(pk=session_id)
            .prefetch_related("uploaded_files")
            .first()
        )
        if session and session.status == AuditScreeningSession.Status.ACTIVE:
            files = list(session.uploaded_files.all())

    # Active sessions for this user (for dropdown or "current" display)
    active_sessions = (
        AuditScreeningSession.objects.using(tenant_db)
        .filter(status=AuditScreeningSession.Status.ACTIVE, auditor_user_id=user_id)
        .order_by("-created_at")[:20]
    )
    cases = InvestigationCase.objects.using(tenant_db).filter(
        status__in=[InvestigationCase.Status.OPEN, InvestigationCase.Status.IN_PROGRESS]
    ).order_by("title")[:100]

    ctx = _audit_risk_context(
        request,
        "audit_risk_screening",
        session=session,
        files=files,
        active_sessions=active_sessions,
        cases=cases,
        max_file_mb=max_file_mb,
        max_session_mb=max_session_mb,
        max_age_hours=max_age_hours,
    )
    return render(request, "tenant_portal/audit_risk/screening_upload.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_fraud_alerts_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import RiskAlert
    alerts = RiskAlert.objects.using(request.tenant_db).select_related("assessment").order_by("-created_at")[:100]
    ctx = _audit_risk_context(request, "audit_risk_fraud_alerts", alerts=alerts)
    return render(request, "tenant_portal/audit_risk/fraud_alerts.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_high_risk_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import TransactionRiskAssessment
    from tenant_grants.models import Grant
    from tenant_users.models import TenantUser

    tenant_db = request.tenant_db
    qs = (
        TransactionRiskAssessment.objects.using(tenant_db)
        .filter(risk_level__in=["high", "critical"])
        .select_related("grant")
        .order_by("-risk_score", "-assessed_at")
    )
    # Filters
    project = request.GET.get("project", "").strip()
    if project:
        qs = qs.filter(grant_id=project)
    period_from = request.GET.get("period_from", "").strip()
    if period_from:
        qs = qs.filter(assessed_at__date__gte=period_from)
    period_to = request.GET.get("period_to", "").strip()
    if period_to:
        qs = qs.filter(assessed_at__date__lte=period_to)
    module = request.GET.get("module", "").strip()
    if module:
        qs = qs.filter(module__icontains=module)
    vendor = request.GET.get("vendor", "").strip()
    if vendor:
        qs = qs.filter(vendor_display__icontains=vendor)
    risk_indicator = request.GET.get("risk_indicator", "").strip()
    if risk_indicator:
        qs = qs.filter(indicator_summary__icontains=risk_indicator)
    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        qs = qs.filter(investigation_status=status_filter)

    assessments = list(qs[:200])
    # Resolve assigned investigator names
    assigned_ids = {a.assigned_to_id for a in assessments if a.assigned_to_id}
    assigned_map = {}
    if assigned_ids:
        for u in TenantUser.objects.using(tenant_db).filter(pk__in=assigned_ids).values("id", "full_name", "email"):
            assigned_map[u["id"]] = u.get("full_name") or u.get("email") or f"User #{u['id']}"
    for a in assessments:
        a.assigned_display = assigned_map.get(a.assigned_to_id, "—") if a.assigned_to_id else "—"
    projects = list(
        Grant.objects.using(tenant_db).filter(status="active").order_by("code").values_list("id", "code", "title")
    )
    tenant_users = list(
        TenantUser.objects.using(tenant_db).filter(is_active=True).order_by("full_name", "email").values("id", "full_name", "email")
    )
    selected_project_id = int(project) if project and project.isdigit() else None
    ctx = _audit_risk_context(
        request,
        "audit_risk_high_risk",
        assessments=assessments,
        projects=projects,
        tenant_users=tenant_users,
        filter_project=project,
        selected_project_id=selected_project_id,
        filter_period_from=period_from,
        filter_period_to=period_to,
        filter_module=module,
        filter_vendor=vendor,
        filter_risk_indicator=risk_indicator,
        filter_status=status_filter,
    )
    return render(request, "tenant_portal/audit_risk/high_risk_transactions.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_high_risk_view_transaction(
    request: HttpRequest, assessment_id: int
) -> HttpResponse:
    """Redirect to the transaction (e.g. general ledger with entry focus)."""
    from tenant_audit_risk.models import TransactionRiskAssessment
    a = get_object_or_404(
        TransactionRiskAssessment.objects.using(request.tenant_db), pk=assessment_id
    )
    if a.source_type == "journalentry":
        url = reverse("tenant_portal:finance_general_ledger")
        return redirect(f"{url}?entry_id={a.source_id}")
    messages.info(request, f"Transaction: {a.source_type}#{a.source_id}")
    return redirect(reverse("tenant_portal:audit_risk_high_risk"))


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_high_risk_assign_view(
    request: HttpRequest, assessment_id: int
) -> HttpResponse:
    """POST: set assigned investigator for this risk assessment."""
    if request.method != "POST":
        return redirect(reverse("tenant_portal:audit_risk_high_risk"))
    from tenant_audit_risk.models import TransactionRiskAssessment
    a = get_object_or_404(
        TransactionRiskAssessment.objects.using(request.tenant_db), pk=assessment_id
    )
    user_id = request.POST.get("assigned_to_id", "").strip()
    if user_id.isdigit():
        a.assigned_to_id = int(user_id)
        a.investigation_status = TransactionRiskAssessment.InvestigationStatus.UNDER_REVIEW
        a.save(update_fields=["assigned_to_id", "investigation_status"])
        messages.success(request, "Investigator assigned.")
    else:
        messages.warning(request, "Select a user.")
    return redirect(request.META.get("HTTP_REFERER") or reverse("tenant_portal:audit_risk_high_risk"))


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_high_risk_clear_view(
    request: HttpRequest, assessment_id: int
) -> HttpResponse:
    """POST: mark risk as cleared."""
    if request.method != "POST":
        return redirect(reverse("tenant_portal:audit_risk_high_risk"))
    from tenant_audit_risk.models import TransactionRiskAssessment
    a = get_object_or_404(
        TransactionRiskAssessment.objects.using(request.tenant_db), pk=assessment_id
    )
    a.investigation_status = TransactionRiskAssessment.InvestigationStatus.CLEARED
    a.save(update_fields=["investigation_status"])
    messages.success(request, "Risk marked as cleared.")
    return redirect(request.META.get("HTTP_REFERER") or reverse("tenant_portal:audit_risk_high_risk"))


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_high_risk_close_view(
    request: HttpRequest, assessment_id: int
) -> HttpResponse:
    """POST: mark risk as closed."""
    if request.method != "POST":
        return redirect(reverse("tenant_portal:audit_risk_high_risk"))
    from tenant_audit_risk.models import TransactionRiskAssessment
    a = get_object_or_404(
        TransactionRiskAssessment.objects.using(request.tenant_db), pk=assessment_id
    )
    a.investigation_status = TransactionRiskAssessment.InvestigationStatus.CLOSED
    a.save(update_fields=["investigation_status"])
    messages.success(request, "Risk marked as closed.")
    return redirect(request.META.get("HTTP_REFERER") or reverse("tenant_portal:audit_risk_high_risk"))


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_high_risk_convert_to_finding_view(
    request: HttpRequest, assessment_id: int
) -> HttpResponse:
    """POST: create a preliminary audit finding from this risk assessment."""
    if request.method != "POST":
        return redirect(reverse("tenant_portal:audit_risk_high_risk"))
    from tenant_audit_risk.models import TransactionRiskAssessment, AuditFinding, RiskAlert
    a = get_object_or_404(
        TransactionRiskAssessment.objects.using(request.tenant_db), pk=assessment_id
    )
    alert = RiskAlert.objects.using(request.tenant_db).filter(assessment=a).first()
    finding = AuditFinding.objects.using(request.tenant_db).create(
        title=f"From risk: {a.source_type}#{a.source_id}",
        description=a.indicator_summary or f"Risk score {a.risk_score}, level {a.risk_level}.",
        finding_stage=AuditFinding.FindingStage.PRELIMINARY,
        status=AuditFinding.Status.OPEN,
        alert=alert,
    )
    a.investigation_status = TransactionRiskAssessment.InvestigationStatus.CONVERTED_TO_FINDING
    a.save(update_fields=["investigation_status"])
    messages.success(request, f"Audit finding created: {finding.title}")
    return redirect(reverse("tenant_portal:audit_risk_findings"))


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_high_risk_request_correction_view(
    request: HttpRequest, assessment_id: int
) -> HttpResponse:
    """GET: show form. POST: create correction request for the source transaction."""
    from tenant_audit_risk.models import (
        TransactionRiskAssessment,
        AuditCorrectionRequest,
    )
    from tenant_users.models import TenantUser
    a = get_object_or_404(
        TransactionRiskAssessment.objects.using(request.tenant_db), pk=assessment_id
    )
    if request.method == "POST":
        assigned_to_id = request.POST.get("assigned_to_id", "").strip()
        if not assigned_to_id.isdigit():
            messages.warning(request, "Select a user to assign the correction to.")
        else:
            instructions = request.POST.get("instructions", "").strip() or "Please review and correct."
            AuditCorrectionRequest.objects.using(request.tenant_db).create(
                source_type=a.source_type,
                source_id=a.source_id,
                assigned_to_id=int(assigned_to_id),
                instructions=instructions,
                created_by_id=getattr(request.tenant_user, "id", None),
            )
            a.investigation_status = TransactionRiskAssessment.InvestigationStatus.CORRECTION_REQUESTED
            a.save(update_fields=["investigation_status"])
            messages.success(request, "Correction request created.")
            return redirect(reverse("tenant_portal:audit_risk_high_risk"))
    users = list(
        TenantUser.objects.using(request.tenant_db).filter(is_active=True).order_by("full_name", "email")
    )
    ctx = _audit_risk_context(
        request, "audit_risk_high_risk", assessment=a, tenant_users=users
    )
    return render(
        request,
        "tenant_portal/audit_risk/high_risk_request_correction.html",
        ctx,
    )


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_control_violations_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import RiskAlert
    alerts = (
        RiskAlert.objects.using(request.tenant_db)
        .filter(alert_type="control_violation")
        .order_by("-created_at")[:100]
    )
    ctx = _audit_risk_context(request, "audit_risk_control_violations", alerts=alerts)
    return render(request, "tenant_portal/audit_risk/control_violations.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_suspicious_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import TransactionRiskAssessment
    list_qs = (
        TransactionRiskAssessment.objects.using(request.tenant_db)
        .filter(risk_score__gte=31)
        .order_by("-risk_score")[:100]
    )
    ctx = _audit_risk_context(request, "audit_risk_suspicious", assessments=list_qs)
    return render(request, "tenant_portal/audit_risk/suspicious_transactions.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_duplicate_payments_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import RiskAlert
    alerts = (
        RiskAlert.objects.using(request.tenant_db)
        .filter(alert_type="duplicate_payment")
        .order_by("-created_at")[:100]
    )
    ctx = _audit_risk_context(request, "audit_risk_dup_payments", alerts=alerts)
    return render(request, "tenant_portal/audit_risk/duplicate_payments.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_budget_violations_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import RiskAlert
    alerts = (
        RiskAlert.objects.using(request.tenant_db)
        .filter(alert_type="budget_violation")
        .order_by("-created_at")[:100]
    )
    ctx = _audit_risk_context(request, "audit_risk_budget_violations", alerts=alerts)
    return render(request, "tenant_portal/audit_risk/budget_violations.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_backdated_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import RiskAlert
    alerts = (
        RiskAlert.objects.using(request.tenant_db)
        .filter(alert_type="backdated")
        .order_by("-created_at")[:100]
    )
    ctx = _audit_risk_context(request, "audit_risk_backdated", alerts=alerts)
    return render(request, "tenant_portal/audit_risk/backdated_entries.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_unusual_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import TransactionRiskAssessment
    list_qs = (
        TransactionRiskAssessment.objects.using(request.tenant_db)
        .filter(details__has_key="late_posting")
        .order_by("-assessed_at")[:100]
    )
    ctx = _audit_risk_context(request, "audit_risk_unusual", assessments=list_qs)
    return render(request, "tenant_portal/audit_risk/unusual_activity.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_scanner_view(request: HttpRequest) -> HttpResponse:
    ctx = _audit_risk_context(request, "audit_risk_scanner")
    return render(request, "tenant_portal/audit_risk/fraud_scanner.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_vendor_risk_view(request: HttpRequest) -> HttpResponse:
    ctx = _audit_risk_context(request, "audit_risk_vendor_risk")
    return render(request, "tenant_portal/audit_risk/vendor_risk.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_payroll_fraud_view(request: HttpRequest) -> HttpResponse:
    ctx = _audit_risk_context(request, "audit_risk_payroll_fraud")
    return render(request, "tenant_portal/audit_risk/payroll_fraud.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_procurement_fraud_view(request: HttpRequest) -> HttpResponse:
    ctx = _audit_risk_context(request, "audit_risk_procurement_fraud")
    return render(request, "tenant_portal/audit_risk/procurement_fraud.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_master_data_log_view(request: HttpRequest) -> HttpResponse:
    ctx = _audit_risk_context(request, "audit_risk_master_log")
    return render(request, "tenant_portal/audit_risk/master_data_log.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_user_activity_view(request: HttpRequest) -> HttpResponse:
    from tenant_finance.models import AuditLog
    logs = AuditLog.objects.using(request.tenant_db).order_by("-changed_at")[:200]
    ctx = _audit_risk_context(request, "audit_risk_user_activity", logs=logs)
    return render(request, "tenant_portal/audit_risk/user_activity_log.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_approval_history_view(request: HttpRequest) -> HttpResponse:
    from tenant_finance.models import AuditLog
    logs = (
        AuditLog.objects.using(request.tenant_db)
        .filter(summary__icontains="approv")
        .order_by("-changed_at")[:200]
    )
    ctx = _audit_risk_context(request, "audit_risk_approval_history", logs=logs)
    return render(request, "tenant_portal/audit_risk/approval_history.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_exception_register_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import RiskAlert
    alerts = RiskAlert.objects.using(request.tenant_db).order_by("-created_at")[:100]
    ctx = _audit_risk_context(request, "audit_risk_exceptions", alerts=alerts)
    return render(request, "tenant_portal/audit_risk/exception_register.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_risk_alerts_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import RiskAlert
    alerts = RiskAlert.objects.using(request.tenant_db).select_related("assessment").order_by("-created_at")[:100]
    ctx = _audit_risk_context(request, "audit_risk_risk_alerts", alerts=alerts)
    return render(request, "tenant_portal/audit_risk/risk_alerts.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_control_breaches_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import RiskAlert
    alerts = (
        RiskAlert.objects.using(request.tenant_db)
        .filter(alert_type__in=["control_violation", "segregation_violation"])
        .order_by("-created_at")[:100]
    )
    ctx = _audit_risk_context(request, "audit_risk_control_breaches", alerts=alerts)
    return render(request, "tenant_portal/audit_risk/control_breaches.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_investigations_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import InvestigationCase
    cases = InvestigationCase.objects.using(request.tenant_db).order_by("-created_at")[:100]
    ctx = _audit_risk_context(request, "audit_risk_investigations", cases=cases)
    return render(request, "tenant_portal/audit_risk/investigations.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_evidence_view(request: HttpRequest) -> HttpResponse:
    ctx = _audit_risk_context(request, "audit_risk_evidence")
    return render(request, "tenant_portal/audit_risk/evidence.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_investigator_notes_view(request: HttpRequest) -> HttpResponse:
    ctx = _audit_risk_context(request, "audit_risk_notes")
    return render(request, "tenant_portal/audit_risk/investigator_notes.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_case_status_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import InvestigationCase
    cases = InvestigationCase.objects.using(request.tenant_db).order_by("-created_at")[:100]
    ctx = _audit_risk_context(request, "audit_risk_case_status", cases=cases)
    return render(request, "tenant_portal/audit_risk/case_status.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_control_rules_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import ControlRule
    rules = ControlRule.objects.using(request.tenant_db).filter(is_active=True).order_by("name")
    ctx = _audit_risk_context(request, "audit_risk_control_rules", rules=rules)
    return render(request, "tenant_portal/audit_risk/control_rules.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_compliance_view(request: HttpRequest) -> HttpResponse:
    ctx = _audit_risk_context(request, "audit_risk_compliance")
    return render(request, "tenant_portal/audit_risk/compliance.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_policy_violations_view(request: HttpRequest) -> HttpResponse:
    ctx = _audit_risk_context(request, "audit_risk_policy_violations")
    return render(request, "tenant_portal/audit_risk/policy_violations.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_findings_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import AuditFinding
    findings = AuditFinding.objects.using(request.tenant_db).order_by("-created_at")[:100]
    ctx = _audit_risk_context(request, "audit_risk_findings", findings=findings)
    return render(request, "tenant_portal/audit_risk/audit_findings.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_confirmed_findings_view(request: HttpRequest) -> HttpResponse:
    """Register of confirmed findings (validated; lifecycle stage = confirmed)."""
    from tenant_audit_risk.models import AuditFinding
    findings = (
        AuditFinding.objects.using(request.tenant_db)
        .filter(finding_stage=AuditFinding.FindingStage.CONFIRMED)
        .select_related("alert")
        .order_by("-confirmed_at", "-created_at")[:100]
    )
    ctx = _audit_risk_context(request, "audit_risk_confirmed_findings", findings=findings)
    return render(request, "tenant_portal/audit_risk/confirmed_findings.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_realized_findings_view(request: HttpRequest) -> HttpResponse:
    """Register of realized findings (impact materialized; financial impact and recovery)."""
    from tenant_audit_risk.models import AuditFinding
    findings = (
        AuditFinding.objects.using(request.tenant_db)
        .filter(finding_stage=AuditFinding.FindingStage.REALIZED)
        .select_related("alert")
        .order_by("-realized_at", "-created_at")[:100]
    )
    ctx = _audit_risk_context(request, "audit_risk_realized_findings", findings=findings)
    return render(request, "tenant_portal/audit_risk/realized_findings.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_finding_promote_view(
    request: HttpRequest, finding_id: int
) -> HttpResponse:
    """POST-only: promote a finding from preliminary→confirmed or confirmed→realized."""
    if request.method != "POST":
        return redirect(reverse("tenant_portal:audit_risk_findings"))
    from tenant_audit_risk.models import AuditFinding

    finding = get_object_or_404(
        AuditFinding.objects.using(request.tenant_db), pk=finding_id
    )
    action = (request.POST.get("action") or "").strip().lower()
    if action == "confirm":
        if finding.finding_stage == AuditFinding.FindingStage.PRELIMINARY:
            finding.finding_stage = AuditFinding.FindingStage.CONFIRMED
            finding.is_actual = True
            finding.confirmed_at = timezone.now()
            finding.save(update_fields=["finding_stage", "is_actual", "confirmed_at"])
            messages.success(request, "Finding confirmed.")
        else:
            messages.warning(request, "Only preliminary findings can be confirmed.")
    elif action == "realize":
        if finding.finding_stage == AuditFinding.FindingStage.CONFIRMED:
            finding.finding_stage = AuditFinding.FindingStage.REALIZED
            finding.is_realized = True
            finding.realized_at = timezone.now()
            finding.save(update_fields=["finding_stage", "is_realized", "realized_at"])
            messages.success(request, "Finding marked as realized.")
        else:
            messages.warning(request, "Only confirmed findings can be marked as realized.")
    else:
        messages.error(request, "Invalid action.")
    return redirect(reverse("tenant_portal:audit_risk_findings"))


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_management_letter_view(request: HttpRequest) -> HttpResponse:
    ctx = _audit_risk_context(request, "audit_risk_management_letter")
    return render(request, "tenant_portal/audit_risk/management_letter.html", ctx)


@tenant_view(
    require_module="audit_risk",
    require_perm_any=["module:audit_risk.view", "finance:audit.view"],
)
def audit_risk_recommendations_view(request: HttpRequest) -> HttpResponse:
    from tenant_audit_risk.models import AuditFinding
    findings = AuditFinding.objects.using(request.tenant_db).filter(status="open").order_by("due_date")[:100]
    ctx = _audit_risk_context(request, "audit_risk_recommendations", findings=findings)
    return render(request, "tenant_portal/audit_risk/recommendations.html", ctx)
