"""
Delete temporary screening files for expired or finished sessions.
Run periodically (e.g. cron every hour) to enforce SCREENING_UPLOAD_MAX_AGE_HOURS.
Sessions are tenant-scoped; run once per tenant DB or use --database.
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Delete temporary audit screening files for expired or finished sessions (all tenant DBs or --database)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            type=str,
            default=None,
            help="Run only for this DB alias (default: all tenant DBs).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would be deleted.",
        )

    def handle(self, *args, **options):
        from tenant_audit_risk.models import AuditScreeningSession, ScreeningUploadFile
        from tenant_audit_risk.services.screening_storage import delete_session_files

        tenant_apps = set(getattr(settings, "TENANT_APP_LABELS", []))
        if "tenant_audit_risk" not in tenant_apps:
            self.stdout.write("tenant_audit_risk not in TENANT_APP_LABELS, skipping.")
            return

        databases = list(settings.DATABASES.keys())
        if options["database"]:
            if options["database"] not in databases:
                self.stderr.write(f"Database '{options['database']}' not found.")
                return
            databases = [options["database"]]
        else:
            databases = [db for db in databases if db != "default"]

        dry_run = options["dry_run"]
        total_deleted = 0
        total_sessions = 0

        for db in databases:
            now = timezone.now()
            # Expired active sessions
            expired = (
                AuditScreeningSession.objects.using(db)
                .filter(
                    status=AuditScreeningSession.Status.ACTIVE,
                    expires_at__lt=now,
                )
            )
            for session in expired:
                total_sessions += 1
                count = delete_session_files(session.id) if not dry_run else 0
                if not dry_run:
                    ScreeningUploadFile.objects.using(db).filter(session=session).delete()
                    session.status = AuditScreeningSession.Status.CLOSED
                    session.save(using=db)
                else:
                    count = session.uploaded_files.count()
                total_deleted += count
                self.stdout.write(
                    f"[{db}] Session {session.id} (expired): would delete {count} file(s)"
                    if dry_run
                    else f"[{db}] Session {session.id} (expired): deleted {count} file(s)"
                )

        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry run: would process {total_sessions} session(s), {total_deleted} file(s)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Cleaned {total_sessions} session(s), {total_deleted} temporary file(s) removed."))
