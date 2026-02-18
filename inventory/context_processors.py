from .views import is_super_user


def user_permissions(request):
    """Add user permission flags to template context."""
    return {
        'is_super_user': is_super_user(request.user) if request.user.is_authenticated else False,
    }

