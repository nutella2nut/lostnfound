from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    # Landing page
    path("", views.LandingPageView.as_view(), name="landing"),
    # Public listing & detail views
    path("browse/", views.ItemListView.as_view(), name="item_list"),
    path("primary-years/", views.PrimaryYearsListView.as_view(), name="primary_years_list"),
    path("students-lost-items/", views.StudentLostItemsListView.as_view(), name="student_lost_items_list"),
    path("items/<int:pk>/", views.ItemDetailView.as_view(), name="item_detail"),
    path("items/<int:pk>/claim/", views.ClaimItemView.as_view(), name="claim_item"),
    path("student-items/<int:pk>/", views.StudentLostItemDetailView.as_view(), name="student_lost_item_detail"),
    # Staff-only upload flow
    path("staff/items/upload/", views.ItemUploadView.as_view(), name="item_upload"),
    path("staff/items/analyze/", views.analyze_images_ajax, name="analyze_images_ajax"),
    path("staff/dashboard/", views.AdminDashboardView.as_view(), name="admin_dashboard"),
    # Super User approval flow
    path("staff/approval-queue/", views.ApprovalQueueView.as_view(), name="approval_queue"),
    path("staff/approve/<str:item_type>/<int:item_id>/", views.ApproveItemView.as_view(), name="approve_item"),
    path("staff/reject/<str:item_type>/<int:item_id>/", views.RejectItemView.as_view(), name="reject_item"),
]


