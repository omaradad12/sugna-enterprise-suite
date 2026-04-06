"""POST handlers for importing finance draft vouchers / journals from Excel."""
from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from rbac.models import user_has_permission
from tenant_portal.views import tenant_view


def _can_import(user, tenant_db: str) -> bool:
    return user_has_permission(user, "finance:journals.create", using=tenant_db) or user_has_permission(
        user, "module:finance.manage", using=tenant_db
    )


def _pay_pv_draft_excel_import_redirect():
    return reverse("tenant_portal:pay_pv_draft_excel_import")


def _recv_receipt_draft_excel_import_redirect():
    return reverse("tenant_portal:recv_receipt_draft_excel_import")


@tenant_view(require_module="finance_grants", require_perm="module:finance.view")
def pay_payment_voucher_draft_excel_import_view(request: HttpRequest) -> HttpResponse:
    from tenant_finance.services.draft_entry_excel_import import import_payment_voucher_drafts_from_excel

    tenant_db = request.tenant_db
    user = request.tenant_user
    if not _can_import(user, tenant_db):
        return HttpResponseForbidden("Forbidden")
    if request.method == "GET":
        return render(
            request,
            "tenant_portal/pay/payment_voucher_draft_excel_import.html",
            {
                "tenant": request.tenant,
                "tenant_user": user,
                "active_submenu": "dashboard",
                "active_item": "dashboard_post_transaction",
            },
        )
    if request.method != "POST":
        return redirect(_pay_pv_draft_excel_import_redirect())
    f = request.FILES.get("draft_excel_file")
    if not f:
        messages.error(request, _("Choose an Excel file to import."))
        return redirect(_pay_pv_draft_excel_import_redirect())
    try:
        res = import_payment_voucher_drafts_from_excel(using=tenant_db, user=user, file_obj=f)
    except RuntimeError as exc:
        messages.error(request, str(exc))
        return redirect(_pay_pv_draft_excel_import_redirect())
    except Exception as exc:
        messages.error(request, _("Import failed: %(err)s") % {"err": exc})
        return redirect(_pay_pv_draft_excel_import_redirect())
    for err in res.get("errors") or []:
        messages.warning(request, err)
    amt_rows = sorted(set(res.get("amount_issue_rows") or []))
    if amt_rows:
        messages.warning(
            request,
            _("Rows with blank or invalid amount in the spreadsheet — correct and re-import: %(rows)s")
            % {"rows": ", ".join(str(r) for r in amt_rows)},
        )
    messages.success(
        request,
        _("Imported %(n)s payment voucher draft(s). Complete lines, then submit for approval before posting to the GL.")
        % {"n": res.get("created", 0)},
    )
    return redirect(reverse("tenant_portal:finance_draft_entry_hub"))


@tenant_view(require_module="finance_grants", require_perm="module:finance.view")
def pay_payment_voucher_draft_excel_template_view(request: HttpRequest) -> HttpResponse:
    from tenant_finance.services.draft_entry_excel_import import excel_template_bytes

    if not _can_import(request.tenant_user, request.tenant_db):
        return HttpResponseForbidden("Forbidden")
    data, name = excel_template_bytes(kind="payment")
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp


@tenant_view(require_module="finance_grants", require_perm="module:finance.view")
def recv_receipt_draft_excel_import_view(request: HttpRequest) -> HttpResponse:
    from tenant_finance.services.draft_entry_excel_import import import_receipt_voucher_drafts_from_excel

    tenant_db = request.tenant_db
    user = request.tenant_user
    if not _can_import(user, tenant_db):
        return HttpResponseForbidden("Forbidden")
    if request.method == "GET":
        return render(
            request,
            "tenant_portal/recv/receipt_voucher_draft_excel_import.html",
            {
                "tenant": request.tenant,
                "tenant_user": user,
                "active_submenu": "dashboard",
                "active_item": "dashboard_post_transaction",
            },
        )
    if request.method != "POST":
        return redirect(_recv_receipt_draft_excel_import_redirect())
    f = request.FILES.get("draft_excel_file")
    if not f:
        messages.error(request, _("Choose an Excel file to import."))
        return redirect(_recv_receipt_draft_excel_import_redirect())
    try:
        res = import_receipt_voucher_drafts_from_excel(using=tenant_db, user=user, file_obj=f)
    except RuntimeError as exc:
        messages.error(request, str(exc))
        return redirect(_recv_receipt_draft_excel_import_redirect())
    except Exception as exc:
        messages.error(request, _("Import failed: %(err)s") % {"err": exc})
        return redirect(_recv_receipt_draft_excel_import_redirect())
    for err in res.get("errors") or []:
        messages.warning(request, err)
    amt_rows = sorted(set(res.get("amount_issue_rows") or []))
    if amt_rows:
        messages.warning(
            request,
            _("Rows with blank or invalid amount in the spreadsheet — correct and re-import: %(rows)s")
            % {"rows": ", ".join(str(r) for r in amt_rows)},
        )
    messages.success(
        request,
        _("Imported %(n)s receipt voucher draft(s). Complete missing fields before submit or post.")
        % {"n": res.get("created", 0)},
    )
    return redirect(reverse("tenant_portal:recv_receipt_entry"))


@tenant_view(require_module="finance_grants", require_perm="module:finance.view")
def recv_receipt_draft_excel_template_view(request: HttpRequest) -> HttpResponse:
    from tenant_finance.services.draft_entry_excel_import import excel_template_bytes

    if not _can_import(request.tenant_user, request.tenant_db):
        return HttpResponseForbidden("Forbidden")
    data, name = excel_template_bytes(kind="receipt")
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp


@tenant_view(require_module="finance_grants", require_perm="finance:journals.view")
def finance_journal_draft_excel_import_view(request: HttpRequest) -> HttpResponse:
    from tenant_finance.services.draft_entry_excel_import import import_manual_journal_drafts_from_excel

    tenant_db = request.tenant_db
    if request.method != "POST":
        return redirect(reverse("tenant_portal:finance_journals"))
    if not _can_import(request.tenant_user, tenant_db):
        return HttpResponseForbidden("Forbidden")
    f = request.FILES.get("draft_excel_file")
    if not f:
        messages.error(request, _("Choose an Excel file to import."))
        return redirect(reverse("tenant_portal:finance_journals"))
    try:
        res = import_manual_journal_drafts_from_excel(using=tenant_db, user=request.tenant_user, file_obj=f)
    except RuntimeError as exc:
        messages.error(request, str(exc))
        return redirect(reverse("tenant_portal:finance_journals"))
    except Exception as exc:
        messages.error(request, _("Import failed: %(err)s") % {"err": exc})
        return redirect(reverse("tenant_portal:finance_journals"))
    for err in res.get("errors") or []:
        messages.warning(request, err)
    messages.success(
        request,
        _("Imported %(n)s manual journal draft(s). Complete lines before submit or post.")
        % {"n": res.get("created", 0)},
    )
    return redirect(reverse("tenant_portal:finance_journals"))


@tenant_view(require_module="finance_grants", require_perm="finance:journals.view")
def finance_journal_draft_excel_template_view(request: HttpRequest) -> HttpResponse:
    from tenant_finance.services.draft_entry_excel_import import excel_template_bytes

    if not _can_import(request.tenant_user, request.tenant_db):
        return HttpResponseForbidden("Forbidden")
    data, name = excel_template_bytes(kind="journal")
    resp = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp
