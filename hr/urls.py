from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LocationViewSet,
    AssetCategoryViewSet,
    BranchViewSet,
    PenaltyListCreateAPI, 
    PenaltyDetailAPI, 
    AttendanceDocumentAPI, 
    AttendanceDocumentDeleteAPI,
    StaffListAPI,
    StaffDetailAPI,
    CandidateListCreateAPI,
    CandidateDetailAPI,
    AssetListCreateAPI,
    AssetDetailAPI,
)

router = DefaultRouter()
router.register(r'locations', LocationViewSet, basename='location')
router.register(r'asset-categories', AssetCategoryViewSet, basename='asset-category')
router.register(r'hr-branches', BranchViewSet, basename='hr-branch')

urlpatterns = [
    path("", include(router.urls)),
    path("penalties/", PenaltyListCreateAPI.as_view(), name="penalty-list-create"),
    path("penalties/<int:pk>/", PenaltyDetailAPI.as_view(), name="penalty-detail"),
    path("attendance/", AttendanceDocumentAPI.as_view(), name="attendance-list-create"),
    path("attendance/<int:pk>/", AttendanceDocumentDeleteAPI.as_view(), name="attendance-detail"),
    path("staffs/", StaffListAPI.as_view(), name="staff-list"),
    path("staffs/<int:pk>/", StaffDetailAPI.as_view(), name="staff-detail"),
    path('candidates/', CandidateListCreateAPI.as_view(), name='candidate-list-create'),
    path('candidates/<int:pk>/', CandidateDetailAPI.as_view(), name='candidate-detail'),
    path('assets/', AssetListCreateAPI.as_view(), name='asset-list-create'),
    path('assets/<int:pk>/', AssetDetailAPI.as_view(), name='asset-detail'),
]