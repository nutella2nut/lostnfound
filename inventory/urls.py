from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    # Landing page
    path("", views.LandingPageView.as_view(), name="landing"),
    # Public listing & detail views
    path("browse/", views.ItemListView.as_view(), name="item_list"),
    path("items/<int:pk>/", views.ItemDetailView.as_view(), name="item_detail"),
    path("items/<int:pk>/claim/", views.ClaimItemView.as_view(), name="claim_item"),
    # Staff-only upload flow
    path("staff/items/upload/", views.ItemUploadView.as_view(), name="item_upload"),
    path("staff/items/analyze/", views.analyze_images_ajax, name="analyze_images_ajax"),
    path("staff/dashboard/", views.AdminDashboardView.as_view(), name="admin_dashboard"),
]


