"""Platform Console forms for subscription plans."""
from django import forms
from django.core.exceptions import ValidationError

from tenants.models import Module, SubscriptionPlan


class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = [
            "code",
            "name",
            "description",
            "price",
            "currency",
            "billing_cycle",
            "trial_enabled",
            "trial_duration_days",
            "visibility",
            "max_users",
            "max_storage_mb",
            "max_organizations",
            "sort_order",
            "is_active",
            "is_draft",
            "included_modules",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"class": "w-full py-2 px-3 border border-slate-200 rounded-lg text-sm font-mono"}),
            "name": forms.TextInput(attrs={"class": "w-full py-2 px-3 border border-slate-200 rounded-lg text-sm"}),
            "description": forms.Textarea(attrs={"rows": 4, "class": "w-full py-2 px-3 border border-slate-200 rounded-lg text-sm"}),
            "price": forms.NumberInput(attrs={"class": "w-full py-2 px-3 border border-slate-200 rounded-lg text-sm", "step": "0.01"}),
            "currency": forms.TextInput(attrs={"class": "w-24 py-2 px-3 border border-slate-200 rounded-lg text-sm uppercase"}),
            "billing_cycle": forms.Select(attrs={"class": "w-full py-2 px-3 border border-slate-200 rounded-lg text-sm"}),
            "trial_enabled": forms.CheckboxInput(attrs={"class": "rounded border-slate-300 text-primary-600"}),
            "trial_duration_days": forms.NumberInput(attrs={"class": "w-full py-2 px-3 border border-slate-200 rounded-lg text-sm"}),
            "visibility": forms.Select(attrs={"class": "w-full py-2 px-3 border border-slate-200 rounded-lg text-sm"}),
            "max_users": forms.NumberInput(attrs={"class": "w-full py-2 px-3 border border-slate-200 rounded-lg text-sm"}),
            "max_storage_mb": forms.NumberInput(attrs={"class": "w-full py-2 px-3 border border-slate-200 rounded-lg text-sm"}),
            "max_organizations": forms.NumberInput(attrs={"class": "w-full py-2 px-3 border border-slate-200 rounded-lg text-sm"}),
            "sort_order": forms.NumberInput(attrs={"class": "w-32 py-2 px-3 border border-slate-200 rounded-lg text-sm"}),
            "is_active": forms.CheckboxInput(attrs={"class": "rounded border-slate-300 text-primary-600"}),
            "is_draft": forms.CheckboxInput(attrs={"class": "rounded border-slate-300 text-primary-600"}),
            "included_modules": forms.SelectMultiple(
                attrs={"class": "w-full min-h-[120px] py-2 px-3 border border-slate-200 rounded-lg text-sm"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["included_modules"].queryset = Module.objects.filter(is_active=True).order_by(
            "sort_order", "code"
        )
        self.fields["included_modules"].required = False
        for fn in ("max_users", "max_storage_mb", "max_organizations", "trial_duration_days"):
            self.fields[fn].required = False

    def clean_currency(self):
        c = (self.cleaned_data.get("currency") or "USD").strip().upper()
        if len(c) != 3:
            raise ValidationError("Enter a 3-letter ISO currency code (e.g. USD).")
        return c

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not code:
            raise ValidationError("Code is required.")
        return code
