"""Microsoft OAuth2 token helper for XOAUTH2 IMAP/SMTP authentication."""

import logging
import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("inventory.ms_oauth")


class MicrosoftOAuthNotConfigured(Exception):
    """Raised when no MicrosoftOAuthToken row exists."""
    pass


class MicrosoftOAuthRefreshFailed(Exception):
    """Raised when the refresh token is invalid/expired."""
    pass


def _get_fernet():
    from cryptography.fernet import Fernet
    key = getattr(settings, "MS_OAUTH_TOKEN_ENCRYPTION_KEY", "")
    if not key:
        raise MicrosoftOAuthNotConfigured(
            "MS_OAUTH_TOKEN_ENCRYPTION_KEY is not set."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def _get_msal_app():
    import msal
    return msal.ConfidentialClientApplication(
        client_id=settings.MS_OAUTH_CLIENT_ID,
        client_credential=settings.MS_OAUTH_CLIENT_SECRET,
        authority=settings.MS_OAUTH_AUTHORITY,
    )


def is_configured() -> bool:
    """Returns True if MicrosoftOAuthToken row exists and env is present."""
    if not getattr(settings, "MS_OAUTH_CLIENT_ID", ""):
        return False
    from inventory.models import MicrosoftOAuthToken
    return MicrosoftOAuthToken.objects.exists()


def get_access_token() -> str:
    """
    Returns a valid access token, refreshing if necessary.
    Raises MicrosoftOAuthNotConfigured if no token row exists.
    Raises MicrosoftOAuthRefreshFailed if the refresh call fails terminally.
    """
    from inventory.models import MicrosoftOAuthToken

    try:
        token_row = MicrosoftOAuthToken.objects.get()
    except MicrosoftOAuthToken.DoesNotExist:
        raise MicrosoftOAuthNotConfigured(
            "No MicrosoftOAuthToken row exists. Run 'python manage.py microsoft_oauth_setup'."
        )

    # Return cached token if still valid (with 60s buffer)
    if (
        token_row.cached_access_token
        and token_row.cached_access_token_expires_at
        and token_row.cached_access_token_expires_at > timezone.now() + timezone.timedelta(seconds=60)
    ):
        return token_row.cached_access_token

    return _refresh_token(token_row)


def force_refresh() -> str:
    """Force a refresh even if the cached token is still valid."""
    from inventory.models import MicrosoftOAuthToken

    try:
        token_row = MicrosoftOAuthToken.objects.get()
    except MicrosoftOAuthToken.DoesNotExist:
        raise MicrosoftOAuthNotConfigured(
            "No MicrosoftOAuthToken row exists. Run 'python manage.py microsoft_oauth_setup'."
        )
    return _refresh_token(token_row)


def _refresh_token(token_row) -> str:
    """Refresh the access token using the stored refresh token. Thread-safe."""
    from inventory.models import MicrosoftOAuthToken

    fernet = _get_fernet()

    # Row-level lock to prevent concurrent refresh races
    with transaction.atomic():
        token_row = MicrosoftOAuthToken.objects.select_for_update().get(pk=token_row.pk)

        # Re-check after acquiring lock — another thread may have refreshed already
        if (
            token_row.cached_access_token
            and token_row.cached_access_token_expires_at
            and token_row.cached_access_token_expires_at > timezone.now() + timezone.timedelta(seconds=60)
        ):
            return token_row.cached_access_token

        # Decrypt refresh token
        try:
            refresh_token = fernet.decrypt(token_row.encrypted_refresh_token).decode()
        except Exception:
            raise MicrosoftOAuthRefreshFailed(
                "Failed to decrypt refresh token. Check MS_OAUTH_TOKEN_ENCRYPTION_KEY."
            )

        scopes = token_row.scopes.split()
        app = _get_msal_app()

        # Retry with exponential backoff for transient failures
        last_error = None
        delays = [1, 3, 9]
        for attempt, delay in enumerate(delays):
            result = app.acquire_token_by_refresh_token(refresh_token, scopes=scopes)

            if "access_token" in result:
                # Success — update stored tokens
                token_row.cached_access_token = result["access_token"]
                expires_in = result.get("expires_in", 3600)
                token_row.cached_access_token_expires_at = (
                    timezone.now() + timezone.timedelta(seconds=expires_in)
                )
                token_row.last_refreshed_at = timezone.now()

                # Handle refresh token rotation
                new_refresh_token = result.get("refresh_token")
                if new_refresh_token:
                    token_row.encrypted_refresh_token = fernet.encrypt(
                        new_refresh_token.encode()
                    )

                token_row.save()
                logger.info("OAuth access token refreshed successfully.")
                return token_row.cached_access_token

            error = result.get("error", "")
            error_desc = result.get("error_description", "")

            if error == "invalid_grant":
                raise MicrosoftOAuthRefreshFailed(
                    f"Refresh token is invalid or expired ({error_desc}). "
                    "Re-run 'python manage.py microsoft_oauth_setup' to re-authorize."
                )

            last_error = f"{error}: {error_desc}"
            logger.warning(
                "OAuth refresh attempt %d failed: %s. Retrying in %ds.",
                attempt + 1, last_error, delay,
            )
            time.sleep(delay)

        raise MicrosoftOAuthRefreshFailed(
            f"Failed to refresh access token after {len(delays)} attempts: {last_error}"
        )
