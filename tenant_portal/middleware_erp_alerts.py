"""Attach structured ERP alert collector to each request."""

from __future__ import annotations

from tenant_portal.erp_alerting.collector import ErpAlertCollector


class ErpAlertingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.erp_alerts = ErpAlertCollector()
        return self.get_response(request)
