"""One-time interactive OAuth2 setup command for Microsoft 365 email access."""

import http.server
import logging
import secrets
import threading
import webbrowser

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger("inventory.microsoft_oauth_setup")


class Command(BaseCommand):
    help = (
        "One-time interactive setup: captures a Microsoft OAuth2 refresh token "
        "by opening a browser for the mailbox owner to sign in."
    )

    def handle(self, *args, **options):
        import msal
        from cryptography.fernet import Fernet

        from inventory.models import MicrosoftOAuthToken

        # Validate required env vars
        client_id = getattr(settings, "MS_OAUTH_CLIENT_ID", "")
        client_secret = getattr(settings, "MS_OAUTH_CLIENT_SECRET", "")
        tenant_id = getattr(settings, "MS_OAUTH_TENANT_ID", "")
        encryption_key = getattr(settings, "MS_OAUTH_TOKEN_ENCRYPTION_KEY", "")

        missing = []
        if not client_id:
            missing.append("MS_OAUTH_CLIENT_ID")
        if not client_secret:
            missing.append("MS_OAUTH_CLIENT_SECRET")
        if not tenant_id:
            missing.append("MS_OAUTH_TENANT_ID")
        if not encryption_key:
            missing.append("MS_OAUTH_TOKEN_ENCRYPTION_KEY")

        if missing:
            raise CommandError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Set them before running this command."
            )

        redirect_uri = getattr(settings, "MS_OAUTH_REDIRECT_URI", "http://localhost:8765/oauth/callback")
        scopes = settings.MS_OAUTH_SCOPES.split()
        authority = settings.MS_OAUTH_AUTHORITY

        fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)

        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=authority,
        )

        state = secrets.token_urlsafe(32)
        auth_url = app.get_authorization_request_url(
            scopes=scopes,
            state=state,
            redirect_uri=redirect_uri,
        )

        self.stdout.write(self.style.WARNING("\nOpening browser for Microsoft sign-in..."))
        self.stdout.write(f"If the browser doesn't open, visit this URL:\n\n{auth_url}\n")

        # Set up the callback server
        result = {"code": None, "error": None}
        server_done = threading.Event()

        class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                from urllib.parse import parse_qs, urlparse
                params = parse_qs(urlparse(self.path).query)

                if params.get("state", [None])[0] != state:
                    result["error"] = "State mismatch — possible CSRF attack."
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Error: state mismatch.")
                elif "error" in params:
                    result["error"] = params.get("error_description", params["error"])[0]
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(f"Error: {result['error']}".encode())
                elif "code" in params:
                    result["code"] = params["code"][0]
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(
                        b"<html><body><h2>Authorization successful!</h2>"
                        b"<p>You can close this tab and return to the terminal.</p></body></html>"
                    )
                else:
                    result["error"] = "No code in callback."
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Error: no authorization code received.")

                server_done.set()

            def log_message(self, format, *args):
                pass  # Suppress HTTP server logs

        server = http.server.HTTPServer(("127.0.0.1", 8765), OAuthCallbackHandler)
        server.timeout = 300  # 5 minutes

        # Open browser
        webbrowser.open(auth_url)

        # Wait for callback
        self.stdout.write("Waiting for browser sign-in (timeout: 5 minutes)...")
        server_thread = threading.Thread(target=lambda: server.handle_request())
        server_thread.start()
        server_done.wait(timeout=300)
        server.server_close()

        if result["error"]:
            raise CommandError(f"OAuth setup failed: {result['error']}")

        if not result["code"]:
            raise CommandError("Timed out waiting for browser callback.")

        # Exchange code for tokens
        self.stdout.write("Exchanging authorization code for tokens...")
        token_result = app.acquire_token_by_authorization_code(
            code=result["code"],
            scopes=scopes,
            redirect_uri=redirect_uri,
        )

        if "error" in token_result:
            raise CommandError(
                f"Token exchange failed: {token_result.get('error_description', token_result['error'])}"
            )

        if "refresh_token" not in token_result:
            raise CommandError(
                "No refresh token returned. Ensure 'offline_access' is in the requested scopes."
            )

        # Get account email from token claims
        id_token_claims = token_result.get("id_token_claims", {})
        account_email = (
            id_token_claims.get("preferred_username")
            or id_token_claims.get("email")
            or getattr(settings, "LF_EMAIL_ADDRESS", "unknown@example.com")
        )

        # Encrypt and store
        encrypted_refresh = fernet.encrypt(token_result["refresh_token"].encode())

        from django.utils import timezone

        # Delete existing token (singleton pattern)
        MicrosoftOAuthToken.objects.all().delete()

        token_row = MicrosoftOAuthToken(
            account_email=account_email,
            encrypted_refresh_token=encrypted_refresh,
            cached_access_token=token_result.get("access_token", ""),
            cached_access_token_expires_at=(
                timezone.now() + timezone.timedelta(seconds=token_result.get("expires_in", 3600))
            ),
            scopes=" ".join(scopes),
            last_refreshed_at=timezone.now(),
        )
        token_row.save()

        self.stdout.write(self.style.SUCCESS(
            f"\nOAuth setup complete. Refresh token stored for {account_email}. "
            "The app can now send and receive email."
        ))
