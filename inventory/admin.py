from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils import timezone
from datetime import timedelta

from .models import Item, ItemImage, StudentLostItem, StudentLostItemImage, UserProfile, Claim
from .views import is_super_user

User = get_user_model()

# Custom AdminSite that restricts access to Super Users only
class SuperUserOnlyAdminSite(admin.AdminSite):
    """Custom admin site that only allows Super Users to access."""
    
    def has_permission(self, request):
        """Only Super Users can access Django admin."""
        return (
            request.user and
            request.user.is_active and
            is_super_user(request.user)
        )

# Replace the default admin site with our custom one
admin.site = SuperUserOnlyAdminSite(name='admin')

# Using default Django admin - no customizations


class ItemImageInline(admin.TabularInline):
    model = ItemImage
    extra = 1


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "approval_status", "item_type", "claimed_info", "location_found", "date_found", "created_by", "created_at")
    list_filter = ("status", "approval_status", "item_type", "category", "location_found", "date_found", "created_at", "claimed_at")
    search_fields = ("title", "description", "location_found", "claimed_by_name")
    readonly_fields = ("created_at", "updated_at", "claimed_at", "claimed_notification")
    fieldsets = (
        ("Item Information", {
            "fields": ("title", "description", "category", "location_found", "date_found")
        }),
        ("Approval & Type", {
            "fields": ("approval_status", "item_type")
        }),
        ("Status", {
            "fields": ("status", "claimed_by_name", "claimed_at", "claimed_notification")
        }),
        ("Metadata", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    inlines = [ItemImageInline]
    
    def claimed_info(self, obj):
        """Display claimed information with notification styling."""
        if obj.status == Item.Status.CLAIMED and obj.claimed_by_name:
            # Check if claimed recently (within last 24 hours)
            if obj.claimed_at and obj.claimed_at > timezone.now() - timedelta(hours=24):
                return format_html(
                    '<span style="background: #fef3c7; color: #92400e; padding: 4px 12px; border-radius: 12px; font-weight: bold; font-size: 11px;">'
                    '⚠️ {} claimed - may arrive soon!</span>',
                    obj.claimed_by_name
                )
            else:
                return format_html(
                    '<span style="color: #059669;">✓ Claimed by {}</span>',
                    obj.claimed_by_name
                )
        elif obj.status == Item.Status.CLAIMED:
            return format_html('<span style="color: #059669;">✓ Claimed</span>')
        return "-"
    claimed_info.short_description = "Claimed By"
    
    def claimed_notification(self, obj):
        """Show notification message in detail view."""
        if obj.status == Item.Status.CLAIMED and obj.claimed_by_name:
            return format_html(
                '<div style="background: #fef3c7; border: 2px solid #fbbf24; border-radius: 8px; padding: 16px; margin-top: 12px;">'
                '<strong style="color: #92400e; font-size: 14px;">⚠️ NOTIFICATION:</strong><br>'
                '<span style="color: #78350f;">'
                '<strong>{}</strong> has claimed item "<strong>{}</strong>" on {}. '
                'They may come to the reception soon. Please be ready to verify and return the item.'
                '</span></div>',
                obj.claimed_by_name,
                obj.title,
                obj.claimed_at.strftime("%B %d, %Y at %I:%M %p") if obj.claimed_at else "recently"
            )
        return "-"
    claimed_notification.short_description = "Claim Notification"
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('created_by')
    
    def changelist_view(self, request, extra_context=None):
        """Add notification count to admin list view."""
        extra_context = extra_context or {}
        # Count recently claimed items (within 24 hours)
        recent_claims = Item.objects.filter(
            status=Item.Status.CLAIMED,
            claimed_at__gte=timezone.now() - timedelta(hours=24)
        ).count()
        if recent_claims > 0:
            extra_context['recent_claims_count'] = recent_claims
        return super().changelist_view(request, extra_context)


@admin.register(ItemImage)
class ItemImageAdmin(admin.ModelAdmin):
    list_display = ("item", "created_at")
    list_filter = ("created_at",)
    search_fields = ("item__title",)


class StudentLostItemImageInline(admin.TabularInline):
    model = StudentLostItemImage
    extra = 1


@admin.register(StudentLostItem)
class StudentLostItemAdmin(admin.ModelAdmin):
    list_display = ("title", "approval_status", "email_from", "submitted_at", "approved_by", "approved_at")
    list_filter = ("approval_status", "submitted_at", "approved_at")
    search_fields = ("title", "description", "email_from", "email_subject")
    readonly_fields = ("submitted_at", "email_subject", "email_from")
    fieldsets = (
        ("Item Information", {
            "fields": ("title", "description")
        }),
        ("Email Information", {
            "fields": ("email_subject", "email_from", "submitted_at"),
            "classes": ("collapse",)
        }),
        ("Approval", {
            "fields": ("approval_status", "approved_by", "approved_at")
        }),
    )
    inlines = [StudentLostItemImageInline]
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('approved_by')


@admin.register(StudentLostItemImage)
class StudentLostItemImageAdmin(admin.ModelAdmin):
    list_display = ("student_item", "created_at")
    list_filter = ("created_at",)
    search_fields = ("student_item__title",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "is_super_user", "user_is_staff")
    list_filter = ("is_super_user",)
    search_fields = ("user__username", "user__email")
    readonly_fields = ("user",)
    
    def user_is_staff(self, obj):
        return obj.user.is_staff
    user_is_staff.boolean = True
    user_is_staff.short_description = "Is Staff"
    
    fieldsets = (
        ("User", {
            "fields": ("user",)
        }),
        ("Lost & Found Permissions", {
            "fields": ("is_super_user",)
        }),
    )


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("item", "claimant_name", "claimed_at")
    list_filter = ("claimed_at",)
    search_fields = ("item__title", "claimant_name")
    readonly_fields = ("claimed_at",)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('item')


# Custom User Admin for Super Users to manage roles
class UserProfileInline(admin.StackedInline):
    """Inline admin for UserProfile to show is_super_user field."""
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Lost & Found Profile"
    fields = ("is_super_user",)
    fk_name = "user"


class CustomUserAdmin(BaseUserAdmin):
    """Custom User admin that allows Super Users to manage is_staff and is_super_user."""
    
    inlines = (UserProfileInline,)
    
    def get_readonly_fields(self, request, obj=None):
        """Make is_staff readonly for non-Super Users."""
        readonly = list(super().get_readonly_fields(request, obj))
        # Only Super Users can edit is_staff
        if not is_super_user(request.user):
            if "is_staff" not in readonly:
                readonly.append("is_staff")
        return readonly
    
    def get_fieldsets(self, request, obj=None):
        """Ensure is_staff is visible and editable for Super Users."""
        fieldsets = super().get_fieldsets(request, obj)
        
        # For Super Users, ensure is_staff is in the Permissions fieldset
        if is_super_user(request.user):
            fieldsets_list = list(fieldsets)
            for i, (name, fieldset_dict) in enumerate(fieldsets_list):
                if name == "Permissions":
                    # Ensure is_staff is in the fields
                    fields = list(fieldset_dict.get("fields", ()))
                    if "is_staff" not in fields:
                        fields.append("is_staff")
                    fieldsets_list[i] = (
                        name,
                        {
                            **fieldset_dict,
                            "fields": tuple(fields),
                        },
                    )
                    break
            return tuple(fieldsets_list)
        
        return fieldsets
    
    def get_inline_instances(self, request, obj=None):
        """Ensure UserProfile exists before inline formset is created."""
        if obj:
            # Ensure UserProfile exists for existing users
            UserProfile.objects.get_or_create(user=obj)
        return super().get_inline_instances(request, obj)
    
    def save_model(self, request, obj, form, change):
        """Save the user model."""
        super().save_model(request, obj, form, change)
        # Ensure UserProfile exists after saving (for new users)
        if not change:  # Only for new users
            UserProfile.objects.get_or_create(user=obj)
    
    def save_formset(self, request, form, formset, change):
        """Handle UserProfile inline saving - prevent duplicate creation."""
        if formset.model == UserProfile:
            # For UserProfile inline, ensure we're updating existing instance, not creating new
            instances = formset.save(commit=False)
            for instance in instances:
                if not instance.pk:
                    # If no pk, try to get existing UserProfile
                    try:
                        existing_profile = UserProfile.objects.get(user=form.instance)
                        # Update existing profile with form data
                        existing_profile.is_super_user = instance.is_super_user
                        existing_profile.save()
                    except UserProfile.DoesNotExist:
                        # If it doesn't exist, create it
                        instance.user = form.instance
                        instance.save()
                else:
                    # Update existing instance
                    instance.save()
            # Delete any marked for deletion
            for obj in formset.deleted_objects:
                obj.delete()
        else:
            # For other inlines, use default behavior
            super().save_formset(request, form, formset, change)

# Note: User admin registration is handled in apps.py ready() method
# to ensure proper order and avoid AlreadyRegistered errors


