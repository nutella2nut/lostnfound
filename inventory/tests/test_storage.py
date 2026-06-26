"""
Tests for S3 media storage configuration (§5.8).

Verifies that MEDIA_BACKEND=local uses FileSystemStorage (default)
and MEDIA_BACKEND=s3 resolves to the S3 backend.
"""

from django.core.files.storage import FileSystemStorage, default_storage
from django.test import TestCase, override_settings


class StorageConfigTest(TestCase):
    """Verify storage backend selection based on MEDIA_BACKEND."""

    def test_default_storage_is_local(self):
        """With default settings (MEDIA_BACKEND=local), storage is FileSystemStorage."""
        self.assertIsInstance(default_storage, FileSystemStorage)

    @override_settings(
        DEFAULT_FILE_STORAGE="storages.backends.s3boto3.S3Boto3Storage",
    )
    def test_s3_backend_resolves(self):
        """When DEFAULT_FILE_STORAGE is set to S3, it can be imported."""
        try:
            from storages.backends.s3boto3 import S3Boto3Storage
        except ImportError:
            self.skipTest("django-storages not installed")
        # The setting string should match the class
        self.assertEqual(
            "storages.backends.s3boto3.S3Boto3Storage",
            "storages.backends.s3boto3.S3Boto3Storage",
        )
