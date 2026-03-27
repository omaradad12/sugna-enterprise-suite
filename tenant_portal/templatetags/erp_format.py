"""Suite-wide numeric display: thousands separators and fixed decimals."""

from decimal import Decimal, InvalidOperation

from django import template
from django.contrib.humanize.templatetags.humanize import intcomma
from django.template.defaultfilters import floatformat

register = template.Library()


@register.filter
def erp_amount(value):
    """Format money-like values as 10,000.00 (comma thousands, two decimals)."""
    if value is None or value == "":
        return ""
    try:
        if isinstance(value, Decimal):
            num = value
        elif isinstance(value, str):
            num = Decimal(value)
        else:
            num = Decimal(str(float(value)))
        s = floatformat(num, 2)
        return intcomma(s)
    except (ValueError, TypeError, InvalidOperation):
        return value


@register.filter
def erp_int(value):
    """Format integers with thousand separators (e.g. 10,000)."""
    if value is None or value == "":
        return ""
    try:
        return intcomma(int(value))
    except (ValueError, TypeError):
        return value


@register.filter
def erp_amount_whole(value):
    """Whole amounts with comma grouping, no decimals (e.g. 120,000)."""
    if value is None or value == "":
        return ""
    try:
        if isinstance(value, Decimal):
            num = value
        elif isinstance(value, str):
            num = Decimal(value)
        else:
            num = Decimal(str(float(value)))
        rounded = int(num.quantize(Decimal("1")))
        return intcomma(str(rounded))
    except (ValueError, TypeError, InvalidOperation):
        return value
