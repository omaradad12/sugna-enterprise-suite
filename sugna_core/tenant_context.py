from __future__ import annotations

from contextvars import ContextVar
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from tenants.models import Tenant


_current_tenant: ContextVar[Optional["Tenant"]] = ContextVar("current_tenant", default=None)


def set_current_tenant(tenant: Optional["Tenant"]) -> None:
    _current_tenant.set(tenant)


def get_current_tenant() -> Optional["Tenant"]:
    return _current_tenant.get()

