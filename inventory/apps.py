from django.apps import AppConfig
from django.contrib.auth import get_user_model


class InventoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inventory"

    def ready(self):
        import inventory.signals  # noqa: F401
        
        # Unregister default User admin and register custom one
        # Note: admin.site is already replaced with SuperUserOnlyAdminSite in admin.py
        from django.contrib import admin
        from inventory.admin import CustomUserAdmin
        
        User = get_user_model()
        if admin.site.is_registered(User):
            admin.site.unregister(User)
        admin.site.register(User, CustomUserAdmin)


