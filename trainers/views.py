from accounts.permissions import has_dynamic_permission
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.db.models import Count, Q
from django.contrib.auth import get_user_model
import csv

from .models import Trainer, Student, Attendance, Branch, ExamResult
from .serializers import (
    TrainerSerializer, 
    StudentSerializer, 
    AttendanceSerializer,
    TrainerUserSerializer,
    AcademicBatchSerializer,
    BranchSerializer,
    ExamResultSerializer
)
from .permissions import IsTrainerOwnStudent

User = get_user_model()


def _has_perm(user, perm):
    return user.is_authenticated and has_dynamic_permission(user, perm)


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
        trainers = User.objects.filter(role='TRAINER', is_active=True)
        
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

        qs = Student.objects.select_related('trainer', 'trainer__user', 'academic_batch', 'branch')
        qs = qs.select_related('fee_account')

        if hasattr(request.user, 'trainer_profile'):
            qs = qs.filter(trainer=request.user.trainer_profile)

        status_filter = request.GET.get('status')
        batch_filter = request.GET.get('batch')
        academic_batch = request.GET.get('academic_batch')
        trainer_filter = request.GET.get('trainer')
        branch_id = request.GET.get('branch_id')
        search = request.GET.get('search')

        if status_filter:
            qs = qs.filter(status=status_filter)
        if batch_filter:
            qs = qs.filter(batch=batch_filter)
        if academic_batch:
            qs = qs.filter(academic_batch_id=academic_batch)
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

        serializer = StudentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class AcademicBatchListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'manage_students') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        qs = AcademicBatch.objects.all()
        academic_year = request.GET.get('academic_year')
        if academic_year:
            qs = qs.filter(academic_year=academic_year)
        serializer = AcademicBatchSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = AcademicBatchSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


class AcademicBatchDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(AcademicBatch, pk=pk)

    def get(self, request, pk):
        batch = self.get_object(pk)
        return Response(AcademicBatchSerializer(batch).data)

    def put(self, request, pk):
        batch = self.get_object(pk)
        serializer = AcademicBatchSerializer(batch, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)

    def delete(self, request, pk):
        batch = self.get_object(pk)
        batch.delete()
        return Response({"message": "Batch deleted"}, status=status.HTTP_204_NO_CONTENT)


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
        if not _has_perm(request.user, 'students:edit_any'):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        student = self.get_object(request, pk)
        serializer = StudentSerializer(student, data=request.data)
        if serializer.is_valid():
            serializer.save()
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
            'student', 'trainer', 'trainer__user'
        ).order_by('-date')
        if hasattr(request.user, 'trainer_profile'):
            qs = qs.filter(trainer=request.user.trainer_profile)

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

        serializer = AttendanceSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(trainer=trainer)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
        

class AttendanceDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'attendance:mark') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        records = Attendance.objects.select_related(
            'student', 'trainer', 'trainer__user'
        ).order_by('-date')

        if hasattr(request.user, 'trainer_profile'):
            records = records.filter(trainer=request.user.trainer_profile)

        student_id = request.GET.get('student')
        trainer_id = request.GET.get('trainer')
        branch_id = request.GET.get('branch_id')
        date = request.GET.get('date')

        if student_id:
            records = records.filter(student_id=student_id)
        if trainer_id:
            records = records.filter(trainer_id=trainer_id)
        if branch_id:
            records = records.filter(student__branch_id=branch_id)
        if date:
            records = records.filter(date=date)

        
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

                obj, created = Attendance.objects.update_or_create(
                    student=student, 
                    date=date,
                    defaults={
                        'trainer': trainer_to_assign,
                        'status': r.get('status', 'PRESENT')
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
        qs = Attendance.objects.filter(student_id=student_id).order_by('-date')

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
        qs = Attendance.objects.filter(student_id=student_id).order_by('date')

        if hasattr(request.user, 'trainer_profile'):
            qs = qs.filter(trainer=request.user.trainer_profile)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="student_{student_id}_attendance.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(['Date', 'Trainer', 'Status'])

        for r in qs:
            writer.writerow([
                r.date,
                r.trainer.user.get_full_name(),
                r.status
            ])

        return response


class AttendanceStudentsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not (_has_perm(request.user, 'students:read_tenant') or _has_perm(request.user, 'attendance:mark') or hasattr(request.user, 'trainer_profile')):
            return Response({"error": "Only authorized users can access this endpoint"}, status=403)
        students = Student.objects.exclude(
            status__in=['COMPLETED', 'DROPPED']
        ).select_related('trainer', 'trainer__user').order_by('name')

        if hasattr(request.user, 'trainer_profile'):
            students = students.filter(trainer=request.user.trainer_profile)
        
        batch = request.GET.get('batch')
        student_class = request.GET.get('student_class')
        trainer_id = request.GET.get('trainer')
        branch_id = request.GET.get('branch_id')
        location = request.GET.get('location')
        
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

        serializer = StudentSerializer(students, many=True)
        return Response({
            'count': students.count(),
            'results': serializer.data
        })



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
        qs = ExamResult.objects.select_related('student', 'academic_batch')
        
        student_id = request.GET.get('student_id')
        academic_batch_id = request.GET.get('academic_batch_id')
        exam_type = request.GET.get('exam_type')

        if student_id:
            qs = qs.filter(student_id=student_id)
        if academic_batch_id:
            qs = qs.filter(academic_batch_id=academic_batch_id)
        if exam_type:
            qs = qs.filter(exam_type=exam_type.upper())

        serializer = ExamResultSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ExamResultSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ExamResultDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        result = get_object_or_404(ExamResult, pk=pk)
        serializer = ExamResultSerializer(result)
        return Response(serializer.data)

    def put(self, request, pk):
        result = get_object_or_404(ExamResult, pk=pk)
        serializer = ExamResultSerializer(result, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        result = get_object_or_404(ExamResult, pk=pk)
        result.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

