from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.db.models import Q

from tenant_portal.decorators import tenant_view
from tenant_portal.views import (
    _accounting_period_label_for_date,
    _finance_assert_open_period,
    _finance_export_csv_url,
    _finance_generate_adjusting_journal_number,
    _finance_journal_gl_date,
    _finance_validate_journal_line_grants,
    _finance_validate_journal_payload,
    _parse_finance_filters,
)


def _fund_label_from_grant(grant, tenant_db: str) -> str:
    """Derive fund label from project default mapping (cost center) or project code."""
    if not grant or not getattr(grant, "project_id", None):
        return "—"
    from tenant_finance.models import ProjectDimensionMapping

    m = (
        ProjectDimensionMapping.objects.using(tenant_db)
        .filter(project_id=grant.project_id)
        .select_related("cost_center")
        .first()
    )
    if m and m.cost_center_id:
        cc = m.cost_center
        return f"{cc.code} — {cc.name}"
    p = grant.project
    return f"{p.code} — {p.name}"


def _annotate_grants_for_form(qs, tenant_db: str):
    out = []
    for g in qs:
        out.append(
            {
                "id": g.id,
                "code": g.code,
                "title": g.title,
                "label": f"{g.code} — {g.title}",
                "donor_id": g.donor_id,
                "fund_label": _fund_label_from_grant(g, tenant_db),
            }
        )
    return out


