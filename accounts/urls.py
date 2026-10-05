# accounts/urls.py
from django.urls import path
from .views import (
    LoginAPIView,
    RefreshTokenAPIView,
    LogoutAPIView,
    CurrentUserAPIView, 
    DashboardStatsAPIView,
    ActivityLogListView,
    StaffListView,
    StaffDetailView,
    StaffCreateView,
    StaffUpdateView,
    EmployeeListAPI,
    StaffAssetTimelineView,
    AppPermissionListView,
    RoleListCreateView,
    RoleDetailView,
    UserProfileUpdateAPIView,
    ChangePasswordAPIView
)

urlpatterns = [
    path('login/', LoginAPIView.as_view(), name='login'),
    path('token/refresh/', RefreshTokenAPIView.as_view(), name='token_refresh'),
    path('logout/', LogoutAPIView.as_view(), name='logout'),
    path('user/me/', CurrentUserAPIView.as_view(), name='current_user'),
    path('user/me/update/', UserProfileUpdateAPIView.as_view(), name='user_profile_update'),
    path('user/me/change-password/', ChangePasswordAPIView.as_view(), name='change_password'),
    path('stats/', DashboardStatsAPIView.as_view(), name='dashboard_stats'),
    path('activities/', ActivityLogListView.as_view(), name='activity_log'),
    path('staff/', StaffListView.as_view(), name='staff_list'),
    path('staff/<int:pk>/', StaffDetailView.as_view(), name='staff_detail'),
    path('staff/create/', StaffCreateView.as_view(), name='staff_create'),
    path('staff/<int:pk>/update/', StaffUpdateView.as_view(), name='staff_update'),
    path('staff/<int:pk>/asset-timeline/', StaffAssetTimelineView.as_view(), name='staff_asset_timeline'),
    path('employees/', EmployeeListAPI.as_view()),
    path('permissions/', AppPermissionListView.as_view(), name='permission_list'),
    path('roles/', RoleListCreateView.as_view(), name='role_list_create'),
    path('roles/<int:pk>/', RoleDetailView.as_view(), name='role_detail'),
]
