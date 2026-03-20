from __future__ import annotations

from django.core.management.base import BaseCommand

from tenants.catalog import DEFAULT_SUBSCRIPTION_PLANS, PLATFORM_MODULE_DEFINITIONS
from tenants.models import Module, SubscriptionPlan


class Command(BaseCommand):
    help = "Seed or update the control-plane Module catalog (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--deactivate-missing",
            action="store_true",
            help="Set is_active=False for modules not present in the catalog (use with care).",
        )

    def handle(self, *args, **options):
        catalog_codes = set()
        created = 0
        updated = 0
        for code, name, extra in PLATFORM_MODULE_DEFINITIONS:
            catalog_codes.add(code)
            obj, was_created = Module.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "is_active": True,
                    **extra,
                },
            )
            if was_created:
                created += 1
                continue
            changed = False
            if obj.name != name:
                obj.name = name
                changed = True
            for k, v in extra.items():
                if getattr(obj, k) != v:
                    setattr(obj, k, v)
                    changed = True
            if changed:
                obj.save()
                updated += 1

        deactivated = 0
        if options["deactivate_missing"]:
            for mod in Module.objects.exclude(code__in=catalog_codes).filter(is_active=True):
                mod.is_active = False
                mod.save(update_fields=["is_active"])
                deactivated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Platform modules seeded. Created: {created}, updated: {updated}, deactivated: {deactivated}."
            )
        )

        plans_created = 0
        for code, name, description, sort_order in DEFAULT_SUBSCRIPTION_PLANS:
            _, was_created = SubscriptionPlan.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "description": description,
                    "sort_order": sort_order,
                    "is_active": True,
                },
            )
            if was_created:
                plans_created += 1
        self.stdout.write(self.style.SUCCESS(f"Subscription plans ensured. New plans: {plans_created}."))