@tenant_view(require_module="finance_grants", require_perm="finance:journals.adjusting")
def finance_adjusting_journals_view(request: HttpRequest) -> HttpResponse:
    """
    Core Accounting → Journal management → Adjusting Journals
    """

    from tenant_finance.models import ChartAccount, FiscalPeriod, JournalEntry
    from tenant_users.models import TenantUser
    from rbac.models import user_has_permission as _user_has_permission
    from tenant_grants.models import Grant, Donor

    tenant_db = request.tenant_db

    f = _parse_finance_filters(request)

    journal_no = (request.GET.get("journal_no") or "").strip()
    status = (request.GET.get("status") or "").strip()
    account_id = (request.GET.get("account_id") or "").strip()
    created_by = (request.GET.get("created_by") or "").strip()
    accounting_period_id = (
        request.GET.get("accounting_period_id") or request.GET.get("fiscal_period_id") or ""
    ).strip()

    entries_qs = (
        JournalEntry.objects.using(tenant_db)
        .prefetch_related("lines", "lines__account", "grant", "created_by", "approved_by")
        .filter(source="manual", journal_type="adjusting_journal")
        .order_by("-entry_date", "-id")
    )

    date_start = f["period_start"]
    date_end = f["period_end"]
    if accounting_period_id:
        period = (
            FiscalPeriod.objects.using(tenant_db)
            .filter(pk=accounting_period_id)
            .first()
        )
        if period:
            date_start = period.start_date
            date_end = period.end_date

    entries_qs = entries_qs.filter(entry_date__gte=date_start, entry_date__lte=date_end)

    if f["grant_id"]:
        entries_qs = entries_qs.filter(grant_id=f["grant_id"])
    if f["donor_id"]:
        entries_qs = entries_qs.filter(grant__donor_id=f["donor_id"])
    if status:
        entries_qs = entries_qs.filter(status=status)
    if journal_no:
        entries_qs = entries_qs.filter(reference__icontains=journal_no)
    if account_id:
        entries_qs = entries_qs.filter(lines__account_id=account_id).distinct()
    if created_by:
        entries_qs = entries_qs.filter(
            Q(created_by__full_name__icontains=created_by)
            | Q(created_by__email__icontains=created_by)
        )

    entries_qs = entries_qs[:200]

    accounting_periods_all = list(
        FiscalPeriod.objects.using(tenant_db)
        .select_related("fiscal_year")
        .order_by("-start_date")
    )

    entries: list[dict] = []
    for entry in entries_qs:
        lines = list(entry.lines.all())
        debit_total = sum((l.debit or Decimal("0")) for l in lines) if lines else Decimal("0")
        credit_total = sum((l.credit or Decimal("0")) for l in lines) if lines else Decimal("0")
        journal_no_display = entry.reference or _finance_generate_adjusting_journal_number(
            tenant_db, entry.entry_date
        )
        pd = getattr(entry, "posting_date", None) or entry.entry_date
        adj_raw = getattr(entry, "adjustment_type", "") or ""
        adj_display = entry.get_adjustment_type_display() if adj_raw else "—"
        entries.append(
            {
                "id": entry.id,
                "journal_no": journal_no_display,
                "date": entry.entry_date,
                "posting_date": pd,
                "accounting_period_label": _accounting_period_label_for_date(accounting_periods_all, pd),
                "reference": entry.reference,
                "memo": entry.memo,
                "grant": entry.grant,
                "status": entry.status,
                "debit_total": debit_total,
                "credit_total": credit_total,
                "created_by": entry.created_by,
                "approved_by": entry.approved_by,
                "posted_at": entry.posted_at,
                "adjustment_type": adj_raw,
                "adjustment_type_display": adj_display,
            }
        )

    grants = Grant.objects.using(tenant_db).filter(status="active").order_by("code")
    donors = Donor.objects.using(tenant_db).order_by("name")
    accounts = ChartAccount.objects.using(tenant_db).filter(is_active=True).order_by("code")
    accounting_periods_qs = (
        FiscalPeriod.objects.using(tenant_db)
        .select_related("fiscal_year")
        .order_by("fiscal_year__start_date", "period_number")
    )
    created_by_users = (
        TenantUser.objects.using(tenant_db)
        .filter(is_active=True)
        .order_by("full_name", "email")
    )

    can_create = _user_has_permission(
        request.tenant_user, "finance:journals.create", using=tenant_db
    )
    can_submit = can_create
    can_manage = _user_has_permission(
        request.tenant_user, "module:finance.manage", using=tenant_db
    )
    can_approve = _user_has_permission(
        request.tenant_user, "finance:journals.approve", using=tenant_db
    )
    can_post = _user_has_permission(request.tenant_user, "finance:journals.post", using=tenant_db)

    if request.GET.get("format") == "csv":
        import csv

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="adjusting_journals.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "Journal No",
                "Journal Date",
                "Posting Date",
                "Accounting period",
                "Reference",
                "Description",
                "Adjustment Type",
                "Project / Grant",
                "Debit Total",
                "Credit Total",
                "Status",
                "Created By",
                "Approved By",
                "Posted Date",
            ]
        )
        for e in entries:
            writer.writerow(
                [
                    e["journal_no"],
                    e["date"],
                    e["posting_date"],
                    e["accounting_period_label"],
                    e["reference"] or "",
                    e["memo"] or "",
                    e["adjustment_type_display"],
                    getattr(e["grant"], "code", ""),
                    e["debit_total"],
                    e["credit_total"],
                    e["status"],
                    getattr(e["created_by"], "full_name", "") or getattr(e["created_by"], "email", ""),
                    getattr(e["approved_by"], "full_name", "")
                    or getattr(e["approved_by"], "email", ""),
                    e["posted_at"],
                ]
            )
        return response

    return render(
        request,
        "tenant_portal/finance/adjusting_journals.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "entries": entries,
            "filters": f,
            "journal_filters": {
                "journal_no": journal_no,
                "status": status,
                "account_id": account_id,
                "created_by": created_by,
                "accounting_period_id": accounting_period_id,
            },
            "grants": grants,
            "donors": donors,
            "export_csv_url": _finance_export_csv_url(request),
            "journal_statuses": JournalEntry.Status,
            "accounts": accounts,
            "accounting_periods": accounting_periods_qs,
            "created_by_users": created_by_users,
            "can_create_journals": can_create,
            "can_submit_journals": can_submit,
            "can_manage_journals": can_manage,
            "can_approve_journals": can_approve,
            "can_post_journals": can_post,
            "active_submenu": "core",
            "active_item": "core_adjusting",
        },
    )


