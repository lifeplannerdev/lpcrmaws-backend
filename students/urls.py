from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    emergency_reset_db, emergency_restore_data,
    GradeViewSet, CampusViewSet, AcademicPackageViewSet,
    AcademicBatchViewSet, GradeBatchViewSet, StudentViewSet, StudentBatchHistoryViewSet,
    ExamRecordViewSet, AttendanceSessionViewSet, AttendanceRecordViewSet,
    FlagTrainerView
)

router = DefaultRouter()
router.register(r'grades', GradeViewSet)
router.register(r'campuses', CampusViewSet)
router.register(r'packages', AcademicPackageViewSet)
router.register(r'batches', AcademicBatchViewSet)
router.register(r'grade-batches', GradeBatchViewSet)
router.register(r'students', StudentViewSet)
router.register(r'batch-history', StudentBatchHistoryViewSet)
router.register(r'exam-records', ExamRecordViewSet)
router.register(r'exams', ExamRecordViewSet, basename='exams-alias')
router.register(r'attendance-sessions', AttendanceSessionViewSet)
router.register(r'attendance-records', AttendanceRecordViewSet)
router.register(r'student-history', StudentBatchHistoryViewSet, basename='student-history-alias')

urlpatterns = [
    path('emergency-reset-db/', emergency_reset_db, name='emergency-reset-db'),
    path('emergency-restore-data/', emergency_restore_data, name='emergency-restore-data'),
    path('', include(router.urls)),
    path('trainers/', FlagTrainerView.as_view(), name='flag-trainers'),
]
