from .views import is_super_user


def user_permissions(request):
    """Add user permission flags to template context."""
    return {
        'is_super_user': is_super_user(request.user) if request.user.is_authenticated else False,
    }


def site_settings(request):
    """Expose the Super-User-editable SiteSettings to templates as ``site``."""
    from .site_settings import get_site_settings
    return {"site": getattr(request, "site_settings", None) or get_site_settings()}
