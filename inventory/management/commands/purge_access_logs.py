"""Delete AccessAuditLog rows past the retention window (Settings → Audit & privacy).

Run on a schedule in production (e.g. a daily Railway cron job):
    python manage.py purge_access_logs
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from inventory.models import AccessAuditLog
from inventory.site_settings import get_site_settings


class Command(BaseCommand):
    help = "Purge access logs older than the retention window set in Settings (default 365 days)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=None,
            help="Retention window in days. Defaults to the value in Settings → Audit & privacy.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would be deleted without deleting.",
        )

    def handle(self, *args, **options):
        site = get_site_settings()
        days = options["days"] or site.audit_retention_days
        cutoff = timezone.now() - timedelta(days=days)
        qs = AccessAuditLog.objects.filter(created_at__lt=cutoff)
        count = qs.count()

        if options["dry_run"]:
            self.stdout.write(
                f"[dry-run] Would delete {count} access log(s) older than "
                f"{days} days (before {cutoff:%Y-%m-%d %H:%M}Z)."
            )
            return

        deleted, _ = qs.delete()
        site.last_audit_purge_at = timezone.now()
        site.save(update_fields=["last_audit_purge_at"])
        self.stdout.write(
            f"Deleted {deleted} access log(s) older than {days} days "
            f"(before {cutoff:%Y-%m-%d %H:%M}Z)."
        )
