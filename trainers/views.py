from accounts.permissions import has_dynamic_permission
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.dateparse import parse_date
from accounts.models import ActivityLog
import csv

from .models import (
    Trainer, Student, Attendance, AcademicBatch, AcademicPackage, Branch,
    ExamResult, ProcessingStudent, ProcessingDynamicField, ProcessingStudentDocument,
    StudentTimeline, CourseLevel, CourseModule, StudentModuleProgress,
    StudentPackageEnrollment, StudentAcademicPlacement,
)
from .serializers import (
    TrainerSerializer, 
    StudentSerializer, 
    AttendanceSerializer,
    TrainerUserSerializer,
    AcademicBatchSerializer,
    StudentTimelineSerializer,
    BranchSerializer,
    ExamResultSerializer,
    ProcessingStudentSerializer,
    ProcessingDynamicFieldSerializer,
    ProcessingStudentDocumentSerializer,
    CourseLevelSerializer,
    CourseModuleSerializer,
    StudentModuleProgressSerializer,
    AcademicPackageSerializer,
    StudentPackageEnrollmentSerializer,
    StudentAcademicPlacementSerializer
)
from .permissions import IsTrainerOwnStudent
from .academic_services import (
    AcademicWorkflowError,
    finalize_batch_level,
    placement_for_attendance,
    transfer_failed_student,
    upgrade_academic_package,
)

User = get_user_model()


def _has_perm(user, perm):
    return user.is_authenticated and has_dynamic_permission(user, perm)


def _parse_effective_date(value):
    if not value:
        return timezone.localdate()
    parsed = parse_date(str(value))
    if not parsed:
        raise AcademicWorkflowError('effective_date must use YYYY-MM-DD format.')
    return parsed


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100



class TrainerListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Trainer.objects.select_related('user', 'branch')
        branch_id = request.GET.get('branch_id')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = TrainerSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = TrainerSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TrainerDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        trainer = get_object_or_404(Trainer, pk=pk)
        return Response(TrainerSerializer(trainer).data)

    def put(self, request, pk):
        trainer = get_object_or_404(Trainer, pk=pk)
        serializer = TrainerSerializer(trainer, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        trainer = get_object_or_404(Trainer, pk=pk)
        trainer.delete()
        return Response(status=204)


class TrainerUserListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        trainers = User.objects.filter(
            Q(db_roles__name__iexact='TRAINER') | Q(trainer_profile__isnull=False),
            is_active=True
        ).distinct()
        
        search = request.GET.get('search')
        if search:
            trainers = trainers.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(username__icontains=search) |
                Q(email__icontains=search)
            )
        
        serializer = TrainerUserSerializer(trainers.order_by('first_name'), many=True)
        return Response({
            'count': trainers.count(),
            'results': serializer.data
        })


class StudentListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'manage_students') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        qs = Student.objects.select_related(
            'trainer', 'trainer__user', 'academic_batch', 'branch', 'current_level'
        )
        qs = qs.select_related('fee_account')

        if hasattr(request.user, 'trainer_profile'):
            qs = qs.filter(trainer=request.user.trainer_profile)

        status_filter = request.GET.get('status')
        batch_filter = request.GET.get('batch')
        academic_batch = request.GET.get('academic_batch')
        level_id = request.GET.get('level_id')
        trainer_filter = request.GET.get('trainer')
        branch_id = request.GET.get('branch_id')
        search = request.GET.get('search')

        if status_filter:
            qs = qs.filter(status=status_filter)
        if batch_filter:
            qs = qs.filter(batch=batch_filter)
        if academic_batch:
            qs = qs.filter(academic_batch_id=academic_batch)
        if level_id:
            qs = qs.filter(current_level_id=level_id)
        if trainer_filter:
            qs = qs.filter(trainer_id=trainer_filter)
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone_number__icontains=search)
            )

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = StudentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


    def post(self, request):
        if not _has_perm(request.user, 'students:edit_any'):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        serializer = StudentSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class AcademicBatchListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = AcademicBatch.objects.select_related('starting_level', 'branch')
        if hasattr(request.user, 'trainer_profile'):
            qs = qs.filter(branch=request.user.trainer_profile.branch)
        academic_year = request.GET.get('academic_year')
        if academic_year:
            qs = qs.filter(academic_year=academic_year)
        serializer = AcademicBatchSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not (_has_perm(request.user, 'students:edit_any') or _has_perm(request.user, 'manage_students') or request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        serializer = AcademicBatchSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class AcademicBatchDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(AcademicBatch.objects.select_related('starting_level', 'branch'), pk=pk)

    def get(self, request, pk):
        batch = self.get_object(pk)
        if hasattr(request.user, 'trainer_profile') and batch.branch_id != request.user.trainer_profile.branch_id:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return Response(AcademicBatchSerializer(batch).data)

    def put(self, request, pk):
        if not (_has_perm(request.user, 'students:edit_any') or _has_perm(request.user, 'manage_students') or request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        batch = self.get_object(pk)
        serializer = AcademicBatchSerializer(batch, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        if not (_has_perm(request.user, 'students:edit_any') or _has_perm(request.user, 'manage_students') or request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        batch = self.get_object(pk)
        batch.delete()
        return Response({"message": "Batch deleted"}, status=status.HTTP_204_NO_CONTENT)


class AcademicPackageListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        packages = AcademicPackage.objects.select_related('minimum_level', 'maximum_level')
        if request.GET.get('active_only', '').lower() in ('1', 'true', 'yes'):
            packages = packages.filter(is_active=True)
        return Response(AcademicPackageSerializer(packages, many=True).data)

    def post(self, request):
        if not (_has_perm(request.user, 'students:edit_any') or _has_perm(request.user, 'manage_students') or request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        serializer = AcademicPackageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AcademicPackageDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(
            AcademicPackage.objects.select_related('minimum_level', 'maximum_level'), pk=pk
        )

    def get(self, request, pk):
        return Response(AcademicPackageSerializer(self.get_object(pk)).data)

    def put(self, request, pk):
        if not (_has_perm(request.user, 'students:edit_any') or _has_perm(request.user, 'manage_students') or request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        package = self.get_object(pk)
        serializer = AcademicPackageSerializer(package, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if not (_has_perm(request.user, 'students:edit_any') or _has_perm(request.user, 'manage_students') or request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        package = self.get_object(pk)
        try:
            package.delete()
        except ProtectedError:
            return Response(
                {"detail": "Packages assigned to students cannot be deleted; deactivate them instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class StudentDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, IsTrainerOwnStudent]

    def get_object(self, request, pk):
        qs = Student.objects.select_related('trainer', 'trainer__user', 'fee_account')
        if hasattr(request.user, 'trainer_profile'):
            qs = qs.filter(trainer=request.user.trainer_profile)
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'manage_students') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        student = self.get_object(request, pk)
        return Response(StudentSerializer(student).data)

    def put(self, request, pk):
        if not (_has_perm(request.user, 'students:edit_any') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        student = self.get_object(request, pk)
        
        old_status = student.status
        old_batch = student.academic_batch_id
        
        serializer = StudentSerializer(student, data=request.data, context={'request': request})
        if serializer.is_valid():
            student = serializer.save()
            
            # Log changes
            if old_status != student.status:
                StudentTimeline.objects.create(
                    student=student,
                    event_type='STATUS_CHANGE',
                    description=f"Status changed from {old_status} to {student.status}",
                    created_by=request.user
                )
            if old_batch != student.academic_batch_id:
                old_acad = AcademicBatch.objects.filter(id=old_batch).first()
                old_name = old_acad.name if old_acad else 'None'
                new_name = student.academic_batch.name if student.academic_batch else 'None'
                StudentTimeline.objects.create(
                    student=student,
                    event_type='BATCH_ASSIGNMENT',
                    description=f"Academic Batch changed from {old_name} to {new_name}",
                    created_by=request.user
                )
                
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        if not _has_perm(request.user, 'students:edit_any'):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        student = self.get_object(request, pk)
        student.delete()
        return Response(
            {"message": "Student deleted successfully"},
            status=status.HTTP_204_NO_CONTENT
        )



class AttendanceListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'attendance:mark') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        qs = Attendance.objects.select_related(
            'student', 'trainer', 'trainer__user', 'placement',
            'placement__academic_batch', 'placement__level'
        ).order_by('-date')
        if hasattr(request.user, 'trainer_profile'):
            qs = qs.filter(trainer=request.user.trainer_profile)

        student_id = request.GET.get('student_id') or request.GET.get('student')
        academic_batch_id = request.GET.get('academic_batch_id')
        level_id = request.GET.get('level_id')
        placement_id = request.GET.get('placement_id')
        branch_id = request.GET.get('branch_id')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        if student_id:
            qs = qs.filter(student_id=student_id)
        if academic_batch_id:
            qs = qs.filter(placement__academic_batch_id=academic_batch_id)
        if level_id:
            qs = qs.filter(placement__level_id=level_id)
        if placement_id:
            qs = qs.filter(placement_id=placement_id)
        if branch_id:
            qs = qs.filter(placement__academic_batch__branch_id=branch_id)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AttendanceSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):  
        if not _has_perm(request.user, 'attendance:mark'):
            return Response(
                {"detail": "Only trainers can mark attendance"},
                status=403
            )

        trainer = request.user.trainer_profile
        student_id = request.data.get('student')

        student = Student.objects.filter(
            id=student_id, trainer=trainer
        ).first()
        
        if not student:
            return Response(
                {"detail": "You can mark attendance only for your students"},
                status=403
            )

        from fees.models import FeePolicy
        policy = FeePolicy.objects.filter(company=student.company).first()
        
        has_fee_account = hasattr(student, 'fee_account') and student.fee_account is not None
        
        is_flexible = getattr(student, 'fee_attendance_policy', 'STRICT') == 'FLEXIBLE'
        
        if not is_flexible and policy and policy.block_without_fee_account and not has_fee_account:
            return Response(
                {"detail": "Attendance blocked: Student has no fee structure assigned."},
                status=403
            )

        serializer = AttendanceSerializer(data=request.data)
        if serializer.is_valid():
            approval_status = 'APPROVED'
            
            pending_enabled = policy.pending_if_overdue if policy else True
            if not is_flexible and pending_enabled:
                # If marked PRESENT, check for overdue fees
                if serializer.validated_data.get('status', 'PRESENT') == 'PRESENT':
                    if has_fee_account and getattr(student.fee_account, 'is_overdue', False):
                        approval_status = 'PENDING_FEE_APPROVAL'

            try:
                placement = placement_for_attendance(student, serializer.validated_data['date'])
            except AcademicWorkflowError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            serializer.save(
                trainer=trainer,
                placement=placement,
                approval_status=approval_status,
            )
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
        

class AttendanceDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'attendance:mark') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        records = Attendance.objects.select_related(
            'student', 'trainer', 'trainer__user', 'placement',
            'placement__academic_batch', 'placement__level'
        ).order_by('-date')

        if hasattr(request.user, 'trainer_profile'):
            records = records.filter(trainer=request.user.trainer_profile)

        student_id = request.GET.get('student')
        trainer_id = request.GET.get('trainer')
        branch_id = request.GET.get('branch_id')
        date = request.GET.get('date')
        approval_status = request.GET.get('approval_status')
        academic_batch_id = request.GET.get('academic_batch_id')
        level_id = request.GET.get('level_id')
        placement_id = request.GET.get('placement_id')
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')

        if student_id:
            records = records.filter(student_id=student_id)
        if trainer_id:
            records = records.filter(trainer_id=trainer_id)
        if branch_id:
            records = records.filter(student__branch_id=branch_id)
        if date:
            records = records.filter(date=date)
        if approval_status:
            records = records.filter(approval_status=approval_status)
        if academic_batch_id:
            records = records.filter(placement__academic_batch_id=academic_batch_id)
        if level_id:
            records = records.filter(placement__level_id=level_id)
        if placement_id:
            records = records.filter(placement_id=placement_id)
        if date_from:
            records = records.filter(date__gte=date_from)
        if date_to:
            records = records.filter(date__lte=date_to)

        
        if date:
            serializer = AttendanceSerializer(records, many=True)
            return Response({
                'count': records.count(),
                'results': serializer.data
            })
        
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(records, request)
        serializer = AttendanceSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

class QuickMarkAttendanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _has_perm(request.user, 'attendance:mark'):
            return Response({"error": "Unauthorized"}, status=403)

        date = request.data.get('date')
        records = request.data.get('records', [])

        if not date or not records:
            return Response({"error": "date and records required"}, status=400)

        saved = []
        errors = []
        
        from fees.models import FeePolicy
        company = getattr(request.user, 'company', 'LP')
        policy = FeePolicy.objects.filter(company=company).first()

        for r in records:
            try:
                student_id = r.get('student')
                student = Student.objects.filter(id=student_id).exclude(status__in=['COMPLETED', 'DROPPED']).first()
                
                if not student:
                    continue

                # Ensure only the assigned trainer or an authorized role can mark attendance
                if hasattr(request.user, 'trainer_profile') and student.trainer != request.user.trainer_profile:
                    continue

                trainer_to_assign = student.trainer

                has_fee_account = hasattr(student, 'fee_account') and student.fee_account is not None
                
                is_flexible = getattr(student, 'fee_attendance_policy', 'STRICT') == 'FLEXIBLE'
                
                if not is_flexible and policy and policy.block_without_fee_account and not has_fee_account:
                    errors.append({
                        'student_id': r.get('student'),
                        'error': 'Attendance blocked: Student has no fee structure assigned.'
                    })
                    continue

                approval_status = 'APPROVED'
                pending_enabled = policy.pending_if_overdue if policy else True
                if not is_flexible and pending_enabled:
                    if r.get('status', 'PRESENT') == 'PRESENT':
                        if has_fee_account and getattr(student.fee_account, 'is_overdue', False):
                            approval_status = 'PENDING_FEE_APPROVAL'

                try:
                    placement = placement_for_attendance(student, date)
                except AcademicWorkflowError as exc:
                    errors.append({'student_id': student_id, 'error': str(exc)})
                    continue

                obj, created = Attendance.objects.update_or_create(
                    placement=placement,
                    date=date,
                    defaults={
                        'student': student,
                        'trainer': trainer_to_assign,
                        'status': r.get('status', 'PRESENT'),
                        'approval_status': approval_status
                    }
                )
                saved.append(obj)
                
            except Exception as e:
                errors.append({
                    'student_id': r.get('student'),
                    'error': str(e)
                })
                print(f"Error saving attendance for student {r.get('student')}: {str(e)}")
                continue

        if not saved:
            return Response({
                'error': 'No attendance records were saved',
                'details': errors
            }, status=400)

        return Response(
            AttendanceSerializer(saved, many=True).data,
            status=201
        )


class AttendanceRecordsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'attendance:mark') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        qs = Attendance.objects.select_related(
            'placement', 'placement__academic_batch', 'placement__level', 'trainer', 'trainer__user'
        ).filter(student_id=student_id).order_by('-date')

        placement_id = request.GET.get('placement_id')
        if placement_id:
            qs = qs.filter(placement_id=placement_id)

        if hasattr(request.user, 'trainer_profile'):
            qs = qs.filter(trainer=request.user.trainer_profile)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AttendanceSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class ExportStudentAttendanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'attendance:mark') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        qs = Attendance.objects.select_related(
            'placement', 'placement__academic_batch', 'placement__level', 'trainer', 'trainer__user'
        ).filter(student_id=student_id).order_by('date')

        if hasattr(request.user, 'trainer_profile'):
            qs = qs.filter(trainer=request.user.trainer_profile)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="student_{student_id}_attendance.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(['Date', 'Academic Batch', 'Grade', 'Trainer', 'Status'])

        for r in qs:
            writer.writerow([
                r.date,
                r.placement.academic_batch.name,
                r.placement.level.name,
                r.trainer.user.get_full_name(),
                r.status
            ])

        return response


class AttendanceApproveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not _has_perm(request.user, 'fees:manage'):
            return Response({"detail": "Only accountants can approve attendance"}, status=403)
        
        attendance = get_object_or_404(Attendance, pk=pk)
        
        if attendance.approval_status != 'PENDING_FEE_APPROVAL':
            return Response({"detail": "Attendance is not pending approval"}, status=400)

        attendance.approval_status = 'APPROVED'
        attendance.approved_by = request.user
        attendance.approval_notes = request.data.get('approval_notes', '')
        attendance.save()

        return Response(AttendanceSerializer(attendance).data)

class AttendanceStudentsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'attendance:mark') or hasattr(request.user, 'trainer_profile')):
            return Response({"error": "Only authorized users can access this endpoint"}, status=403)
        students = Student.objects.filter(
            academic_placements__status='ACTIVE'
        ).exclude(
            status__in=['COMPLETED', 'DROPPED', 'AWAITING_REPEAT_TRANSFER', 'AWAITING_PACKAGE_UPGRADE']
        ).select_related('trainer', 'trainer__user', 'academic_batch', 'current_level').order_by('name').distinct()

        if hasattr(request.user, 'trainer_profile'):
            students = students.filter(trainer=request.user.trainer_profile)
        
        batch = request.GET.get('batch')
        student_class = request.GET.get('student_class')
        trainer_id = request.GET.get('trainer')
        branch_id = request.GET.get('branch_id')
        location = request.GET.get('location')
        academic_batch_id = request.GET.get('academic_batch_id')
        level_id = request.GET.get('level_id')
        
        if batch:
            students = students.filter(batch=batch)
        if student_class:
            students = students.filter(student_class=student_class)
        if trainer_id and not hasattr(request.user, 'trainer_profile'):
            students = students.filter(trainer_id=trainer_id)
        if branch_id:
            students = students.filter(branch_id=branch_id)
        if location:
            students = students.filter(trainer__user__location=location)
        if academic_batch_id:
            students = students.filter(academic_placements__academic_batch_id=academic_batch_id)
        if level_id:
            students = students.filter(academic_placements__level_id=level_id)

        serializer = StudentSerializer(students, many=True)
        return Response({
            'count': students.count(),
            'results': serializer.data
        })


class AttendanceReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'attendance:mark') or hasattr(request.user, 'trainer_profile')):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        records = Attendance.objects.select_related(
            'student', 'placement__academic_batch', 'placement__level'
        )
        if hasattr(request.user, 'trainer_profile'):
            records = records.filter(trainer=request.user.trainer_profile)

        filters = {
            'academic_batch_id': 'placement__academic_batch_id',
            'level_id': 'placement__level_id',
            'student_id': 'student_id',
            'branch_id': 'placement__academic_batch__branch_id',
        }
        for query_key, lookup in filters.items():
            value = request.GET.get(query_key)
            if value:
                records = records.filter(**{lookup: value})
        if request.GET.get('date_from'):
            records = records.filter(date__gte=request.GET['date_from'])
        if request.GET.get('date_to'):
            records = records.filter(date__lte=request.GET['date_to'])

        group_by = request.GET.get('group_by', 'academic_batch')
        group_fields = {
            'academic_batch': ['placement__academic_batch_id', 'placement__academic_batch__name'],
            'grade': ['placement__level_id', 'placement__level__name'],
            'student': ['student_id', 'student__name'],
        }.get(group_by)
        if not group_fields:
            return Response({'detail': 'group_by must be academic_batch, grade, or student.'}, status=status.HTTP_400_BAD_REQUEST)

        summary = records.values(*group_fields).annotate(
            total=Count('id'),
            present=Count('id', filter=Q(status='PRESENT')),
            absent=Count('id', filter=Q(status='ABSENT')),
            no_session=Count('id', filter=Q(status='NO_SESSION')),
        ).order_by(*group_fields)
        return Response({'group_by': group_by, 'results': list(summary)})



class StudentStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Student.objects.all()
            
        if hasattr(request.user, 'trainer_profile'):
            qs = qs.filter(trainer=request.user.trainer_profile)
        
        stats = {
            "total": qs.count(),
            "ACTIVE": 0,
            "COMPLETED": 0,
            "PAUSED": 0,
            "DROPPED": 0,
        }

        for item in qs.values('status').annotate(c=Count('id')):
            stats[item['status']] = item['c']

        stats["PAUSED_DROPPED"] = stats["PAUSED"] + stats["DROPPED"]
        return Response(stats)


class BranchListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Branch.objects.all()
        serializer = BranchSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = BranchSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class BranchDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        branch = get_object_or_404(Branch, pk=pk)
        serializer = BranchSerializer(branch)
        return Response(serializer.data)

    def put(self, request, pk):
        branch = get_object_or_404(Branch, pk=pk)
        serializer = BranchSerializer(branch, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        branch = get_object_or_404(Branch, pk=pk)
        branch.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExamResultListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'manage_students') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        qs = ExamResult.objects.select_related(
            'student', 'academic_batch', 'placement', 'placement__level'
        )
        if hasattr(request.user, 'trainer_profile'):
            qs = qs.filter(student__trainer=request.user.trainer_profile)
        
        student_id = request.GET.get('student_id')
        academic_batch_id = request.GET.get('academic_batch_id')
        exam_type = request.GET.get('exam_type')
        level_id = request.GET.get('level_id')
        placement_id = request.GET.get('placement_id')

        if student_id:
            qs = qs.filter(student_id=student_id)
        if academic_batch_id:
            qs = qs.filter(academic_batch_id=academic_batch_id)
        if exam_type:
            qs = qs.filter(exam_type=exam_type.upper())
        if level_id:
            qs = qs.filter(placement__level_id=level_id)
        if placement_id:
            qs = qs.filter(placement_id=placement_id)

        serializer = ExamResultSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not (_has_perm(request.user, 'students:edit_any') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        serializer = ExamResultSerializer(data=request.data)
        if serializer.is_valid():
            placement = serializer.validated_data['placement']
            if hasattr(request.user, 'trainer_profile') and placement.student.trainer != request.user.trainer_profile:
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ExamResultDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'manage_students') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        result = get_object_or_404(ExamResult.objects.select_related('student__trainer', 'placement__level'), pk=pk)
        if hasattr(request.user, 'trainer_profile') and result.student.trainer != request.user.trainer_profile:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        serializer = ExamResultSerializer(result)
        return Response(serializer.data)

    def put(self, request, pk):
        if not (_has_perm(request.user, 'students:edit_any') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        result = get_object_or_404(ExamResult.objects.select_related('student__trainer'), pk=pk)
        if result.processed_at:
            return Response({"detail": "Finalized exam results cannot be edited."}, status=status.HTTP_400_BAD_REQUEST)
        if hasattr(request.user, 'trainer_profile') and result.student.trainer != request.user.trainer_profile:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        serializer = ExamResultSerializer(result, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        if not _has_perm(request.user, 'students:edit_any'):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        result = get_object_or_404(ExamResult, pk=pk)
        if result.processed_at:
            return Response({"detail": "Finalized exam results cannot be deleted."}, status=status.HTTP_400_BAD_REQUEST)
        result.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProcessingStudentActivityLogAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        can_read_any = _has_perm(request.user, 'processing_students:read_any')
        can_read_own = _has_perm(request.user, 'processing_students:read_own')
        
        if not (can_read_any or can_read_own):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            
        student = get_object_or_404(ProcessingStudent, pk=pk)
        
        if not can_read_any and can_read_own and student.assigned_to != request.user:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        logs = ActivityLog.objects.filter(
            entity_type='ProcessingStudent',
            entity_id=student.id
        ).order_by('-created_at')
        
        data = []
        for log in logs:
            data.append({
                "id": log.id,
                "action": log.get_action_display(),
                "description": log.description,
                "created_at": log.created_at,
                "user": log.user.username if log.user else "System"
            })
            
        return Response(data)

class ProcessingStudentNoteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        can_edit_any = _has_perm(request.user, 'processing_students:edit_any')
        can_edit_own = _has_perm(request.user, 'processing_students:edit_own')
        
        student = get_object_or_404(ProcessingStudent, pk=pk)
        
        if not (can_edit_any or (can_edit_own and student.assigned_to == request.user)):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        note = request.data.get('note')
        if not note:
            return Response({"detail": "Note is required"}, status=status.HTTP_400_BAD_REQUEST)

        ActivityLog.objects.create(
            user=request.user,
            action='PROCESSING_STUDENT_NOTE',
            entity_type='ProcessingStudent',
            entity_id=student.id,
            entity_name=student.name,
            description=note
        )
        return Response({"detail": "Note added successfully"}, status=status.HTTP_201_CREATED)

class ProcessingStudentDocumentListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    from rest_framework.parsers import MultiPartParser, FormParser
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, pk):
        can_read_any = _has_perm(request.user, 'processing_students:read_any')
        can_read_own = _has_perm(request.user, 'processing_students:read_own')
        
        student = get_object_or_404(ProcessingStudent, pk=pk)
        if not can_read_any and can_read_own and student.assigned_to != request.user:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            
        docs = student.documents.all()
        return Response(ProcessingStudentDocumentSerializer(docs, many=True).data)

    def post(self, request, pk):
        can_edit_any = _has_perm(request.user, 'processing_students:edit_any')
        can_edit_own = _has_perm(request.user, 'processing_students:edit_own')
        
        student = get_object_or_404(ProcessingStudent, pk=pk)
        if not (can_edit_any or (can_edit_own and student.assigned_to == request.user)):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            
        data = request.data.copy()
        data['student'] = student.id
        
        serializer = ProcessingStudentDocumentSerializer(data=data)
        if serializer.is_valid():
            serializer.save(uploaded_by=request.user)
            ActivityLog.objects.create(
                user=request.user,
                action='PROCESSING_STUDENT_UPDATED',
                entity_type='ProcessingStudent',
                entity_id=student.id,
                entity_name=student.name,
                description=f"Document uploaded: {serializer.validated_data.get('title')}"
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProcessingStudentDocumentDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        doc = get_object_or_404(ProcessingStudentDocument, pk=pk)
        student = doc.student
        
        can_edit_any = _has_perm(request.user, 'processing_students:edit_any')
        can_edit_own = _has_perm(request.user, 'processing_students:edit_own')
        
        if not (can_edit_any or (can_edit_own and student.assigned_to == request.user)):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            
        doc_title = doc.title
        doc.delete()
        
        ActivityLog.objects.create(
            user=request.user,
            action='PROCESSING_STUDENT_UPDATED',
            entity_type='ProcessingStudent',
            entity_id=student.id,
            entity_name=student.name,
            description=f"Document deleted: {doc_title}"
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

class ProcessingDynamicFieldListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (_has_perm(request.user, 'processing_students:read_any') or _has_perm(request.user, 'processing_students:read_own')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            
        qs = ProcessingDynamicField.objects.filter(is_active=True).order_by('order')
        serializer = ProcessingDynamicFieldSerializer(qs, many=True)
        return Response(serializer.data)


class ProcessingStudentListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        can_read_any = _has_perm(request.user, 'processing_students:read_any')
        can_read_own = _has_perm(request.user, 'processing_students:read_own')
        
        if not (can_read_any or can_read_own):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        qs = ProcessingStudent.objects.select_related('assigned_to')

        if not can_read_any and can_read_own:
            qs = qs.filter(assigned_to=request.user)

        category_filter = request.GET.get('category')
        if category_filter:
            qs = qs.filter(category=category_filter)

        search = request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(mobile_number__icontains=search) |
                Q(email__icontains=search)
            )

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = ProcessingStudentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        if not (_has_perm(request.user, 'processing_students:edit_any') or _has_perm(request.user, 'processing_students:edit_own')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        data = request.data.copy()
        
        # If user can only edit own, enforce assignment
        if _has_perm(request.user, 'processing_students:edit_own') and not _has_perm(request.user, 'processing_students:edit_any'):
            data['assigned_to'] = request.user.id

        serializer = ProcessingStudentSerializer(data=data)
        if serializer.is_valid():
            student = serializer.save()
            ActivityLog.objects.create(
                user=request.user,
                action='PROCESSING_STUDENT_CREATED',
                entity_type='ProcessingStudent',
                entity_id=student.id,
                entity_name=student.name,
                description=f"Processing Student {student.name} was created."
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProcessingStudentDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        qs = ProcessingStudent.objects.select_related('assigned_to')
        can_read_any = _has_perm(request.user, 'processing_students:read_any')
        can_read_own = _has_perm(request.user, 'processing_students:read_own')
        
        if not can_read_any and can_read_own:
            qs = qs.filter(assigned_to=request.user)
            
        return get_object_or_404(qs, pk=pk)

    def get(self, request, pk):
        if not (_has_perm(request.user, 'processing_students:read_any') or _has_perm(request.user, 'processing_students:read_own')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        
        student = self.get_object(request, pk)
        return Response(ProcessingStudentSerializer(student).data)

    def put(self, request, pk):
        return self.patch(request, pk)

    def patch(self, request, pk):
        student = self.get_object(request, pk)
        
        can_edit_any = _has_perm(request.user, 'processing_students:edit_any')
        can_edit_own = _has_perm(request.user, 'processing_students:edit_own') and student.assigned_to == request.user
        
        if not (can_edit_any or can_edit_own):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        serializer = ProcessingStudentSerializer(student, data=request.data, partial=True)
        if serializer.is_valid():
            changes_list = []
            for field, new_val in serializer.validated_data.items():
                if field == 'dynamic_data':
                    old_dict = getattr(student, 'dynamic_data', {}) or {}
                    new_dict = new_val or {}
                    for k, v in new_dict.items():
                        old_v = old_dict.get(k, '')
                        if str(old_v) != str(v):
                            changes_list.append(f"{k}: '{old_v}' -> '{v}'")
                else:
                    old_val = getattr(student, field, '')
                    if old_val is None: old_val = ''
                    if str(old_val) != str(new_val):
                        changes_list.append(f"{field}: '{old_val}' -> '{new_val}'")

            changes_desc = ", ".join(changes_list) if changes_list else "no visible changes"
            
            serializer.save()
            
            if changes_list:
                ActivityLog.objects.create(
                    user=request.user,
                    action='PROCESSING_STUDENT_UPDATED',
                    entity_type='ProcessingStudent',
                    entity_id=student.id,
                    entity_name=student.name,
                    description=f"Processing Student updated: {changes_desc}"
                )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        student = self.get_object(request, pk)
        
        can_edit_any = _has_perm(request.user, 'processing_students:edit_any')
        can_edit_own = _has_perm(request.user, 'processing_students:edit_own') and student.assigned_to == request.user
        
        if not (can_edit_any or can_edit_own):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            
        student_name = student.name
        student_id = student.id
        student.delete()
        
        ActivityLog.objects.create(
            user=request.user,
            action='PROCESSING_STUDENT_DELETED',
            entity_type='ProcessingStudent',
            entity_id=student_id,
            entity_name=student_name,
            description=f"Processing Student {student_name} was deleted."
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class StudentTimelineAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'manage_students') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            
        student = get_object_or_404(Student, pk=pk)
        
        # If trainer, ensure it's their student
        if hasattr(request.user, 'trainer_profile') and student.trainer != request.user.trainer_profile:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        timeline = student.timeline.all()
        serializer = StudentTimelineSerializer(timeline, many=True)
        return Response(serializer.data)


class StudentAcademicHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'manage_students') or hasattr(request.user, 'trainer_profile')):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        student = get_object_or_404(Student.objects.select_related('trainer', 'trainer__user'), pk=pk)
        if hasattr(request.user, 'trainer_profile') and student.trainer != request.user.trainer_profile:
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        package_enrollments = StudentPackageEnrollment.objects.select_related(
            'package', 'package__minimum_level', 'package__maximum_level'
        ).filter(student=student)
        placements = StudentAcademicPlacement.objects.select_related(
            'academic_batch', 'academic_batch__branch', 'level',
            'package_enrollment__package'
        ).filter(student=student).order_by('-entered_on', '-id')

        placement_data = []
        for placement in placements:
            serialized = StudentAcademicPlacementSerializer(placement).data
            records = Attendance.objects.select_related(
                'trainer', 'trainer__user', 'placement__academic_batch', 'placement__level'
            ).filter(placement=placement).order_by('-date', '-id')
            serialized['attendance_records'] = AttendanceSerializer(records, many=True).data
            placement_data.append(serialized)

        return Response({
            'student_id': student.id,
            'package_enrollments': StudentPackageEnrollmentSerializer(package_enrollments, many=True).data,
            'placements': placement_data,
        })


class StudentPackageUpgradeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not _has_perm(request.user, 'students:edit_any'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        student = get_object_or_404(Student, pk=pk)
        package_id = request.data.get('academic_package_id')
        if not package_id:
            return Response({'academic_package_id': 'This field is required.'}, status=status.HTTP_400_BAD_REQUEST)
        package = get_object_or_404(AcademicPackage.objects.select_related('minimum_level', 'maximum_level'), pk=package_id)
        try:
            effective_date = _parse_effective_date(request.data.get('effective_date'))
            enrollment, resumed_placement = upgrade_academic_package(
                student,
                package,
                actor=request.user,
                effective_date=effective_date,
            )
        except AcademicWorkflowError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'package_enrollment': StudentPackageEnrollmentSerializer(enrollment).data,
            'resumed_placement': StudentAcademicPlacementSerializer(resumed_placement).data if resumed_placement else None,
            'student': StudentSerializer(student).data,
        })


class AcademicBatchLevelFinalizeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, batch_id, level_id):
        if not _has_perm(request.user, 'students:edit_any'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        academic_batch = get_object_or_404(AcademicBatch.objects.select_related('branch'), pk=batch_id)
        level = get_object_or_404(CourseLevel, pk=level_id)
        try:
            effective_date = _parse_effective_date(request.data.get('effective_date'))
            result = finalize_batch_level(
                academic_batch,
                level,
                actor=request.user,
                effective_date=effective_date,
            )
        except AcademicWorkflowError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class StudentRepeatTransferAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not _has_perm(request.user, 'students:edit_any'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        student = get_object_or_404(Student, pk=pk)
        target_batch_id = request.data.get('academic_batch_id')
        if not target_batch_id:
            return Response({'academic_batch_id': 'This field is required.'}, status=status.HTTP_400_BAD_REQUEST)
        target_batch = get_object_or_404(
            AcademicBatch.objects.select_related('branch', 'starting_level'), pk=target_batch_id
        )
        try:
            effective_date = _parse_effective_date(request.data.get('effective_date'))
            placement = transfer_failed_student(
                student,
                target_batch,
                actor=request.user,
                effective_date=effective_date,
            )
        except AcademicWorkflowError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'placement': StudentAcademicPlacementSerializer(placement).data,
            'student': StudentSerializer(student).data,
        }, status=status.HTTP_201_CREATED)

class StudentAcademicActionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not (_has_perm(request.user, 'students:edit_any') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            
        student = get_object_or_404(Student, pk=pk)
        
        if hasattr(request.user, 'trainer_profile') and student.trainer != request.user.trainer_profile:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        action = request.data.get('action')
        new_academic_batch_id = request.data.get('academic_batch_id')
        new_level_id = request.data.get('level_id') # For promote

        if not action or not new_academic_batch_id:
            return Response({"error": "action and academic_batch_id are required"}, status=400)

        academic_batch = get_object_or_404(AcademicBatch, pk=new_academic_batch_id)

        desc = ""
        if action == 'PROMOTE':
            if not new_level_id:
                return Response({"error": "level_id is required for PROMOTE action"}, status=400)
            
            new_level = get_object_or_404(CourseLevel, pk=new_level_id)
            old_level_name = student.current_level.name if student.current_level else (student.batch or 'None')
            old_acad = student.academic_batch.name if student.academic_batch else 'None'
            
            student.current_level = new_level
            student.batch = new_level.name  # For backwards compatibility
            student.academic_batch = academic_batch
            student.status = 'PENDING_BATCH_ASSIGNMENT'
            desc = f"Promoted from {old_level_name} ({old_acad}) to {new_level.name} ({academic_batch.name})"
        elif action == 'FALLBACK':
            old_acad = student.academic_batch.name if student.academic_batch else 'None'
            student.academic_batch = academic_batch
            level_name = student.current_level.name if student.current_level else (student.batch or 'None')
            desc = f"Fallbacked from {old_acad} to {academic_batch.name} within {level_name}"
        elif action == 'EXAM_PREP':
            student.status = 'EXAM_PREPARATION'
            desc = "Marked for Exam Preparation"
            action = 'STATUS_CHANGE'
        else:
            return Response({"error": "Invalid action"}, status=400)

        student.save()

        StudentTimeline.objects.create(
            student=student,
            event_type=action,
            description=desc,
            created_by=request.user
        )

        return Response({"message": "Success", "student": StudentSerializer(student).data})


class CourseLevelListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = CourseLevel.objects.all().order_by('order')
        serializer = CourseLevelSerializer(qs, many=True)
        return Response(serializer.data)


class StudentModuleProgressAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        
        if not (_has_perm(request.user, 'students:read_any') or (hasattr(request.user, 'trainer_profile') and student.trainer == request.user.trainer_profile)):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            
        progress = StudentModuleProgress.objects.filter(student=student)
        serializer = StudentModuleProgressSerializer(progress, many=True)
        return Response(serializer.data)

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        
        if not (_has_perm(request.user, 'students:edit_any') or (hasattr(request.user, 'trainer_profile') and student.trainer == request.user.trainer_profile)):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            
        module_id = request.data.get('module_id')
        progress_status = request.data.get('status')
        score = request.data.get('score')
        remarks = request.data.get('remarks')
        
        if not module_id or not progress_status:
            return Response({"error": "module_id and status are required"}, status=400)
            
        module = get_object_or_404(CourseModule, pk=module_id)
        
        progress, created = StudentModuleProgress.objects.update_or_create(
            student=student,
            module=module,
            academic_batch=student.academic_batch,
            defaults={
                'status': progress_status,
                'score': score,
                'remarks': remarks,
                'evaluated_by': request.user
            }
        )
        
        return Response(StudentModuleProgressSerializer(progress).data)

