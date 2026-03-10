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
            # Finance
            ("module:finance.view", "View finance dashboards and reports"),
            ("module:finance.manage", "Manage finance setup and entries"),
            ("module:finance.override_budget", "Override budget/award spend controls for grant-linked postings"),
            # Grant Management
            ("module:grants.view", "View grants and budgets"),
            ("module:grants.manage", "Manage grants, budgets, and workflows"),
            ("module:grants.approve", "Approve or reject grants"),
            # Integrations
            ("module:integrations.manage", "Manage integrations (webhooks and ERP connections)"),
        ]

        perms = {}
        for code, name in baseline:
            p, _ = Permission.objects.using(alias).get_or_create(code=code, defaults={"name": name})
            perms[code] = p

        admin_role, _ = Role.objects.using(alias).get_or_create(name="Tenant Admin", defaults={"description": "Full access inside tenant."})
        for p in perms.values():
            RolePermission.objects.using(alias).get_or_create(role=admin_role, permission=p)

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

        UserRole.objects.using(alias).get_or_create(user=user, role=admin_role)

        self.stdout.write(self.style.SUCCESS(f"Bootstrapped RBAC + tenant admin '{user.email}' in DB '{alias}'."))  # noqa: T201

