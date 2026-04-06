"""Template tags for tenant slug–prefixed URL generation."""

from __future__ import annotations

from typing import Any

from django import template

from tenant_portal.url_utils import reverse_tenant

register = template.Library()


@register.simple_tag(takes_context=True)
def url_tenant(context, viewname: str, *args: Any, **kwargs: Any) -> str:
    """
    Reverse viewname and prefix with /t/<tenant_slug>/ when the request has a tenant.

    Usage:
      {% url_tenant 'tenant_portal:hospital_home' %}
      {% url_tenant 'tenant_portal:hospital_encounter_detail' encounter.id %}
      {% url_tenant 'tenant_portal:hospital_encounter_detail' encounter_id=encounter.id %}
    """
    request = context.get("request")
    if kwargs:
        return reverse_tenant(request, viewname, kwargs=kwargs)
    if args:
        return reverse_tenant(request, viewname, args=tuple(args))
    return reverse_tenant(request, viewname)