@require_http_methods(["GET", "POST"])
@tenant_view(require_module="finance_grants", require_perm="finance:journals.adjusting")
def finance_adjusting_journal_create_view(request: HttpRequest) -> HttpResponse:
    """Full-page form: NGO adjusting journal (draft)."""
    from django.utils.dateparse import parse_date
    from django.db import transaction
    from rbac.models import user_has_permission
    from tenant_finance.models import AuditLog, JournalEntry, JournalLine, JournalEntryAttachment
    from tenant_grants.models import Grant, Donor

    tenant_db = request.tenant_db
    if not user_has_permission(request.tenant_user, "finance:journals.create", using=tenant_db):
        return render(
            request,
            "tenant_portal/forbidden.html",
            {
                "tenant": request.tenant,
                "tenant_user": request.tenant_user,
                "reason": "You do not have permission to create journal entries.",
            },
            status=403,
        )

    from tenant_finance.models import FiscalPeriod

    accounting_periods_all = list(
        FiscalPeriod.objects.using(tenant_db).select_related("fiscal_year").order_by("-start_date")
    )
    grants_qs = Grant.objects.using(tenant_db).filter(status="active").select_related("project", "donor").order_by("code")
    grant_rows = _annotate_grants_for_form(grants_qs, tenant_db)
    from tenant_finance.models import ChartAccount

    accounts = ChartAccount.objects.using(tenant_db).filter(is_active=True).order_by("code")
    accounts_json = [{"id": a.id, "label": f"{a.code} — {a.name}"} for a in accounts]
    donors = Donor.objects.using(tenant_db).order_by("name")

    adjustment_choices = list(JournalEntry.AdjustmentType.choices)

    accounting_period_rows = []
    for p in accounting_periods_all:
        sub = (p.period_name or p.name or "").strip() or f"P{p.period_number}"
        fy = getattr(p, "fiscal_year", None)
        label = f"{fy.name} — {sub}" if fy and getattr(fy, "name", None) else sub
        accounting_period_rows.append(
            {
                "start": p.start_date.isoformat(),
                "end": p.end_date.isoformat(),
                "label": label,
            }
        )

    if request.method == "POST":
        entry_date = parse_date(request.POST.get("entry_date") or "")
        posting_date = parse_date(request.POST.get("posting_date") or "")
        memo = (request.POST.get("memo") or "").strip()
        reference = (request.POST.get("reference") or "").strip()
        adjustment_type = (request.POST.get("adjustment_type") or "").strip()
        grant_id = (request.POST.get("grant_id") or "").strip()
        donor_id = (request.POST.get("donor_id") or "").strip()

        if not entry_date or not posting_date:
            messages.error(request, "Journal date and posting date are required.")
            return redirect(reverse("tenant_portal:finance_adjusting_journal_create"))
        if not memo:
            messages.error(request, "Description is required.")
            return redirect(reverse("tenant_portal:finance_adjusting_journal_create"))
        if not adjustment_type or adjustment_type not in dict(adjustment_choices):
            messages.error(request, "Please select a valid adjustment type.")
            return redirect(reverse("tenant_portal:finance_adjusting_journal_create"))

        try:
            _finance_assert_open_period(posting_date, tenant_db, request.tenant_user_id)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(reverse("tenant_portal:finance_adjusting_journal_create"))

        accounts_post = request.POST.getlist("line_account")
        debits = request.POST.getlist("line_debit")
        credits = request.POST.getlist("line_credit")
        descriptions = request.POST.getlist("line_description")
        line_grants = request.POST.getlist("line_grant")

        lines = []
        for idx in range(len(accounts_post)):
            if not accounts_post[idx]:
                continue
            lines.append(
                {
                    "account_id": accounts_post[idx],
                    "description": descriptions[idx] if idx < len(descriptions) else "",
                    "debit": debits[idx] if idx < len(debits) else "0",
                    "credit": credits[idx] if idx < len(credits) else "0",
                    "grant_id": line_grants[idx] if idx < len(line_grants) else "",
                }
            )

        header = {
            "entry_date": entry_date,
            "memo": memo,
            "grant_id": grant_id,
            "journal_type": "adjusting_journal",
            "source": "manual",
        }
        try:
            _finance_validate_journal_payload(header, lines, tenant_db)
            _finance_validate_journal_line_grants(lines, tenant_db, posting_date)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(reverse("tenant_portal:finance_adjusting_journal_create"))

        grant = None
        if grant_id:
            grant = Grant.objects.using(tenant_db).select_related("project", "donor").filter(pk=grant_id).first()
        donor = None
        if donor_id:
            donor = Donor.objects.using(tenant_db).filter(pk=donor_id).first()
        if grant and donor and grant.donor_id != donor.id:
            messages.error(request, "Donor must match the selected grant's donor.")
            return redirect(reverse("tenant_portal:finance_adjusting_journal_create"))
        if grant and not donor:
            donor = grant.donor

        with transaction.atomic(using=tenant_db):
            entry = JournalEntry(
                entry_date=entry_date,
                posting_date=posting_date,
                memo=memo,
                reference=reference,
                adjustment_type=adjustment_type,
                grant=grant,
                donor=donor,
                status=JournalEntry.Status.DRAFT,
                created_by=request.tenant_user,
                journal_type="adjusting_journal",
                source="manual",
                source_type=JournalEntry.SourceType.MANUAL,
                is_system_generated=False,
            )
            try:
                entry.full_clean()
            except DjangoValidationError as e:
                err = " ".join(f"{k}: {v}" for k, v in (e.message_dict or {}).items()) or str(e)
                messages.error(request, err)
                return redirect(reverse("tenant_portal:finance_adjusting_journal_create"))
            entry.save(using=tenant_db)

            for line in lines:
                gid = line.get("grant_id") or None
                if gid == "":
                    gid = None
                lg = None
                if gid:
                    lg = Grant.objects.using(tenant_db).filter(pk=gid).first()
                JournalLine.objects.using(tenant_db).create(
                    entry=entry,
                    account_id=line["account_id"],
                    grant=lg,
                    description=line["description"],
                    debit=Decimal(line["debit"] or "0"),
                    credit=Decimal(line["credit"] or "0"),
                )

            f = request.FILES.get("attachment")
            if f:
                JournalEntryAttachment.objects.using(tenant_db).create(
                    entry=entry,
                    file=f,
                    original_filename=getattr(f, "name", "") or "",
                    uploaded_by=request.tenant_user,
                )

            AuditLog.objects.using(tenant_db).create(
                model_name="journalentry",
                object_id=entry.id,
                action=AuditLog.Action.CREATE,
                user_id=request.tenant_user.id if request.tenant_user else None,
                username=request.tenant_user.get_full_name() if request.tenant_user else "",
                summary=f"Created adjusting journal DRAFT on {entry.entry_date}",
            )

        messages.success(request, "Adjusting journal saved as draft.")
        return redirect(reverse("tenant_portal:finance_adjusting_journals"))

    today = None
    try:
        from django.utils import timezone as _tz

        today = _tz.localdate()
    except Exception:
        pass

    return render(
        request,
        "tenant_portal/finance/adjusting_journal_form.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "grant_rows": grant_rows,
            "accounts": accounts,
            "accounts_json": accounts_json,
            "donors": donors,
            "adjustment_choices": adjustment_choices,
            "accounting_period_rows": accounting_period_rows,
            "today": today,
            "active_submenu": "core",
            "active_item": "core_adjusting",
        },
    )
