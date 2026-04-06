from django.core.management.base import BaseCommand

from tenants.models import Module


class Command(BaseCommand):
    help = "Seed default platform modules (Finance & Grants, Integrations, Audit & Risk, Hospital, AI Auditor)."

    def handle(self, *args, **options):
        defaults = [
            ("finance_grants", "Financial & Grant Management"),
            ("integrations", "Integrations"),
            ("audit_risk", "Audit & Risk"),
            ("hospital", "Hospital Management System"),
            ("ai_auditor", "AI Auditor"),
        ]

        created = 0
        for code, name in defaults:
            obj, was_created = Module.objects.get_or_create(
                code=code,
                defaults={"name": name, "is_active": True},
            )
            if not was_created:
                # Ensure name/active flag are up to date if the module already exists
                changed = False
                if obj.name != name:
                    obj.name = name
                    changed = True
                if not obj.is_active:
                    obj.is_active = True
                    changed = True
                if changed:
                    obj.save()
            else:
                created += 1

        self.stdout.write(
            self.style.SUCCESS(f"Seed complete. {created} module(s) created, others ensured active.")
        )

