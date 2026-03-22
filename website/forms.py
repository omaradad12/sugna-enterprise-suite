from django import forms


class ContactForm(forms.Form):
    organization_name = forms.CharField(
        label="Organization name",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-input", "autocomplete": "organization"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-input", "autocomplete": "email"}),
    )
    phone = forms.CharField(
        required=False,
        max_length=40,
        widget=forms.TextInput(attrs={"class": "form-input", "autocomplete": "tel"}),
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-textarea", "rows": 5}),
    )


class DemoRequestForm(forms.Form):
    full_name = forms.CharField(
        label="Full name",
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-input", "autocomplete": "name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-input", "autocomplete": "email"}),
    )
    organization_name = forms.CharField(
        label="Organization",
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-input", "autocomplete": "organization"}),
    )
    phone = forms.CharField(
        required=False,
        max_length=40,
        widget=forms.TextInput(attrs={"class": "form-input", "autocomplete": "tel"}),
    )
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-textarea",
                "rows": 4,
                "placeholder": "Tell us about your programs, regions, and timeline (optional)",
            }
        ),
    )
