"""
Canonical identification of receivable (accounts receivable) GL accounts for reporting.

Used by outstanding receivables, global indicators, and alerts so totals always
match posted subledger / GL logic.
"""

from django.db.models import Q

from tenant_finance.models import ChartAccount


def receivable_accounts_q() -> Q:
    """
    Asset accounts that represent receivables: name/code match, or RECEIVABLE category.
    """
    return Q(type=ChartAccount.Type.ASSET) & (
        Q(name__icontains="receivable")
        | Q(code__icontains="receivable")
        | Q(category__code__iexact="RECEIVABLE")
        | Q(category__name__icontains="receivable")
    )
