"""Tenant URL helpers: slug-prefixed paths for /t/<tenant_slug>/… links."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse


def reverse_tenant(
    request: HttpRequest | None,
    viewname: str,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> str:
    """
    Reverse a view name and prefix with /t/<tenant_slug>/ when request.tenant is set.

    Inner routes stay registered as /t/hospital/…; TenantResolutionMiddleware strips the
    slug segment before resolve. Generated links must include the slug for correct routing.
    """
    if args is None:
        args = ()
    if kwargs:
        path = reverse(viewname, kwargs=kwargs)
    elif args:
        path = reverse(viewname, args=args)
    else:
        path = reverse(viewname)

    tenant = getattr(request, "tenant", None) if request else None
    if tenant and getattr(tenant, "slug", None) and path.startswith("/t/"):
        rest = path[3:]
        return f"/t/{tenant.slug}/{rest}"
    return path


def reverse_tenant_safe(
    request: HttpRequest | None,
    viewname: str,
    *,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> str:
    """Like reverse_tenant but returns '#' if the view name cannot be resolved."""
    try:
        return reverse_tenant(request, viewname, args=args or (), kwargs=kwargs)
    except NoReverseMatch:
        return "#"
