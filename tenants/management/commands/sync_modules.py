from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Backward-compatible alias: syncs module catalog via seed_platform."

    def handle(self, *args, **options):
        call_command("seed_platform")
