from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from platform_email_templates.forms import (
    PlatformEmailTemplateForm,
    SampleContextForm,
    TestEmailForm,
    sample_dict_from_form,
)
from platform_email_templates.models import PlatformEmailTemplate
from platform_email_templates.services import (
    DOCUMENTED_VARIABLE_KEYS,
    default_sample_context,
    render_platform_email_template,
    send_test_email,
)

logger = logging.getLogger(__name__)


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def email_template_list_view(request):
    rows = PlatformEmailTemplate.objects.all().order_by("category", "name")
    return render(
        request,
        "platform_dashboard/email_templates/email_template_list.html",
        {"rows": rows},
    )


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def email_template_create_view(request):
    if request.method == "POST":
        form = PlatformEmailTemplateForm(request.POST, is_create=True)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.is_system = False
            obj.save()
            messages.success(request, "Email template created.")
            return redirect("platform_dashboard:email_template_list")
    else:
        form = PlatformEmailTemplateForm(is_create=True)
    return render(
        request,
        "platform_dashboard/email_templates/email_template_form.html",
        {"form": form, "mode": "create"},
    )


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def email_template_edit_view(request, pk: int):
    obj = get_object_or_404(PlatformEmailTemplate, pk=pk)
    if request.method == "POST":
        form = PlatformEmailTemplateForm(request.POST, instance=obj, is_create=False)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved.")
            return redirect("platform_dashboard:email_template_list")
    else:
        form = PlatformEmailTemplateForm(instance=obj, is_create=False)
    return render(
        request,
        "platform_dashboard/email_templates/email_template_form.html",
        {"form": form, "mode": "edit", "template_obj": obj},
    )


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def email_template_delete_view(request, pk: int):
    if request.method != "POST":
        return redirect("platform_dashboard:email_template_list")
    obj = get_object_or_404(PlatformEmailTemplate, pk=pk)
    if obj.is_system:
        messages.error(request, "System templates cannot be deleted.")
        return redirect("platform_dashboard:email_template_list")
    name = obj.name
    obj.delete()
    messages.success(request, f"Deleted «{name}».")
    return redirect("platform_dashboard:email_template_list")


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def email_template_preview_view(request, pk: int):
    obj = get_object_or_404(PlatformEmailTemplate, pk=pk)
    if request.method == "POST":
        ctx_form = SampleContextForm(request.POST)
        test_form = TestEmailForm(request.POST)
        action = request.POST.get("action") or "preview"
        if action == "send_test":
            if test_form.is_valid() and ctx_form.is_valid():
                to = test_form.cleaned_data["test_email"]
                context_dict = sample_dict_from_form(ctx_form)
                try:
                    send_test_email(obj, to, context_dict)
                    messages.success(request, f"Test message sent to {to}.")
                except Exception as exc:
                    logger.exception("test send failed")
                    messages.error(request, f"Send failed: {exc}")
            elif not test_form.is_valid():
                messages.error(request, "Enter a valid email address for the test send.")
            else:
                messages.error(request, "Fix merge field errors before sending a test.")
    else:
        ctx_form = SampleContextForm()
        test_form = TestEmailForm(initial={"test_email": getattr(request.user, "email", "") or ""})

    context_dict = sample_dict_from_form(ctx_form)
    rendered_subject, rendered_body = render_platform_email_template(obj, context_dict)

    return render(
        request,
        "platform_dashboard/email_templates/email_template_preview.html",
        {
            "template_obj": obj,
            "ctx_form": ctx_form,
            "test_form": test_form,
            "rendered_subject": rendered_subject,
            "rendered_body": rendered_body,
        },
    )
