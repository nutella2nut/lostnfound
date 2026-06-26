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
    # Broadcast (§2)
    path("staff/broadcast/<str:kind>/<int:pk>/", views.BroadcastItemView.as_view(), name="broadcast_item"),
    path("staff/broadcasts/", views.BroadcastHistoryView.as_view(), name="broadcast_history"),
    # How to report (§3.4)
    path("how-to-report-lost/", views.HowToReportLostView.as_view(), name="how_to_report_lost"),
    # Magic Link My Reports (§4)
    path("my-reports/", views.MyReportsView.as_view(), name="my_reports"),
    path("my-reports/request-link/", views.RequestMagicLinkView.as_view(), name="request_magic_link"),
    path("my-reports/sign-in/<str:token>/", views.MagicLinkSignInView.as_view(), name="magic_link_signin"),
    path("my-reports/sign-out/", views.MyReportsSignOutView.as_view(), name="my_reports_signout"),
    # Staff User Management (§6)
    path("staff/users/", views.UserManagementListView.as_view(), name="user_management_list"),
    path("staff/users/new/", views.UserManagementCreateView.as_view(), name="user_management_create"),
    path("staff/users/role-changes/", views.UserRoleChangeHistoryView.as_view(), name="user_role_change_history"),
    path("staff/users/<int:pk>/", views.UserManagementDetailView.as_view(), name="user_management_detail"),
    path("staff/users/<int:pk>/edit/", views.UserManagementEditView.as_view(), name="user_management_edit"),
    path("staff/users/<int:pk>/set-password/", views.UserManagementSetPasswordView.as_view(), name="user_management_set_password"),
    path("staff/users/<int:pk>/delete/", views.UserManagementDeleteView.as_view(), name="user_management_delete"),
]


