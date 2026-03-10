from __future__ import annotations

from django.core.management.base import BaseCommand

from tenants.models import Module


class Command(BaseCommand):
    help = "Ensure baseline Module catalog exists in the control-plane database."

    def handle(self, *args, **options):
        baseline = [
            ("finance", "Finance"),
            ("grants", "Grant Management"),
            ("integrations", "Integrations"),
        ]
        created = 0
        for code, name in baseline:
            _, was_created = Module.objects.get_or_create(code=code, defaults={"name": name, "is_active": True})
            created += 1 if was_created else 0
        self.stdout.write(self.style.SUCCESS(f"Module catalog synced. New: {created}"))  # noqa: T201

