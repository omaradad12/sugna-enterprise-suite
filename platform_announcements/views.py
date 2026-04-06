from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from platform_announcements.forms import PlatformAnnouncementForm
from platform_announcements.models import PlatformAnnouncement
from platform_email_templates.services import send_announcement_emails as dispatch_announcement_emails

logger = logging.getLogger(__name__)


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def announcement_list_view(request):
    qs = PlatformAnnouncement.objects.all().order_by("-updated_at")
    rows = []
    for a in qs:
        rows.append(
            {
                "obj": a,
                "display_status": a.display_status(),
            }
        )
    return render(
        request,
        "platform_dashboard/announcements/announcement_list.html",
        {"rows": rows},
    )


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def announcement_create_view(request):
    if request.method == "POST":
        form = PlatformAnnouncementForm(request.POST)
        if form.is_valid():
            ann = form.save(commit=False)
            ann.created_by = request.user
            if ann.status == PlatformAnnouncement.Status.PUBLISHED and not ann.published_at:
                ann.published_at = timezone.now()
            ann.save()
            form.save_m2m()
            if ann.send_email and ann.status == PlatformAnnouncement.Status.PUBLISHED:
                _try_send_announcement_emails(ann)
            messages.success(request, "Announcement saved.")
            return redirect("platform_dashboard:announcement_list")
    else:
        loc = timezone.localtime(timezone.now())
        form = PlatformAnnouncementForm(
            initial={
                "status": PlatformAnnouncement.Status.DRAFT,
                "start_at": loc.strftime("%Y-%m-%dT%H:%M"),
            }
        )
    return render(
        request,
        "platform_dashboard/announcements/announcement_form.html",
        {"form": form, "mode": "create"},
    )


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def announcement_edit_view(request, pk: int):
    ann = get_object_or_404(PlatformAnnouncement, pk=pk)
    if request.method == "POST":
        form = PlatformAnnouncementForm(request.POST, instance=ann)
        if form.is_valid():
            obj = form.save(commit=False)
            if obj.status == PlatformAnnouncement.Status.PUBLISHED and not obj.published_at:
                obj.published_at = timezone.now()
            if obj.status == PlatformAnnouncement.Status.DRAFT:
                obj.published_at = None
            obj.save()
            form.save_m2m()
            if obj.send_email and obj.status == PlatformAnnouncement.Status.PUBLISHED:
                _try_send_announcement_emails(obj)
            messages.success(request, "Announcement updated.")
            return redirect("platform_dashboard:announcement_list")
    else:
        form = PlatformAnnouncementForm(instance=ann)
    return render(
        request,
        "platform_dashboard/announcements/announcement_form.html",
        {"form": form, "mode": "edit", "announcement": ann},
    )


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def announcement_delete_view(request, pk: int):
    if request.method != "POST":
        return redirect("platform_dashboard:announcement_list")
    ann = get_object_or_404(PlatformAnnouncement, pk=pk)
    title = ann.title
    ann.delete()
    messages.success(request, f"Deleted «{title}».")
    return redirect("platform_dashboard:announcement_list")


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def announcement_publish_view(request, pk: int):
    if request.method != "POST":
        return redirect("platform_dashboard:announcement_list")
    ann = get_object_or_404(PlatformAnnouncement, pk=pk)
    ann.status = PlatformAnnouncement.Status.PUBLISHED
    if not ann.published_at:
        ann.published_at = timezone.now()
    ann.save(update_fields=["status", "published_at", "updated_at"])
    if ann.send_email:
        _try_send_announcement_emails(ann)
    messages.success(request, "Published.")
    return redirect("platform_dashboard:announcement_list")


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def announcement_unpublish_view(request, pk: int):
    if request.method != "POST":
        return redirect("platform_dashboard:announcement_list")
    ann = get_object_or_404(PlatformAnnouncement, pk=pk)
    ann.status = PlatformAnnouncement.Status.DRAFT
    ann.published_at = None
    ann.save(update_fields=["status", "published_at", "updated_at"])
    messages.success(request, "Unpublished (draft).")
    return redirect("platform_dashboard:announcement_list")


def _try_send_announcement_emails(ann: PlatformAnnouncement) -> None:
    try:
        n = dispatch_announcement_emails(ann)
        logger.info("announcement id=%s email batches sent=%s", ann.pk, n)
    except Exception:
        logger.exception("announcement id=%s email dispatch failed", ann.pk)
