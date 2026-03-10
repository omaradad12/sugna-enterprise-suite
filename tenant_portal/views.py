from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from tenant_portal.auth import get_tenant_db_for_request, get_tenant_user, tenant_login, tenant_logout
from rbac.models import user_has_permission
from tenant_portal.decorators import tenant_view


def tenant_login_view(request: HttpRequest) -> HttpResponse:
    tenant = getattr(request, "tenant", None)
    tenant_db = get_tenant_db_for_request(request)
    if not tenant:
        return render(request, "tenant_portal/tenant_missing.html", status=404)
    if not tenant_db:
        return render(request, "tenant_portal/tenant_not_provisioned.html", {"tenant": tenant}, status=503)

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        from tenant_users.models import TenantUser

        user = TenantUser.objects.using(tenant_db).filter(email=email, is_active=True).first()
        if user and user.check_password(password):
            tenant_login(request, user.id)
            return redirect(reverse("tenant_portal:home"))
        messages.error(request, "Invalid email or password.")

    return render(request, "tenant_portal/login.html", {"tenant": tenant})


def tenant_logout_view(request: HttpRequest) -> HttpResponse:
    tenant_logout(request)
    return redirect(reverse("tenant_portal:login"))


def tenant_home_view(request: HttpRequest) -> HttpResponse:
    tenant = getattr(request, "tenant", None)
    tenant_db = get_tenant_db_for_request(request)
    if not tenant:
        return render(request, "tenant_portal/tenant_missing.html", status=404)
    if not tenant_db:
        return render(request, "tenant_portal/tenant_not_provisioned.html", {"tenant": tenant}, status=503)

    user = get_tenant_user(request)
    if not user:
        return redirect(reverse("tenant_portal:login"))

    enabled = set(tenant.modules.values_list("code", flat=True))

    modules = [
        {"key": "dashboard", "name": "Dashboard", "perm": "platform:dashboard.view", "icon": "bar-chart-2", "requires": None},
        {"key": "finance", "name": "Finance", "perm": "module:finance.view", "icon": "dollar-sign", "requires": "finance"},
        {"key": "grants", "name": "Grant Management", "perm": "module:grants.view", "icon": "clipboard", "requires": "grants"},
        {"key": "integrations", "name": "Integrations", "perm": "module:integrations.manage", "icon": "link", "requires": "integrations"},
        {"key": "users", "name": "Users", "perm": "users:manage", "icon": "users", "requires": None},
        {"key": "rbac", "name": "Roles & Permissions", "perm": "rbac:roles.manage", "icon": "shield", "requires": None},
        {"key": "modules", "name": "Modules", "perm": "module:modules.manage", "icon": "grid", "requires": None},
    ]

    def _is_visible(m):
        if m["requires"] and m["requires"] not in enabled:
            return False
        return user_has_permission(user, m["perm"], using=tenant_db)

    visible_modules = [m for m in modules if _is_visible(m)]

    return render(
        request,
        "tenant_portal/home.html",
        {"tenant": tenant, "tenant_user": user, "modules": visible_modules},
    )


@tenant_view(require_module="finance", require_perm="module:finance.view")
def finance_home_view(request: HttpRequest) -> HttpResponse:
    from tenant_finance.models import ChartAccount, JournalEntry

    tenant_db = request.tenant_db
    context = {
        "tenant": request.tenant,
        "tenant_user": request.tenant_user,
        "accounts_count": ChartAccount.objects.using(tenant_db).count(),
        "journals_count": JournalEntry.objects.using(tenant_db).count(),
    }
    return render(request, "tenant_portal/finance/home.html", context)


@tenant_view(require_module="finance", require_perm="module:finance.manage")
def finance_accounts_view(request: HttpRequest) -> HttpResponse:
    from tenant_finance.models import ChartAccount

    tenant_db = request.tenant_db
    if request.method == "POST":
        code = (request.POST.get("code") or "").strip()
        name = (request.POST.get("name") or "").strip()
        type_ = (request.POST.get("type") or "").strip()
        if not code or not name or not type_:
            messages.error(request, "Please provide code, name, and type.")
        else:
            ChartAccount.objects.using(tenant_db).create(code=code, name=name, type=type_, is_active=True)
            messages.success(request, "Account created.")
            return redirect(reverse("tenant_portal:finance_accounts"))

    accounts = ChartAccount.objects.using(tenant_db).order_by("code")
    return render(
        request,
        "tenant_portal/finance/accounts.html",
        {"tenant": request.tenant, "tenant_user": request.tenant_user, "accounts": accounts, "types": ChartAccount.Type},
    )


