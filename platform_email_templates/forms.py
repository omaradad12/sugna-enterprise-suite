from __future__ import annotations

from django import forms

from platform_email_templates.models import PlatformEmailTemplate
from platform_email_templates.services import DOCUMENTED_VARIABLE_KEYS, default_sample_context


class PlatformEmailTemplateForm(forms.ModelForm):
    variables_text = forms.CharField(
        label="Variables list",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono",
                "placeholder": "One variable per line, e.g.\ntenant_name\nannouncement_title",
            }
        ),
        help_text="One per line; should match placeholders in subject and body.",
    )

    class Meta:
        model = PlatformEmailTemplate
        fields = ["code", "name", "category", "subject", "body", "status"]
        widgets = {
            "code": forms.TextInput(attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono"}),
            "name": forms.TextInput(attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"}),
            "category": forms.Select(attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"}),
            "subject": forms.TextInput(attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"}),
            "body": forms.Textarea(attrs={"rows": 14, "class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-mono"}),
            "status": forms.Select(attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"}),
        }

    def __init__(self, *args, **kwargs):
        self.is_create = kwargs.pop("is_create", False)
        super().__init__(*args, **kwargs)
        if self.is_create:
            self.fields["code"].required = True
        if self.instance and self.instance.pk and self.instance.variables:
            self.initial.setdefault("variables_text", "\n".join(self.instance.variables))
        if self.instance and self.instance.pk and getattr(self.instance, "is_system", False):
            self.fields["code"].disabled = True

    def clean_variables_text(self):
        raw = (self.cleaned_data.get("variables_text") or "").strip()
        if not raw:
            return []
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        return lines

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.variables = self.cleaned_data.get("variables_text") or []
        if commit:
            obj.save()
        return obj


class SampleContextForm(forms.Form):
    """Sample values for preview / test send (merge fields)."""

    tenant_name = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "w-full rounded border border-slate-200 px-2 py-1.5 text-sm"}))
    tenant_domain = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "w-full rounded border border-slate-200 px-2 py-1.5 text-sm"}))
    announcement_title = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "w-full rounded border border-slate-200 px-2 py-1.5 text-sm"}))
    announcement_message = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3, "class": "w-full rounded border border-slate-200 px-2 py-1.5 text-sm"}))
    invoice_number = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "w-full rounded border border-slate-200 px-2 py-1.5 text-sm"}))
    amount = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "w-full rounded border border-slate-200 px-2 py-1.5 text-sm"}))
    due_date = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "w-full rounded border border-slate-200 px-2 py-1.5 text-sm"}))
    plan_name = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "w-full rounded border border-slate-200 px-2 py-1.5 text-sm"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        samples = default_sample_context()
        for name in DOCUMENTED_VARIABLE_KEYS:
            if name in self.fields and not self.initial.get(name):
                self.initial[name] = samples.get(name, "")


def sample_dict_from_form(form: SampleContextForm) -> dict[str, str]:
    if not form.is_valid():
        return default_sample_context()
    out = default_sample_context()
    for k in DOCUMENTED_VARIABLE_KEYS:
        v = form.cleaned_data.get(k)
        if v is not None and str(v).strip() != "":
            out[k] = str(v).strip()
    return out


class TestEmailForm(forms.Form):
    test_email = forms.EmailField(
        label="Send test to",
        widget=forms.EmailInput(attrs={"class": "w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"}),
    )
