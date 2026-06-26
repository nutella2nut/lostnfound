"""Tests for inventory/ms_oauth.py — OAuth2 token helper."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from inventory.models import MicrosoftOAuthToken
from inventory.ms_oauth import (
    MicrosoftOAuthNotConfigured,
    MicrosoftOAuthRefreshFailed,
    get_access_token,
    is_configured,
)

TEST_ENCRYPTION_KEY = Fernet.generate_key().decode()
TEST_FERNET = Fernet(TEST_ENCRYPTION_KEY.encode())


def _create_token_row(
    access_token="cached-token",
    expires_in_seconds=3600,
    refresh_token="test-refresh-token",
):
    """Helper to create a MicrosoftOAuthToken row."""
    encrypted = TEST_FERNET.encrypt(refresh_token.encode())
    return MicrosoftOAuthToken.objects.create(
        account_email="test@tisb.ac.in",
        encrypted_refresh_token=encrypted,
        cached_access_token=access_token,
        cached_access_token_expires_at=timezone.now() + timedelta(seconds=expires_in_seconds),
        scopes="https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send offline_access",
        last_refreshed_at=timezone.now(),
    )


@override_settings(
    MS_OAUTH_CLIENT_ID="test-client-id",
    MS_OAUTH_CLIENT_SECRET="test-secret",
    MS_OAUTH_TENANT_ID="test-tenant",
    MS_OAUTH_AUTHORITY="https://login.microsoftonline.com/test-tenant",
    MS_OAUTH_TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
)
class GetAccessTokenTests(TestCase):
    def test_returns_cached_token_when_not_expired(self):
        _create_token_row(access_token="my-cached-token", expires_in_seconds=3600)
        token = get_access_token()
        self.assertEqual(token, "my-cached-token")

    @patch("inventory.ms_oauth._get_msal_app")
    def test_refreshes_when_cached_token_expired(self, mock_get_app):
        _create_token_row(access_token="expired-token", expires_in_seconds=30)
        mock_app = MagicMock()
        mock_app.acquire_token_by_refresh_token.return_value = {
            "access_token": "new-access-token",
            "expires_in": 3600,
        }
        mock_get_app.return_value = mock_app

        token = get_access_token()
        self.assertEqual(token, "new-access-token")
        mock_app.acquire_token_by_refresh_token.assert_called_once()

        # Verify stored
        row = MicrosoftOAuthToken.objects.get()
        self.assertEqual(row.cached_access_token, "new-access-token")
        self.assertIsNotNone(row.last_refreshed_at)

    def test_raises_not_configured_when_no_row(self):
        with self.assertRaises(MicrosoftOAuthNotConfigured):
            get_access_token()

    @patch("inventory.ms_oauth._get_msal_app")
    def test_raises_refresh_failed_on_invalid_grant(self, mock_get_app):
        _create_token_row(access_token="expired", expires_in_seconds=30)
        mock_app = MagicMock()
        mock_app.acquire_token_by_refresh_token.return_value = {
            "error": "invalid_grant",
            "error_description": "Token expired",
        }
        mock_get_app.return_value = mock_app

        with self.assertRaises(MicrosoftOAuthRefreshFailed):
            get_access_token()

    @patch("inventory.ms_oauth._get_msal_app")
    def test_refresh_token_rotation(self, mock_get_app):
        row = _create_token_row(access_token="expired", expires_in_seconds=30)
        mock_app = MagicMock()
        mock_app.acquire_token_by_refresh_token.return_value = {
            "access_token": "new-access",
            "expires_in": 3600,
            "refresh_token": "rotated-refresh-token",
        }
        mock_get_app.return_value = mock_app

        get_access_token()

        row.refresh_from_db()
        decrypted = TEST_FERNET.decrypt(row.encrypted_refresh_token).decode()
        self.assertEqual(decrypted, "rotated-refresh-token")

    def test_encrypted_refresh_token_not_readable_without_key(self):
        row = _create_token_row(refresh_token="secret-refresh")
        wrong_fernet = Fernet(Fernet.generate_key())
        with self.assertRaises(Exception):
            wrong_fernet.decrypt(row.encrypted_refresh_token)


class SingletonTests(TestCase):
    def test_singleton_enforcement(self):
        _create_token_row.__wrapped__ = None  # just to clarify we're not using helpers
        encrypted = TEST_FERNET.encrypt(b"token1")
        MicrosoftOAuthToken.objects.create(
            account_email="a@tisb.ac.in",
            encrypted_refresh_token=encrypted,
            scopes="offline_access",
        )
        with self.assertRaises(ValidationError):
            MicrosoftOAuthToken(
                account_email="b@tisb.ac.in",
                encrypted_refresh_token=encrypted,
                scopes="offline_access",
            ).save()


@override_settings(MS_OAUTH_CLIENT_ID="")
class IsConfiguredTests(TestCase):
    def test_not_configured_without_client_id(self):
        self.assertFalse(is_configured())

    @override_settings(MS_OAUTH_CLIENT_ID="test")
    def test_not_configured_without_token_row(self):
        self.assertFalse(is_configured())