@tenant_view(require_module="finance", require_perm="module:finance.manage")
def finance_journals_view(request: HttpRequest) -> HttpResponse:
    from tenant_finance.models import ChartAccount, JournalEntry, JournalLine
    from django.utils.dateparse import parse_date
    from decimal import Decimal, InvalidOperation
    from django.db.models import Sum

    tenant_db = request.tenant_db
    if request.method == "POST":
        entry_date = parse_date(request.POST.get("entry_date") or "")
        memo = (request.POST.get("memo") or "").strip()
        grant_id = request.POST.get("grant_id")
        account_id = request.POST.get("account_id")
        debit = request.POST.get("debit") or "0"
        credit = request.POST.get("credit") or "0"
        if not entry_date or not account_id:
            messages.error(request, "Please provide entry date and account.")
        else:
            from tenant_grants.models import Grant

            grant = None
            if grant_id:
                grant = Grant.objects.using(tenant_db).filter(pk=grant_id).first()

            account = ChartAccount.objects.using(tenant_db).filter(pk=account_id).first()
            try:
                debit_val = Decimal(str(debit or "0") or "0")
                credit_val = Decimal(str(credit or "0") or "0")
            except (InvalidOperation, ValueError):
                messages.error(request, "Invalid debit/credit amount.")
                debit_val = None
                credit_val = None

            if debit_val is not None and credit_val is not None:
                # Budget control: prevent overspend when linking expense debit to a grant.
                if grant and account and account.type == "expense" and debit_val > 0:
                    budget_total = (
                        grant.budget_lines.using(tenant_db).aggregate(total=Sum("amount")).get("total") or Decimal("0")
                    )
                    spent_to_date = (
                        JournalLine.objects.using(tenant_db)
                        .filter(entry__grant_id=grant.id, account__type="expense")
                        .aggregate(total=Sum("debit"))
                        .get("total")
                        or Decimal("0")
                    )

                    # Use the stricter of: award amount (hard ceiling) and budget total (if configured).
                    award_ceiling = Decimal(str(grant.award_amount or 0))
                    budget_ceiling = Decimal(str(budget_total))
                    ceiling = award_ceiling
                    if budget_ceiling > 0 and budget_ceiling < ceiling:
                        ceiling = budget_ceiling

                    projected = spent_to_date + debit_val
                    can_override = user_has_permission(request.tenant_user, "module:finance.override_budget", using=tenant_db)
                    if ceiling > 0 and projected > ceiling and not can_override:
                        messages.error(
                            request,
                            f"Overspend blocked: projected spend {projected} exceeds allowed ceiling {ceiling} for grant {grant.code}.",
                        )
                        return redirect(reverse("tenant_portal:finance_journals"))

                entry = JournalEntry.objects.using(tenant_db).create(entry_date=entry_date, memo=memo, grant=grant)
                JournalLine.objects.using(tenant_db).create(entry=entry, account=account, debit=debit_val, credit=credit_val)
                messages.success(request, "Journal entry created.")
                return redirect(reverse("tenant_portal:finance_journals"))

    entries = JournalEntry.objects.using(tenant_db).prefetch_related("lines").order_by("-entry_date", "-id")[:50]
    accounts = ChartAccount.objects.using(tenant_db).filter(is_active=True).order_by("code")
    from tenant_grants.models import Grant

    grants = Grant.objects.using(tenant_db).order_by("-created_at")[:50]
    return render(
        request,
        "tenant_portal/finance/journals.html",
        {"tenant": request.tenant, "tenant_user": request.tenant_user, "entries": entries, "accounts": accounts, "grants": grants},
    )


@tenant_view(require_module="grants", require_perm="module:grants.view")
def grants_home_view(request: HttpRequest) -> HttpResponse:
    from tenant_grants.models import Donor, Grant

    tenant_db = request.tenant_db
    return render(
        request,
        "tenant_portal/grants/home.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "donors_count": Donor.objects.using(tenant_db).count(),
            "grants_count": Grant.objects.using(tenant_db).count(),
        },
    )


@tenant_view(require_module="grants", require_perm="module:grants.manage")
def grants_donors_view(request: HttpRequest) -> HttpResponse:
    from tenant_grants.models import Donor

    tenant_db = request.tenant_db
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        if not name:
            messages.error(request, "Donor name is required.")
        else:
            Donor.objects.using(tenant_db).create(name=name, email=email)
            messages.success(request, "Donor created.")
            return redirect(reverse("tenant_portal:grants_donors"))

    donors = Donor.objects.using(tenant_db).order_by("name")
    return render(
        request,
        "tenant_portal/grants/donors.html",
        {"tenant": request.tenant, "tenant_user": request.tenant_user, "donors": donors},
    )


