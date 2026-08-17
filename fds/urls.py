from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import (
    FdsFeeStructureViewSet, FdsBatchViewSet, FdsEnquiryViewSet,
    FdsTrialViewSet, FdsStudentViewSet, FdsWeddingGroupViewSet,
    FdsAttendanceViewSet, FdsFeesCollectionViewSet, FdsStudentFeeAccountViewSet,
    FdsDashboardView, FdsTrainerListView
)

router = DefaultRouter()
router.register(r'fee-structures', FdsFeeStructureViewSet, basename='fds-fee-structures')
router.register(r'batches', FdsBatchViewSet, basename='fds-batches')
router.register(r'enquiries', FdsEnquiryViewSet, basename='fds-enquiries')
router.register(r'trials', FdsTrialViewSet, basename='fds-trials')
router.register(r'students', FdsStudentViewSet, basename='fds-students')
router.register(r'wedding-groups', FdsWeddingGroupViewSet, basename='fds-wedding-groups')
router.register(r'attendance', FdsAttendanceViewSet, basename='fds-attendance')
router.register(r'payments', FdsFeesCollectionViewSet, basename='fds-payments')
router.register(r'fee-accounts', FdsStudentFeeAccountViewSet, basename='fds-fee-accounts')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', FdsDashboardView.as_view(), name='fds-dashboard'),
    path('trainers/', FdsTrainerListView.as_view(), name='fds-trainers'),
]
