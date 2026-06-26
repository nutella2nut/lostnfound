"""Custom Django email backend for Microsoft 365 XOAUTH2 SMTP authentication."""

import base64
import logging
import smtplib

from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPBackend

logger = logging.getLogger("inventory.email_backends")


class MicrosoftOAuth2EmailBackend(DjangoSMTPBackend):
    """
    SMTP backend that authenticates via XOAUTH2 against Microsoft 365.
    Replaces the username/password login with an OAuth2 access token.
    """

    def open(self):
        if self.connection:
            return False

        from inventory.ms_oauth import get_access_token

        try:
            if self.use_ssl:
                self.connection = smtplib.SMTP_SSL(
                    self.host, self.port, timeout=self.timeout
                )
            else:
                self.connection = smtplib.SMTP(
                    self.host, self.port, timeout=self.timeout
                )

            if not self.use_ssl and self.use_tls:
                self.connection.ehlo()
                self.connection.starttls(
                    keyfile=self.ssl_keyfile, certfile=self.ssl_certfile
                )
                self.connection.ehlo()

            # XOAUTH2 SASL: user=<email>\x01auth=Bearer <token>\x01\x01
            access_token = get_access_token()
            auth_string = f"user={self.username}\x01auth=Bearer {access_token}\x01\x01"
            auth_b64 = base64.b64encode(auth_string.encode()).decode()
            code, response = self.connection.docmd("AUTH", "XOAUTH2 " + auth_b64)
            if code != 235:
                raise smtplib.SMTPAuthenticationError(
                    code, f"XOAUTH2 SMTP authentication failed: {code} {response}"
                )
            return True
        except Exception:
            if self.connection:
                try:
                    self.connection.quit()
                except Exception:
                    pass
                self.connection = None
            if not self.fail_silently:
                raise
            return False
