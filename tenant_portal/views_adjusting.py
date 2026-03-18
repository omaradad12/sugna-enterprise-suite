from decimal import Decimal

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.db.models import Q

from tenant_portal.decorators import tenant_view
from tenant_portal.views import (
    _finance_assert_open_period,
    _finance_export_csv_url,
    _finance_generate_adjusting_journal_number,
    _finance_validate_journal_payload,
    _parse_finance_filters,
)


@tenant_view(require_module="finance_grants", require_perm="module:finance.view")
def finance_adjusting_journals_view(request: HttpRequest) -> HttpResponse:
    """
    Core Accounting → Journal management → Adjusting Journals
    """

    from tenant_finance.models import ChartAccount, FiscalPeriod, JournalEntry
    from tenant_users.models import TenantUser
    from rbac.models import user_has_permission as _user_has_permission
    from tenant_grants.models import Grant, Donor

    tenant_db = request.tenant_db

    # Common date / grant / donor filters
    f = _parse_finance_filters(request)

    journal_no = (request.GET.get("journal_no") or "").strip()
    status = (request.GET.get("status") or "").strip()
    account_id = (request.GET.get("account_id") or "").strip()
    created_by = (request.GET.get("created_by") or "").strip()
    fiscal_period_id = (request.GET.get("fiscal_period_id") or "").strip()

    entries_qs = (
        JournalEntry.objects.using(tenant_db)
        .prefetch_related("lines", "lines__account", "grant", "created_by", "approved_by")
        .filter(source="manual")
        .order_by("-entry_date", "-id")
    )

    # Date range
    date_start = f["period_start"]
    date_end = f["period_end"]
    if fiscal_period_id:
        period = (
            FiscalPeriod.objects.using(tenant_db)
            .filter(pk=fiscal_period_id)
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

    entries: list[dict] = []
    for entry in entries_qs:
        lines = list(entry.lines.all())
        debit_total = sum((l.debit or Decimal("0")) for l in lines) if lines else Decimal("0")
        credit_total = sum((l.credit or Decimal("0")) for l in lines) if lines else Decimal("0")
        journal_no_display = entry.reference or _finance_generate_adjusting_journal_number(tenant_db, entry.entry_date)
        entries.append(
            {
                "id": entry.id,
                "journal_no": journal_no_display,
                "date": entry.entry_date,
                "reference": entry.reference,
                "memo": entry.memo,
                "grant": entry.grant,
                "status": entry.status,
                "debit_total": debit_total,
                "credit_total": credit_total,
                "created_by": entry.created_by,
                "approved_by": entry.approved_by,
                "posted_at": entry.posted_at,
            }
        )

    grants = Grant.objects.using(tenant_db).filter(status="active").order_by("code")
    donors = Donor.objects.using(tenant_db).order_by("name")
    accounts = ChartAccount.objects.using(tenant_db).filter(is_active=True).order_by("code")
    fiscal_periods = (
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
        request.tenant_user, "finance.add_journalentry", using=tenant_db
    )
    can_manage = _user_has_permission(
        request.tenant_user, "module:finance.manage", using=tenant_db
    )

    if request.GET.get("format") == "csv":
        import csv

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="adjusting_journals.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "Journal No",
                "Date",
                "Reference",
                "Description",
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
                    e["reference"] or "",
                    e["memo"] or "",
                    getattr(e["grant"], "code", ""),
                    e["debit_total"],
                    e["credit_total"],
                    e["status"],
                    getattr(e["created_by"], "full_name", "") or getattr(e["created_by"], "email", ""),
                    getattr(e["approved_by"], "full_name", "") or getattr(
                        e["approved_by"], "email", ""
                    ),
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
                "fiscal_period_id": fiscal_period_id,
            },
            "grants": grants,
            "donors": donors,
            "export_csv_url": _finance_export_csv_url(request),
            "journal_statuses": JournalEntry.Status,
            "accounts": accounts,
            "fiscal_periods": fiscal_periods,
            "created_by_users": created_by_users,
            "can_create_journals": can_create,
            "can_manage_journals": can_manage,
            "active_submenu": "core",
            "active_item": "core_adjusting",
        },
    )

