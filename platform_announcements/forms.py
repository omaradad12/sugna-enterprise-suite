from __future__ import annotations

from django import forms
from django.utils import timezone

from platform_announcements.models import PlatformAnnouncement
from platform_email_templates.models import PlatformEmailTemplate
from tenants.models import Module, Tenant


class PlatformAnnouncementForm(forms.ModelForm):
    class Meta:
        model = PlatformAnnouncement
        fields = [
            "title",
            "message",
            "category",
            "priority",
            "targeting_mode",
            "target_tenants",
            "target_modules",
            "start_at",
            "end_at",
            "send_email",
            "show_popup",
            "show_dashboard_banner",
            "status",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"}),
            "message": forms.Textarea(attrs={"rows": 6, "class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"}),
            "category": forms.Select(attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"}),
            "priority": forms.Select(attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"}),
            "targeting_mode": forms.Select(attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"}),
            "target_tenants": forms.SelectMultiple(
                attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm min-h-[120px]"}
            ),
            "target_modules": forms.SelectMultiple(
                attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm min-h-[100px]"}
            ),
            "start_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local", "class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"},
            ),
            "end_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"type": "datetime-local", "class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"},
            ),
            "send_email": forms.CheckboxInput(attrs={"class": "rounded border-slate-300"}),
            "email_template": forms.Select(
                attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"}
            ),
            "show_popup": forms.CheckboxInput(attrs={"class": "rounded border-slate-300"}),
            "show_dashboard_banner": forms.CheckboxInput(attrs={"class": "rounded border-slate-300"}),
            "status": forms.Select(attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["target_tenants"].queryset = Tenant.objects.order_by("name")
        self.fields["target_modules"].queryset = Module.objects.filter(is_active=True).order_by("sort_order", "code")
        self.fields["target_tenants"].required = False
        self.fields["target_modules"].required = False
        self.fields["end_at"].required = False
        self.fields["email_template"].required = False
        self.fields["email_template"].queryset = PlatformEmailTemplate.objects.filter(
            status=PlatformEmailTemplate.Status.ACTIVE
        ).order_by("category", "name")
        self.fields["email_template"].empty_label = "— Default: Platform announcement —"
        self.fields["start_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S"]
        self.fields["end_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", ""]
        for name in ("start_at", "end_at"):
            val = getattr(self.instance, name, None)
            if val and self.instance.pk:
                loc = timezone.localtime(val)
                self.initial[name] = loc.strftime("%Y-%m-%dT%H:%M")

    def clean_start_at(self):
        v = self.cleaned_data.get("start_at")
        if v is None:
            raise forms.ValidationError("Start date/time is required.")
        if timezone.is_naive(v):
            v = timezone.make_aware(v, timezone.get_current_timezone())
        return v

    def clean_end_at(self):
        v = self.cleaned_data.get("end_at")
        if not v:
            return None
        if timezone.is_naive(v):
            v = timezone.make_aware(v, timezone.get_current_timezone())
        return v
