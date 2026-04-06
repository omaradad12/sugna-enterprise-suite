# Generated manually — default platform email templates

from django.db import migrations


def seed_templates(apps, schema_editor):
    PlatformEmailTemplate = apps.get_model("platform_email_templates", "PlatformEmailTemplate")
    Status = "active"
    defs = [
        # SYSTEM
        {
            "code": "platform_announcement",
            "name": "Platform announcement",
            "category": "system",
            "subject": "Announcement: {{ announcement_title }}",
            "body": (
                "Hello,\n\n"
                "This is a message for {{ tenant_name }} ({{ tenant_domain }}).\n\n"
                "{{ announcement_title }}\n\n"
                "{{ announcement_message }}\n\n"
                "Plan: {{ plan_name }}\n\n"
                "— The platform team"
            ),
            "variables": [
                "tenant_name",
                "tenant_domain",
                "announcement_title",
                "announcement_message",
                "plan_name",
            ],
        },
        {
            "code": "maintenance_notification",
            "name": "Maintenance notification",
            "category": "system",
            "subject": "Scheduled maintenance — {{ tenant_name }}",
            "body": (
                "Dear {{ tenant_name }} team,\n\n"
                "We will perform scheduled maintenance on your environment ({{ tenant_domain }}).\n\n"
                "Details:\n{{ announcement_message }}\n\n"
                "Thank you for your patience."
            ),
            "variables": ["tenant_name", "tenant_domain", "announcement_message"],
        },
        {
            "code": "security_alert",
            "name": "Security alert",
            "category": "system",
            "subject": "Security notice — {{ tenant_name }}",
            "body": (
                "Important security information for {{ tenant_name }} ({{ tenant_domain }}):\n\n"
                "{{ announcement_message }}\n\n"
                "If you have questions, contact support."
            ),
            "variables": ["tenant_name", "tenant_domain", "announcement_message"],
        },
        {
            "code": "new_feature_release",
            "name": "New feature release",
            "category": "system",
            "subject": "New features available — {{ plan_name }}",
            "body": (
                "Hello {{ tenant_name }},\n\n"
                "We have released new capabilities on the platform.\n\n"
                "{{ announcement_message }}\n\n"
                "Your plan: {{ plan_name }}"
            ),
            "variables": ["tenant_name", "announcement_message", "plan_name"],
        },
        # TENANT
        {
            "code": "welcome_email",
            "name": "Welcome email",
            "category": "tenant",
            "subject": "Welcome to Sugna — {{ tenant_name }}",
            "body": (
                "Welcome to {{ tenant_name }}!\n\n"
                "Your workspace is available at {{ tenant_domain }}.\n\n"
                "Plan: {{ plan_name }}\n\n"
                "We are glad you are here."
            ),
            "variables": ["tenant_name", "tenant_domain", "plan_name"],
        },
        {
            "code": "tenant_activation",
            "name": "Tenant activation",
            "category": "tenant",
            "subject": "Your organization is active — {{ tenant_name }}",
            "body": (
                "Good news — {{ tenant_name }} is now active.\n\n"
                "Domain: {{ tenant_domain }}\n"
                "Plan: {{ plan_name }}"
            ),
            "variables": ["tenant_name", "tenant_domain", "plan_name"],
        },
        {
            "code": "tenant_suspension",
            "name": "Tenant suspension",
            "category": "tenant",
            "subject": "Account notice — {{ tenant_name }}",
            "body": (
                "This is regarding {{ tenant_name }} ({{ tenant_domain }}).\n\n"
                "{{ announcement_message }}\n\n"
                "Please contact support if you need assistance."
            ),
            "variables": ["tenant_name", "tenant_domain", "announcement_message"],
        },
        {
            "code": "trial_ending_reminder",
            "name": "Trial ending reminder",
            "category": "tenant",
            "subject": "Your trial is ending soon — {{ tenant_name }}",
            "body": (
                "Hello {{ tenant_name }},\n\n"
                "Your trial period is approaching its end (plan: {{ plan_name }}).\n\n"
                "{{ announcement_message }}\n\n"
                "Due: {{ due_date }}"
            ),
            "variables": ["tenant_name", "plan_name", "announcement_message", "due_date"],
        },
        # BILLING
        {
            "code": "invoice_generated",
            "name": "Invoice generated",
            "category": "billing",
            "subject": "Invoice {{ invoice_number }} — {{ tenant_name }}",
            "body": (
                "Hello {{ tenant_name }},\n\n"
                "A new invoice has been generated.\n\n"
                "Invoice: {{ invoice_number }}\n"
                "Amount: {{ amount }}\n"
                "Due: {{ due_date }}\n"
                "Plan: {{ plan_name }}"
            ),
            "variables": ["tenant_name", "invoice_number", "amount", "due_date", "plan_name"],
        },
        {
            "code": "payment_confirmation",
            "name": "Payment confirmation",
            "category": "billing",
            "subject": "Payment received — {{ invoice_number }}",
            "body": (
                "Thank you, {{ tenant_name }}.\n\n"
                "We have recorded your payment.\n\n"
                "Reference: {{ invoice_number }}\n"
                "Amount: {{ amount }}\n"
                "Plan: {{ plan_name }}"
            ),
            "variables": ["tenant_name", "invoice_number", "amount", "plan_name"],
        },
        {
            "code": "payment_failed",
            "name": "Payment failed",
            "category": "billing",
            "subject": "Payment issue — {{ tenant_name }}",
            "body": (
                "We could not process a payment for {{ tenant_name }}.\n\n"
                "Invoice: {{ invoice_number }}\n"
                "Amount: {{ amount }}\n"
                "Due: {{ due_date }}\n\n"
                "Please update your payment method."
            ),
            "variables": ["tenant_name", "invoice_number", "amount", "due_date"],
        },
        {
            "code": "subscription_renewal_reminder",
            "name": "Subscription renewal reminder",
            "category": "billing",
            "subject": "Renewal reminder — {{ plan_name }}",
            "body": (
                "Hello {{ tenant_name }},\n\n"
                "Your subscription ({{ plan_name }}) is due for renewal.\n\n"
                "Amount: {{ amount }}\n"
                "Due: {{ due_date }}\n\n"
                "{{ announcement_message }}"
            ),
            "variables": ["tenant_name", "plan_name", "amount", "due_date", "announcement_message"],
        },
        # SUPPORT
        {
            "code": "ticket_created",
            "name": "Ticket created",
            "category": "support",
            "subject": "Support ticket opened — {{ tenant_name }}",
            "body": (
                "Hello {{ tenant_name }},\n\n"
                "We have received your support request.\n\n"
                "{{ announcement_message }}\n\n"
                "We will respond as soon as possible."
            ),
            "variables": ["tenant_name", "announcement_message"],
        },
        {
            "code": "ticket_response",
            "name": "Ticket response",
            "category": "support",
            "subject": "Update on your support request — {{ tenant_name }}",
            "body": (
                "Hello {{ tenant_name }},\n\n"
                "{{ announcement_message }}\n\n"
                "— Support"
            ),
            "variables": ["tenant_name", "announcement_message"],
        },
        {
            "code": "ticket_resolved",
            "name": "Ticket resolved",
            "category": "support",
            "subject": "Ticket resolved — {{ tenant_name }}",
            "body": (
                "Hello {{ tenant_name }},\n\n"
                "Your support ticket has been marked resolved.\n\n"
                "{{ announcement_message }}"
            ),
            "variables": ["tenant_name", "announcement_message"],
        },
    ]
    for d in defs:
        PlatformEmailTemplate.objects.update_or_create(
            code=d["code"],
            defaults={
                "name": d["name"],
                "category": d["category"],
                "subject": d["subject"],
                "body": d["body"],
                "variables": d["variables"],
                "status": Status,
                "is_system": True,
            },
        )


def unseed_templates(apps, schema_editor):
    PlatformEmailTemplate = apps.get_model("platform_email_templates", "PlatformEmailTemplate")
    PlatformEmailTemplate.objects.filter(is_system=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("platform_email_templates", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_templates, unseed_templates),
    ]