@tenant_view(require_module="grants", require_perm="module:grants.manage")
def grants_grants_view(request: HttpRequest) -> HttpResponse:
    from tenant_grants.models import Donor, Grant
    from django.utils.dateparse import parse_date

    tenant_db = request.tenant_db
    if request.method == "POST":
        code = (request.POST.get("code") or "").strip()
        title = (request.POST.get("title") or "").strip()
        donor_id = request.POST.get("donor_id")
        award_amount = request.POST.get("award_amount") or "0"
        start_date = parse_date(request.POST.get("start_date") or "")
        end_date = parse_date(request.POST.get("end_date") or "")
        if not code or not title or not donor_id:
            messages.error(request, "Please provide code, title, and donor.")
        else:
            donor = Donor.objects.using(tenant_db).filter(pk=donor_id).first()
            Grant.objects.using(tenant_db).create(
                code=code,
                title=title,
                donor=donor,
                status=Grant.Status.ACTIVE,
                award_amount=award_amount or 0,
                start_date=start_date,
                end_date=end_date,
            )
            messages.success(request, "Grant created.")
            return redirect(reverse("tenant_portal:grants_grants"))

    grants = Grant.objects.using(tenant_db).select_related("donor").order_by("-created_at")[:50]
    donors = Donor.objects.using(tenant_db).order_by("name")
    return render(
        request,
        "tenant_portal/grants/grants.html",
        {"tenant": request.tenant, "tenant_user": request.tenant_user, "grants": grants, "donors": donors},
    )


@tenant_view(require_module="grants", require_perm="module:grants.manage")
def grants_budgets_view(request: HttpRequest) -> HttpResponse:
    from tenant_grants.models import Grant, BudgetLine

    tenant_db = request.tenant_db
    if request.method == "POST":
        grant_id = request.POST.get("grant_id")
        category = (request.POST.get("category") or "").strip()
        amount = request.POST.get("amount") or "0"
        notes = (request.POST.get("notes") or "").strip()
        if not grant_id or not category:
            messages.error(request, "Please select a grant and provide a category.")
        else:
            grant = Grant.objects.using(tenant_db).filter(pk=grant_id).first()
            BudgetLine.objects.using(tenant_db).create(grant=grant, category=category, amount=amount or 0, notes=notes)
            messages.success(request, "Budget line created.")
            return redirect(reverse("tenant_portal:grants_budgets"))

    grants = Grant.objects.using(tenant_db).order_by("-created_at")[:100]
    budget_lines = BudgetLine.objects.using(tenant_db).select_related("grant").order_by("-id")[:200]
    return render(
        request,
        "tenant_portal/grants/budgets.html",
        {"tenant": request.tenant, "tenant_user": request.tenant_user, "grants": grants, "budget_lines": budget_lines},
    )


@tenant_view(require_module="grants", require_perm="module:grants.view")
def grants_approvals_view(request: HttpRequest) -> HttpResponse:
    from django.utils import timezone
    from tenant_grants.models import Grant, GrantApproval

    tenant_db = request.tenant_db
    user = request.tenant_user

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "request":
            grant_id = request.POST.get("grant_id")
            note = (request.POST.get("note") or "").strip()
            grant = Grant.objects.using(tenant_db).filter(pk=grant_id).first()
            if not grant:
                messages.error(request, "Invalid grant.")
            else:
                GrantApproval.objects.using(tenant_db).create(grant=grant, requested_by=user, note=note)
                messages.success(request, "Approval requested.")
                return redirect(reverse("tenant_portal:grants_approvals"))

        if action in {"approve", "reject"}:
            if not user_has_permission(user, "module:grants.approve", using=tenant_db):
                return render(
                    request,
                    "tenant_portal/forbidden.html",
                    {"tenant": request.tenant, "tenant_user": user, "reason": "You do not have approval permission."},
                    status=403,
                )
            approval_id = request.POST.get("approval_id")
            approval = GrantApproval.objects.using(tenant_db).select_related("grant").filter(pk=approval_id).first()
            if not approval:
                messages.error(request, "Invalid approval request.")
            else:
                approval.status = GrantApproval.Status.APPROVED if action == "approve" else GrantApproval.Status.REJECTED
                approval.decided_by = user
                approval.decided_at = timezone.now()
                approval.save(using=tenant_db)
                messages.success(request, f"Request {approval.status}.")
                return redirect(reverse("tenant_portal:grants_approvals"))

    approvals = GrantApproval.objects.using(tenant_db).select_related("grant", "requested_by", "decided_by").order_by("-created_at")[:100]
    grants = Grant.objects.using(tenant_db).order_by("-created_at")[:100]
    can_decide = user_has_permission(user, "module:grants.approve", using=tenant_db)
    return render(
        request,
        "tenant_portal/grants/approvals.html",
        {
            "tenant": request.tenant,
            "tenant_user": user,
            "approvals": approvals,
            "grants": grants,
            "can_decide": can_decide,
        },
    )


