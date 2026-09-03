from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    GradeViewSet, CampusViewSet, AcademicPackageViewSet, AttendancePolicyViewSet,
    AcademicBatchViewSet, StudentViewSet, StudentBatchHistoryViewSet,
    GradeExamRecordViewSet, AttendanceSessionViewSet, AttendanceRecordViewSet,
    PromotionEventViewSet, DemotionEventViewSet,
    FlagTrainerView
)

router = DefaultRouter()
router.register(r'grades', GradeViewSet)
router.register(r'campuses', CampusViewSet)
router.register(r'packages', AcademicPackageViewSet)
router.register(r'attendance-policies', AttendancePolicyViewSet)
router.register(r'batches', AcademicBatchViewSet)
router.register(r'students', StudentViewSet)
router.register(r'student-history', StudentBatchHistoryViewSet)
router.register(r'exams', GradeExamRecordViewSet)
router.register(r'attendance-sessions', AttendanceSessionViewSet)
router.register(r'attendance-records', AttendanceRecordViewSet)
router.register(r'promotions', PromotionEventViewSet)
router.register(r'demotions', DemotionEventViewSet)

urlpatterns = [
    path('trainers/', FlagTrainerView.as_view(), name='flag-trainers'),
    path('', include(router.urls)),
]

