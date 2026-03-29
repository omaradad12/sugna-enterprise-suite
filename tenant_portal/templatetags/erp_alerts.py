"""
Template tags for field-level structured alerts.

Usage:
  {% load erp_alerts %}
  {% erp_field_alert "amount" %}
"""

from django import template

register = template.Library()


@register.inclusion_tag("tenant_portal/includes/erp_field_alert.html", takes_context=True)
def erp_field_alert(context, field_name: str):
    issues = (context.get("erp_field_issues") or {}).get(field_name) or []
    return {"field_name": field_name, "issues": issues}