@tenant_view(require_module="grants", require_perm="module:grants.view")
def grants_reports_view(request: HttpRequest) -> HttpResponse:
    from django.db.models import Sum
    from tenant_grants.models import Grant, BudgetLine
    from tenant_finance.models import JournalLine, JournalEntry

    tenant_db = request.tenant_db

    start = request.GET.get("start") or ""
    end = request.GET.get("end") or ""

    grants = list(Grant.objects.using(tenant_db).select_related("donor").order_by("-created_at")[:200])
    budget_by_grant = {
        row["grant_id"]: row["total"] or 0
        for row in BudgetLine.objects.using(tenant_db).values("grant_id").annotate(total=Sum("amount"))
    }

    entry_filter = {"entry__grant_id__isnull": False, "account__type": "expense"}
    if start:
        entry_filter["entry__entry_date__gte"] = start
    if end:
        entry_filter["entry__entry_date__lte"] = end

    spend_by_grant = {
        row["entry__grant_id"]: row["spent"] or 0
        for row in JournalLine.objects.using(tenant_db).filter(**entry_filter).values("entry__grant_id").annotate(spent=Sum("debit"))
    }

    # Breakdown: spend by expense account (across all grants in range)
    spend_by_account = list(
        JournalLine.objects.using(tenant_db)
        .filter(**entry_filter)
        .values("account__code", "account__name")
        .annotate(spent=Sum("debit"))
        .order_by("-spent")[:20]
    )

    # Breakdown: budget by category (across all grants)
    budget_by_category = list(
        BudgetLine.objects.using(tenant_db).values("category").annotate(total=Sum("amount")).order_by("-total")[:20]
    )

    rows = []
    for g in grants:
        budget = budget_by_grant.get(g.id, 0)
        spent = spend_by_grant.get(g.id, 0)
        remaining = (g.award_amount or 0) - spent
        rows.append(
            {
                "grant": g,
                "budget": budget,
                "spent": spent,
                "remaining": remaining,
            }
        )

    return render(
        request,
        "tenant_portal/grants/reports.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "rows": rows,
            "start": start,
            "end": end,
            "spend_by_account": spend_by_account,
            "budget_by_category": budget_by_category,
        },
    )


@tenant_view(require_module="integrations", require_perm="module:integrations.manage")
def integrations_home_view(request: HttpRequest) -> HttpResponse:
    from tenant_integrations.models import OutboundWebhook, ErpConnection

    tenant_db = request.tenant_db
    return render(
        request,
        "tenant_portal/integrations/home.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "webhooks_count": OutboundWebhook.objects.using(tenant_db).count(),
            "erp_count": ErpConnection.objects.using(tenant_db).count(),
        },
    )


@tenant_view(require_module="integrations", require_perm="module:integrations.manage")
def integrations_webhooks_view(request: HttpRequest) -> HttpResponse:
    from tenant_integrations.models import OutboundWebhook

    tenant_db = request.tenant_db
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        url = (request.POST.get("url") or "").strip()
        secret = (request.POST.get("secret") or "").strip()
        if not name or not url:
            messages.error(request, "Name and URL are required.")
        else:
            wh = OutboundWebhook.objects.using(tenant_db).create(name=name, url=url, is_active=True)
            if secret:
                wh.set_secret(secret)
                wh.save(using=tenant_db)
            messages.success(request, "Webhook created.")
            return redirect(reverse("tenant_portal:integrations_webhooks"))

    webhooks = OutboundWebhook.objects.using(tenant_db).order_by("-created_at")[:100]
    return render(
        request,
        "tenant_portal/integrations/webhooks.html",
        {"tenant": request.tenant, "tenant_user": request.tenant_user, "webhooks": webhooks},
    )


@tenant_view(require_module="integrations", require_perm="module:integrations.manage")
def integrations_erp_view(request: HttpRequest) -> HttpResponse:
    from tenant_integrations.models import ErpConnection

    tenant_db = request.tenant_db
    if request.method == "POST":
        provider = (request.POST.get("provider") or "").strip() or ErpConnection.Provider.GENERIC
        name = (request.POST.get("name") or "").strip()
        base_url = (request.POST.get("base_url") or "").strip()
        api_key = (request.POST.get("api_key") or "").strip()
        if not name:
            messages.error(request, "Connection name is required.")
        else:
            conn = ErpConnection.objects.using(tenant_db).create(provider=provider, name=name, base_url=base_url, is_active=True)
            if api_key:
                conn.set_api_key(api_key)
                conn.save(using=tenant_db)
            messages.success(request, "ERP connection created.")
            return redirect(reverse("tenant_portal:integrations_erp"))

    conns = ErpConnection.objects.using(tenant_db).order_by("-created_at")[:100]
    return render(
        request,
        "tenant_portal/integrations/erp.html",
        {"tenant": request.tenant, "tenant_user": request.tenant_user, "conns": conns, "providers": ErpConnection.Provider},
    )
