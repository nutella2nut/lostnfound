"""Tests for inventory/email_backends.py — XOAUTH2 SMTP backend."""

import base64
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings


@override_settings(
    EMAIL_HOST="smtp-mail.outlook.com",
    EMAIL_PORT=587,
    EMAIL_USE_TLS=True,
    EMAIL_USE_SSL=False,
    EMAIL_HOST_USER="test@tisb.ac.in",
)
class MicrosoftOAuth2EmailBackendTests(TestCase):

    @patch("inventory.ms_oauth.get_access_token")
    @patch("smtplib.SMTP")
    def test_builds_correct_xoauth2_string(self, mock_smtp_cls, mock_get_token):
        from inventory.email_backends import MicrosoftOAuth2EmailBackend

        mock_get_token.return_value = "test-access-token-123"
        mock_conn = MagicMock()
        mock_conn.docmd.return_value = (235, b"Authentication successful")
        mock_smtp_cls.return_value = mock_conn

        backend = MicrosoftOAuth2EmailBackend(
            host="smtp-mail.outlook.com",
            port=587,
            username="test@tisb.ac.in",
            password="",
            use_tls=True,
            use_ssl=False,
        )
        result = backend.open()
        self.assertTrue(result)

        # Verify XOAUTH2 string format
        mock_conn.docmd.assert_called_once()
        call_args = mock_conn.docmd.call_args
        self.assertEqual(call_args[0][0], "AUTH")

        auth_b64 = call_args[0][1].replace("XOAUTH2 ", "")
        decoded = base64.b64decode(auth_b64).decode()
        self.assertEqual(
            decoded,
            "user=test@tisb.ac.in\x01auth=Bearer test-access-token-123\x01\x01",
        )

    @patch("inventory.ms_oauth.get_access_token")
    @patch("smtplib.SMTP")
    def test_raises_on_non_235_response(self, mock_smtp_cls, mock_get_token):
        from inventory.email_backends import MicrosoftOAuth2EmailBackend

        mock_get_token.return_value = "bad-token"
        mock_conn = MagicMock()
        mock_conn.docmd.return_value = (535, b"Authentication unsuccessful")
        mock_smtp_cls.return_value = mock_conn

        backend = MicrosoftOAuth2EmailBackend(
            host="smtp-mail.outlook.com",
            port=587,
            username="test@tisb.ac.in",
            password="",
            use_tls=True,
            use_ssl=False,
            fail_silently=False,
        )
        with self.assertRaises(Exception) as ctx:
            backend.open()
        self.assertIn("535", str(ctx.exception))

    @patch("inventory.ms_oauth.get_access_token")
    @patch("smtplib.SMTP")
    def test_get_access_token_called_once_per_open(self, mock_smtp_cls, mock_get_token):
        from inventory.email_backends import MicrosoftOAuth2EmailBackend

        mock_get_token.return_value = "token"
        mock_conn = MagicMock()
        mock_conn.docmd.return_value = (235, b"OK")
        mock_smtp_cls.return_value = mock_conn

        backend = MicrosoftOAuth2EmailBackend(
            host="smtp-mail.outlook.com",
            port=587,
            username="test@tisb.ac.in",
            password="",
            use_tls=True,
            use_ssl=False,
        )
        backend.open()
        mock_get_token.assert_called_once()
