from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from datetime import timedelta

from .models import Item, ItemImage


class ItemImageInline(admin.TabularInline):
    model = ItemImage
    extra = 1


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "claimed_info", "location_found", "date_found", "created_by", "created_at")
    list_filter = ("status", "location_found", "date_found", "created_at", "claimed_at")
    search_fields = ("title", "description", "location_found", "claimed_by_name")
    readonly_fields = ("created_at", "updated_at", "claimed_at", "claimed_notification")
    fieldsets = (
        ("Item Information", {
            "fields": ("title", "description", "category", "location_found", "date_found")
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


