"""One-off: inspect tenant DB schema. Usage: python scripts/inspect_tenant_db.py t001"""
import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sugna_core.settings")
django.setup()

from django.db import connections

from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant

slug = sys.argv[1] if len(sys.argv) > 1 else "t001"
t = Tenant.objects.filter(slug=slug).first()
if not t:
    print("Tenant not found:", slug)
    sys.exit(1)
ensure_tenant_db_configured(t)
alias = tenant_db_alias(t)
print("Alias:", alias)
c = connections[alias].cursor()
c.execute(
    "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE %s ORDER BY 1",
    ["tenant_finance%"],
)
print("Tables:", [r[0] for r in c.fetchall()])
c.execute("SELECT name FROM django_migrations WHERE app=%s ORDER BY id", ["tenant_finance"])
print("Applied tenant_finance migrations:", [r[0] for r in c.fetchall()])
