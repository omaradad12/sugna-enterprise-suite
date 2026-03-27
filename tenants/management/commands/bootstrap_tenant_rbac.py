from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant


class Command(BaseCommand):
    help = "Create initial tenant admin user + baseline RBAC records in the tenant database."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant slug or ID.")
        parser.add_argument("--email", required=True, help="Tenant admin email.")
        parser.add_argument("--password", required=True, help="Tenant admin password.")
        parser.add_argument("--full-name", default="Tenant Admin", help="Tenant admin full name.")

    def handle(self, *args, **options):
        tenant_arg = options["tenant"]
        tenant = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(pk=tenant_arg).first()
        if not tenant:
            raise CommandError("Tenant not found. Use --tenant <slug|id>.")
        if not tenant.db_name:
            raise CommandError("Tenant has no db_name configured. Run provision_tenant_db first.")

        ensure_tenant_db_configured(tenant)
        alias = tenant_db_alias(tenant)
        self.stdout.write(f"Using tenant DB alias '{alias}' for slug '{tenant.slug}'.")

        from tenant_users.models import TenantUser
        from rbac.models import Permission, Role, RolePermission, UserRole

        # Baseline permissions (extend as modules mature)
        baseline = [
            ("platform:dashboard.view", "View dashboards"),
            ("platform:tenants.read", "Read tenant records"),
            ("platform:tenants.manage", "Manage tenant settings"),
            ("module:modules.manage", "Manage module entitlements"),
            ("rbac:roles.manage", "Manage roles and permissions"),
            ("users:manage", "Manage users"),
            # Data-level scope
            ("finance:scope.all_grants", "Access all grants/projects (otherwise restricted to assignments)"),
            ("finance:scope.all_cost_centers", "Access all cost centers (otherwise restricted)"),
            ("finance:scope.all_projects", "Access all projects (otherwise restricted to assignments)"),
            # Finance reporting
            ("finance:reporting.view", "View finance reports"),
            ("finance:reporting.export", "Export finance reports (CSV/XLSX/PDF)"),
            ("finance:reporting.advanced", "Advanced finance reporting (restricted)"),
            # Finance
            ("module:finance.view", "View finance dashboards and reports"),
            ("module:finance.manage", "Manage finance setup and entries"),
            ("module:finance.override_budget", "Override budget/award spend controls for grant-linked postings"),
            # Finance journals (granular actions)
            ("finance:journals.view", "View journals and vouchers"),
            ("finance:journals.create", "Create draft journals and vouchers"),
            ("finance:journals.edit", "Edit draft or pending journals"),
            ("finance:journals.delete", "Delete draft journals"),
            ("finance:journals.approve", "Approve journals (maker-checker enforced)"),
            ("finance:journals.post", "Post approved journals (maker-checker enforced)"),
            ("finance:journals.reverse", "Reverse posted journals (as per reversal policy)"),
            ("finance:journals.adjusting", "Create and manage adjusting journals (NGO standards)"),
            ("finance:journals.override_maker_checker", "Override maker-checker segregation (restricted)"),
            # Vouchers + payments
            ("finance:vouchers.view", "View vouchers (payment/receipt)"),
            ("finance:vouchers.create", "Create vouchers"),
            ("finance:vouchers.edit", "Edit vouchers (draft/pending)"),
            ("finance:vouchers.delete", "Delete draft vouchers"),
            ("finance:vouchers.approve", "Approve vouchers (maker-checker enforced)"),
            ("finance:vouchers.post", "Post vouchers (maker-checker enforced)"),
            ("finance:vouchers.reverse", "Reverse posted vouchers"),
            ("finance:payments.view", "View payments and disbursements"),
            ("finance:payments.create", "Create payments/disbursements"),
            ("finance:payments.approve", "Approve payments (maker-checker enforced)"),
            ("finance:payments.post", "Post/confirm payments"),
            ("finance:payments.reverse", "Reverse/cancel payments"),
            # Budget control
            ("finance:budget.view", "View budget controls and budget events"),
            ("finance:budget.control", "Manage budget control rules"),
            ("finance:budget.approve", "Approve budget overrides/exception requests"),
            ("finance:budget.override", "Override budget blocks (restricted)"),
            # Bank & cash + reconciliation
            ("finance:bankcash.view", "View bank and cash accounts"),
            ("finance:bankcash.manage", "Manage bank and cash accounts"),
            ("finance:reconciliation.view", "View reconciliations"),
            ("finance:reconciliation.manage", "Manage bank reconciliations"),
            ("finance:reconciliation.post", "Post/close bank reconciliations"),
            # Audit
            ("finance:audit.view", "View finance audit trail"),
            ("finance:audit.manage", "Manage audit settings and retention"),
            # Accounting periods
            ("finance:periods.view", "View accounting periods"),
            ("finance:periods.open", "Open accounting periods"),
            ("finance:periods.close", "Close accounting periods (soft/hard)"),
            ("finance:periods.reopen", "Reopen closed accounting periods"),

            # Controls & compliance (posting/locking/audit)
            ("finance:posting.backdated", "Allow backdated posting (restricted)"),
            ("finance:posting.edit_after_post", "Allow edit-after-post (restricted)"),
            ("finance:locking.lock", "Lock transactions to prevent further changes"),
            ("finance:locking.unlock", "Unlock locked transactions (restricted)"),
            ("finance:maker_checker.override", "Override maker-checker segregation (restricted)"),

            # Transaction actions (separate semantics)
            ("finance:transactions.void", "Void transactions"),
            ("finance:transactions.cancel", "Cancel transactions"),
            ("finance:transactions.reverse", "Reverse transactions"),

            # Document attachments
            ("finance:attachments.view", "View document attachments"),
            ("finance:attachments.upload", "Upload document attachments"),
            ("finance:attachments.delete", "Delete document attachments"),
            # Document Management (central repository)
            ("documents:workspace.view", "View Document Management workspace"),
            ("documents:document.upload", "Upload documents from Document Management"),
            ("documents:document.manage", "Manage document categories and storage settings"),

            # Dashboards, notifications, alerts
            ("dashboard:view", "View dashboards"),
            ("notifications:view", "View notifications"),
            ("notifications:manage", "Manage notification settings"),
            ("alerts:view", "View system alerts"),
            ("alerts:manage", "Manage alert rules and thresholds"),

            # Bulk operations
            ("finance:bulk.post", "Bulk post transactions (restricted)"),
            ("finance:bulk.approve", "Bulk approve transactions (restricted)"),
            ("finance:bulk.import", "Bulk import transactions (restricted)"),

            # API & integrations
            ("api:access", "Access API features (restricted)"),
            ("integrations:manage", "Manage integrations and connections"),
            ("integrations:webhooks.manage", "Manage webhooks"),

            # Read-only auditor mode (cross-module)
            ("auditor:readonly", "Read-only auditor mode (view across modules; no create/edit/post)"),

            # -----------------------------
            # Major system modules (by area)
            # -----------------------------
            ("module:main_cashbook.view", "View Main Cashbook"),
            ("module:main_cashbook.manage", "Manage Main Cashbook"),
            ("module:cash_bank.view", "View Cash & Bank"),
            ("module:cash_bank.manage", "Manage Cash & Bank"),
            ("module:core_accounting.view", "View Core Accounting"),
            ("module:core_accounting.manage", "Manage Core Accounting"),
            ("module:funds_donors.view", "View Funds & Donors"),
            ("module:funds_donors.manage", "Manage Funds & Donors"),
            ("module:budgeting.view", "View Budgeting"),
            ("module:budgeting.manage", "Manage Budgeting"),
            ("module:incoming_fund.view", "View Receivables"),
            ("module:incoming_fund.manage", "Manage Receivables"),
            ("module:outgoing_fund.view", "View Payables"),
            ("module:outgoing_fund.manage", "Manage Payables"),
            ("module:multi_donor_sharing.view", "View Cost Allocation"),
            ("module:multi_donor_sharing.manage", "Manage Cost Allocation"),
            ("module:governance.view", "View Internal Control"),
            ("module:governance.manage", "Manage Internal Control"),
            ("module:reporting.view", "View Reports"),
            ("module:reporting.manage", "Manage Reports configuration"),
            ("module:financial_setup.view", "View Financial Setup"),
            ("module:financial_setup.manage", "Administer Financial Setup"),

            # -------------------------------------------------------
            # Transactional module permissions (granular by action)
            # Use these for segregation of duties (maker-checker).
            # -------------------------------------------------------
            # Main Cashbook
            ("cashbook:entries.view", "View cashbook entries"),
            ("cashbook:entries.create", "Create cashbook entries"),
            ("cashbook:entries.edit", "Edit draft/pending cashbook entries"),
            ("cashbook:entries.delete", "Delete draft cashbook entries"),
            ("cashbook:entries.approve", "Approve cashbook entries (maker-checker enforced)"),
            ("cashbook:entries.post", "Post cashbook entries (maker-checker enforced)"),
            ("cashbook:entries.reverse", "Reverse posted cashbook entries"),

            # Cash & Bank (bank/cash management + petty cash)
            ("cashbank:accounts.view", "View bank and cash accounts"),
            ("cashbank:accounts.manage", "Manage bank and cash accounts"),
            ("cashbank:petty_cash.view", "View petty cash"),
            ("cashbank:petty_cash.create", "Create petty cash vouchers"),
            ("cashbank:petty_cash.approve", "Approve petty cash vouchers"),
            ("cashbank:petty_cash.post", "Post petty cash vouchers"),
            ("cashbank:petty_cash.reverse", "Reverse petty cash vouchers"),

            # Bank Reconciliation
            ("cashbank:reconciliation.view", "View bank reconciliations"),
            ("cashbank:reconciliation.create", "Create bank reconciliations"),
            ("cashbank:reconciliation.edit", "Edit draft bank reconciliations"),
            ("cashbank:reconciliation.approve", "Approve bank reconciliations"),
            ("cashbank:reconciliation.post", "Post/close bank reconciliations"),
            ("cashbank:reconciliation.reverse", "Reverse/rollback reconciliations"),

            # Core Accounting (journals)
            ("core_accounting:journals.view", "View journal entries"),
            ("core_accounting:journals.create", "Create journal entries"),
            ("core_accounting:journals.edit", "Edit draft/pending journal entries"),
            ("core_accounting:journals.delete", "Delete draft journal entries"),
            ("core_accounting:journals.approve", "Approve journal entries (maker-checker enforced)"),
            ("core_accounting:journals.post", "Post journal entries (maker-checker enforced)"),
            ("core_accounting:journals.reverse", "Reverse posted journal entries"),

            # Receipts (Receivables)
            ("incoming_fund:receipts.view", "View receipts"),
            ("incoming_fund:receipts.create", "Create receipts"),
            ("incoming_fund:receipts.edit", "Edit draft/pending receipts"),
            ("incoming_fund:receipts.delete", "Delete draft receipts"),
            ("incoming_fund:receipts.approve", "Approve receipts (maker-checker enforced)"),
            ("incoming_fund:receipts.post", "Post receipts (maker-checker enforced)"),
            ("incoming_fund:receipts.reverse", "Reverse posted receipts"),

            # Payments (Payables)
            ("outgoing_fund:payments.view", "View payments"),
            ("outgoing_fund:payments.create", "Create payments"),
            ("outgoing_fund:payments.edit", "Edit draft/pending payments"),
            ("outgoing_fund:payments.delete", "Delete draft payments"),
            ("outgoing_fund:payments.approve", "Approve payments (maker-checker enforced)"),
            ("outgoing_fund:payments.post", "Post/confirm payments (maker-checker enforced)"),
            ("outgoing_fund:payments.reverse", "Reverse/cancel payments"),

            # Funds & Donors (master + donor compliance)
            ("funds_donors:donors.view", "View donors"),
            ("funds_donors:donors.manage", "Manage donors"),
            ("funds_donors:funds.view", "View funds"),
            ("funds_donors:funds.manage", "Manage funds"),
            ("funds_donors:compliance.view", "View donor compliance rules"),
            ("funds_donors:compliance.manage", "Manage donor compliance rules"),

            # Budgeting + budget control
            ("budgeting:budgets.view", "View budgets"),
            ("budgeting:budgets.create", "Create budgets"),
            ("budgeting:budgets.edit", "Edit budgets"),
            ("budgeting:budgets.approve", "Approve budgets (maker-checker enforced)"),
            ("budgeting:budgets.post", "Activate/finalize budgets"),
            ("budgeting:budget_control.view", "View budget control results/events"),
            ("budgeting:budget_control.manage", "Manage budget control rules"),
            ("budgeting:budget_override.approve", "Approve budget override requests"),
            ("budgeting:budget_override.override", "Override budget blocks (restricted)"),

            # Cost allocation (shared funding)
            ("cost_sharing:allocations.view", "View cost allocations"),
            ("cost_sharing:allocations.create", "Create cost allocations"),
            ("cost_sharing:allocations.edit", "Edit draft/pending allocations"),
            ("cost_sharing:allocations.approve", "Approve allocations (maker-checker enforced)"),
            ("cost_sharing:allocations.post", "Post allocations (maker-checker enforced)"),
            ("cost_sharing:allocations.reverse", "Reverse posted allocations"),

            # Internal control (approval workflows & policies)
            ("governance:workflows.view", "View approval workflows"),
            ("governance:workflows.manage", "Manage approval workflows"),
            ("governance:controls.view", "View controls and policies"),
            ("governance:controls.manage", "Manage controls and policies"),

            # Reports
            ("reporting:view", "View report catalog"),
            ("reporting:export", "Export from reports"),
            ("reporting:advanced", "Advanced reports"),

            # Financial setup administration
            ("setup:view", "View setup pages"),
            ("setup:manage", "Manage setup configuration"),
            ("setup:numbering.manage", "Manage document series / numbering"),
            ("setup:posting_rules.manage", "Manage posting rules"),
            ("setup:periods.manage", "Manage accounting periods configuration"),
            ("setup:audit.manage", "Manage audit trail settings"),
            # Grant Management
            ("module:grants.view", "View grants and budgets"),
            ("module:grants.manage", "Manage grants, budgets, and workflows"),
            ("module:grants.approve", "Approve or reject grants"),
            ("module:grants.pr_line_manager_approve", "Approve, reject, or return PRs (Line Manager)"),
            ("module:grants.pr_procurement_process", "Process PRs after line manager approval (Procurement Officer)"),
            (
                "grants:donor_restrictions.manage",
                "Create, edit, and deactivate donor conditions & restrictions (compliance)",
            ),
            # Integrations
            ("module:integrations.manage", "Manage integrations (webhooks and ERP connections)"),
            # Audit & Risk: full findings and results (Admin + Finance Manager only)
            ("module:audit_risk.view_audit_results", "View audit findings and audit results (restricted)"),
        ]

        perms = {}
        for code, name in baseline:
            p, _ = Permission.objects.using(alias).get_or_create(code=code, defaults={"name": name})
            perms[code] = p

        admin_role, _ = Role.objects.using(alias).get_or_create(
            name="Tenant Admin",
            defaults={"description": "Full access inside tenant.", "is_system": True, "role_type": Role.RoleType.ADMIN},
        )
        if not admin_role.is_system:
            admin_role.is_system = True
            admin_role.save(using=alias, update_fields=["is_system"])
        if getattr(admin_role, "role_type", "") != Role.RoleType.ADMIN:
            admin_role.role_type = Role.RoleType.ADMIN
            admin_role.save(using=alias, update_fields=["role_type"])
        for p in perms.values():
            # Use *_id to avoid cross-DB relation checks by routers.
            RolePermission.objects.using(alias).get_or_create(role_id=admin_role.id, permission_id=p.id)

        # Finance Manager: finance + audit results + user management inside the organization
        finance_manager_role, _ = Role.objects.using(alias).get_or_create(
            name="Finance Manager",
            defaults={
                "description": "Finance and grant access; can view audit findings and audit results.",
                "role_type": Role.RoleType.FINANCIAL,
            },
        )
        if getattr(finance_manager_role, "role_type", "") != Role.RoleType.FINANCIAL:
            finance_manager_role.role_type = Role.RoleType.FINANCIAL
            finance_manager_role.save(using=alias, update_fields=["role_type"])
        for code in (
            "module:finance.view",
            "module:finance.manage",
            "finance:scope.all_grants",
            "finance:scope.all_cost_centers",
            "finance:reporting.view",
            "finance:reporting.export",
            "finance:journals.view",
            "finance:journals.create",
            "finance:journals.edit",
            "finance:journals.delete",
            "finance:journals.approve",
            "finance:journals.post",
            "finance:journals.reverse",
            "finance:journals.adjusting",
            "finance:vouchers.view",
            "finance:vouchers.create",
            "finance:vouchers.edit",
            "finance:vouchers.delete",
            "finance:vouchers.approve",
            "finance:vouchers.post",
            "finance:vouchers.reverse",
            "finance:payments.view",
            "finance:payments.create",
            "finance:payments.approve",
            "finance:payments.post",
            "finance:payments.reverse",
            "finance:budget.view",
            "finance:budget.control",
            "finance:budget.approve",
            "finance:budget.override",
            "finance:bankcash.view",
            "finance:bankcash.manage",
            "finance:reconciliation.view",
            "finance:reconciliation.manage",
            "finance:reconciliation.post",
            "finance:audit.view",
            "finance:periods.view",
            "finance:periods.close",
            "finance:periods.reopen",
            # Controls & compliance
            "finance:posting.backdated",
            "finance:posting.edit_after_post",
            "finance:locking.lock",
            "finance:locking.unlock",
            "finance:maker_checker.override",
            # Transaction actions
            "finance:transactions.void",
            "finance:transactions.cancel",
            "finance:transactions.reverse",
            # Attachments
            "finance:attachments.view",
            "finance:attachments.upload",
            "finance:attachments.delete",
            # Document Management
            "documents:workspace.view",
            "documents:document.upload",
            "documents:document.manage",
            # Dashboards/notifications/alerts
            "dashboard:view",
            "notifications:view",
            "alerts:view",
            # Bulk operations
            "finance:bulk.post",
            "finance:bulk.approve",
            "finance:bulk.import",
            # API & integrations
            "api:access",
            "integrations:manage",
            "integrations:webhooks.manage",
            # Auditor mode
            "auditor:readonly",
            "module:grants.view",
            "module:grants.manage",
            "module:audit_risk.view_audit_results",
            "users:manage",
            "rbac:roles.manage",
        ):
            if code in perms:
                RolePermission.objects.using(alias).get_or_create(
                    role_id=finance_manager_role.id,
                    permission_id=perms[code].id,
                )

        accountant_role, _ = Role.objects.using(alias).get_or_create(
            name="Accountant",
            defaults={
                "description": "Accountant: journals and NGO adjusting entries (submit for approval; no approve/post).",
                "role_type": Role.RoleType.FINANCIAL,
            },
        )
        if getattr(accountant_role, "role_type", "") != Role.RoleType.FINANCIAL:
            accountant_role.role_type = Role.RoleType.FINANCIAL
            accountant_role.save(using=alias, update_fields=["role_type"])
        for code in (
            "module:finance.view",
            "finance:journals.view",
            "finance:journals.create",
            "finance:journals.edit",
            "finance:journals.delete",
            "finance:journals.adjusting",
            "finance:periods.view",
            "finance:reporting.view",
            "finance:reporting.export",
            "finance:attachments.view",
            "finance:attachments.upload",
            "documents:workspace.view",
            "documents:document.upload",
            "dashboard:view",
        ):
            if code in perms:
                RolePermission.objects.using(alias).get_or_create(
                    role_id=accountant_role.id,
                    permission_id=perms[code].id,
                )

        user, created = TenantUser.objects.using(alias).get_or_create(
            email=options["email"].lower().strip(),
            defaults={"full_name": options["full_name"], "is_active": True, "is_tenant_admin": True},
        )
        if created or not user.password_hash:
            user.set_password(options["password"])
            user.full_name = options["full_name"]
            user.is_active = True
            user.is_tenant_admin = True
            user.save(using=alias)

        UserRole.objects.using(alias).get_or_create(user_id=user.id, role_id=admin_role.id)

        risk_compliance_role, _ = Role.objects.using(alias).get_or_create(
            name="Risk & Compliance Manager",
            defaults={
                "description": "Donor restrictions, compliance rules, and policy enforcement setup.",
                "role_type": Role.RoleType.FINANCIAL,
            },
        )
        for code in (
            "module:grants.view",
            "grants:donor_restrictions.manage",
            "module:audit_risk.view_audit_results",
            "dashboard:view",
        ):
            if code in perms:
                RolePermission.objects.using(alias).get_or_create(
                    role_id=risk_compliance_role.id,
                    permission_id=perms[code].id,
                )

        self.stdout.write(self.style.SUCCESS(f"Bootstrapped RBAC + tenant admin '{user.email}' in DB '{alias}'."))  # noqa: T201

