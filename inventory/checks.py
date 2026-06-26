"""Django system checks for the inventory app."""

from django.conf import settings
from django.core.checks import Warning, register


@register()
def check_oauth_token_exists(app_configs, **kwargs):
    """Warn at startup if MS_OAUTH_CLIENT_ID is set but no token row exists."""
    errors = []
    client_id = getattr(settings, "MS_OAUTH_CLIENT_ID", "")
    if client_id:
        from inventory.models import MicrosoftOAuthToken
        if not MicrosoftOAuthToken.objects.exists():
            errors.append(
                Warning(
                    "Microsoft OAuth is configured in env but no token has been captured. "
                    "Run 'python manage.py microsoft_oauth_setup' to authorize the app.",
                    id="inventory.W001",
                )
            )
    return errors
