"""
Resolve which platform announcements apply to a control-plane Tenant.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

from platform_announcements.models import PlatformAnnouncement

if TYPE_CHECKING:
    from tenants.models import Tenant


def active_announcements_queryset():
    now = timezone.now()
    return PlatformAnnouncement.objects.filter(
        status=PlatformAnnouncement.Status.PUBLISHED,
        start_at__lte=now,
    ).filter(Q(end_at__isnull=True) | Q(end_at__gte=now))


def announcement_applies_to_tenant(ann: PlatformAnnouncement, tenant: "Tenant") -> bool:
    if not ann.is_visible_now():
        return False
    mode = ann.targeting_mode
    if mode == PlatformAnnouncement.TargetingMode.ALL_TENANTS:
        return True
    if mode == PlatformAnnouncement.TargetingMode.SELECTED_TENANTS:
        return ann.target_tenants.filter(pk=tenant.pk).exists()
    if mode == PlatformAnnouncement.TargetingMode.BY_MODULE:
        mids = ann.target_modules.values_list("pk", flat=True)
        if not mids:
            return False
        return tenant.modules.filter(pk__in=mids).exists()
    return False


def get_announcements_for_tenant(tenant: "Tenant | None") -> dict:
    """
    Return lists for tenant UI: bell list, banners, popups (ordered by priority then start).
    """
    empty = {
        "platform_announcements": [],
        "platform_announcements_banners": [],
        "platform_announcements_popups": [],
        "platform_announcements_popups_json": "[]",
        "platform_announcements_count": 0,
    }
    if tenant is None:
        return empty
    qs = (
        active_announcements_queryset()
        .prefetch_related("target_tenants", "target_modules")
        .order_by("-priority", "-start_at")
    )
    # Priority order: critical > high > medium > low (model order not same — sort in Python)
    priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    matched: list[PlatformAnnouncement] = []
    for ann in qs:
        if announcement_applies_to_tenant(ann, tenant):
            matched.append(ann)

    matched.sort(key=lambda a: (priority_rank.get(a.priority, 9), -a.start_at.timestamp()))

    banners = [a for a in matched if a.show_dashboard_banner]
    popups = [a for a in matched if a.show_popup]
    popups_payload = [
        {"id": a.pk, "title": a.title, "message": a.message, "priority": a.priority}
        for a in popups
    ]

    return {
        "platform_announcements": matched,
        "platform_announcements_banners": banners,
        "platform_announcements_popups": popups,
        "platform_announcements_popups_json": json.dumps(popups_payload),
        "platform_announcements_count": len(matched),
    }


def iter_tenants_for_announcement(ann: "PlatformAnnouncement"):
    """
    Yield control-plane Tenant rows that should receive this announcement (email targeting).
    """
    from tenants.models import Tenant

    mode = ann.targeting_mode
    if mode == PlatformAnnouncement.TargetingMode.ALL_TENANTS:
        yield from Tenant.objects.all().order_by("name")
    elif mode == PlatformAnnouncement.TargetingMode.SELECTED_TENANTS:
        yield from ann.target_tenants.all().order_by("name")
    elif mode == PlatformAnnouncement.TargetingMode.BY_MODULE:
        mids = list(ann.target_modules.values_list("pk", flat=True))
        if not mids:
            return
        yield from Tenant.objects.filter(modules__in=mids).distinct().order_by("name")
