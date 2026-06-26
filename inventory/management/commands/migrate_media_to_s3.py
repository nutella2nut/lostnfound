"""
One-time management command to upload existing local media files to S3.

Usage:
    python manage.py migrate_media_to_s3 --dry-run   # List what would be uploaded
    python manage.py migrate_media_to_s3 --verbose    # Upload with per-file logging
    python manage.py migrate_media_to_s3              # Upload quietly
"""

import logging

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from inventory.models import ItemImage, StudentLostItemImage

logger = logging.getLogger("inventory.migrate_media")


class Command(BaseCommand):
    help = "Migrate local media files to S3 storage."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List files that would be uploaded without actually uploading.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Log each file as it is processed.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        verbose = options["verbose"]

        media_backend = getattr(settings, "MEDIA_BACKEND", "local")
        if media_backend != "s3" and not dry_run:
            self.stderr.write(
                "MEDIA_BACKEND is not set to 's3'. Set MEDIA_BACKEND=s3 before running."
            )
            return

        image_fields = []
        for img in ItemImage.objects.all():
            image_fields.append(img.image)
        for img in StudentLostItemImage.objects.all():
            image_fields.append(img.image)

        n_uploaded = 0
        n_skipped = 0
        n_failed = 0

        for field in image_fields:
            name = field.name
            if not name:
                continue

            # Check if already exists in remote storage
            try:
                if default_storage.exists(name):
                    if verbose:
                        self.stdout.write(f"  SKIP (exists): {name}")
                    n_skipped += 1
                    continue
            except Exception:
                pass  # If exists() fails, try uploading anyway

            if dry_run:
                self.stdout.write(f"  WOULD UPLOAD: {name}")
                n_uploaded += 1
                continue

            # Read from local filesystem
            local_path = settings.BASE_DIR / "media" / name
            if not local_path.exists():
                if verbose:
                    self.stdout.write(f"  SKIP (not on disk): {name}")
                n_skipped += 1
                continue

            try:
                with open(local_path, "rb") as f:
                    default_storage.save(name, f)
                if verbose:
                    self.stdout.write(f"  UPLOADED: {name}")
                n_uploaded += 1
            except Exception as e:
                logger.error("Failed to upload %s: %s", name, e)
                if verbose:
                    self.stderr.write(f"  FAILED: {name} — {e}")
                n_failed += 1

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            f"\n{prefix}Summary: {n_uploaded} uploaded, "
            f"{n_skipped} already present/skipped, {n_failed} failed"
        )
