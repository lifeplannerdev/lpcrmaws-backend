from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import AcademicGrade, AcademicPackage, AcademicBatch, Student, ExamResult, BatchAttendance, DailyRemark
from .serializers import (
    AcademicGradeSerializer, AcademicPackageSerializer, AcademicBatchSerializer,
    StudentSerializer, ExamResultSerializer, BatchAttendanceSerializer,
    DailyRemarkSerializer, BatchPromotionSerializer, BulkAttendanceSubmitSerializer
)
from fees.models import StudentFeeAccount

class AcademicGradeViewSet(viewsets.ModelViewSet):
    queryset = AcademicGrade.objects.all()
    serializer_class = AcademicGradeSerializer

class AcademicPackageViewSet(viewsets.ModelViewSet):
    queryset = AcademicPackage.objects.all()
    serializer_class = AcademicPackageSerializer

class AcademicBatchViewSet(viewsets.ModelViewSet):
    queryset = AcademicBatch.objects.all()
    serializer_class = AcademicBatchSerializer

    @action(detail=True, methods=['get'])
    def preview_promote(self, request, pk=None):
        batch = self.get_object()
        
        # 1. Verify all students have a MAIN exam result for the current grade
        students = batch.students.filter(is_active=True)
        for student in students:
            if not ExamResult.objects.filter(student=student, batch=batch, grade=batch.current_grade, exam_type='MAIN').exists():
                return Response({'error': f'Student {student.name} does not have a MAIN exam result for this grade.'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Enforce MODEL exam for A1
            if 'A1' in batch.current_grade.name.upper():
                model_passed = ExamResult.objects.filter(student=student, batch=batch, grade=batch.current_grade, exam_type='MODEL', status='PASSED').exists()
                if not model_passed:
                    return Response({'error': f'Student {student.name} must pass the mandatory MODEL exam for {batch.current_grade.name} before promotion.'}, status=status.HTTP_400_BAD_REQUEST)
                
        # 2. Get passed and failed students
        passed_students = []
        failed_students = []
        for student in students:
            result = ExamResult.objects.get(student=student, batch=batch, grade=batch.current_grade, exam_type='MAIN')
            if result.status == 'PASSED':
                passed_students.append({'id': student.id, 'name': student.name})
            else:
                failed_students.append({'id': student.id, 'name': student.name})
                
        # 3. Check next grade
        next_grade = AcademicGrade.objects.filter(order__gt=batch.current_grade.order).order_by('order').first()
        if not next_grade:
            return Response({'error': 'No higher grade available for promotion.'}, status=status.HTTP_400_BAD_REQUEST)
            
        return Response({
            'passed_students': passed_students,
            'failed_students': failed_students,
            'next_grade': {'id': next_grade.id, 'name': next_grade.name}
        })

    @action(detail=True, methods=['post'])
    def promote(self, request, pk=None):
        batch = self.get_object()
        
        # 1. Verify all students have a MAIN exam result for the current grade
        students = batch.students.filter(is_active=True)
        for student in students:
            if not ExamResult.objects.filter(student=student, batch=batch, grade=batch.current_grade, exam_type='MAIN').exists():
                return Response({'error': f'Student {student.name} does not have a MAIN exam result for this grade.'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Enforce MODEL exam for A1
            if 'A1' in batch.current_grade.name.upper():
                model_passed = ExamResult.objects.filter(student=student, batch=batch, grade=batch.current_grade, exam_type='MODEL', status='PASSED').exists()
                if not model_passed:
                    return Response({'error': f'Student {student.name} must pass the mandatory MODEL exam for {batch.current_grade.name} before promotion.'}, status=status.HTTP_400_BAD_REQUEST)
                
        # 2. Get passed and failed students
        passed_students = []
        failed_students = []
        for student in students:
            result = ExamResult.objects.get(student=student, batch=batch, grade=batch.current_grade, exam_type='MAIN')
            if result.status == 'PASSED':
                passed_students.append(student)
            else:
                failed_students.append(student)
                
        # 3. Upgrade batch grade
        next_grade = AcademicGrade.objects.filter(order__gt=batch.current_grade.order).order_by('order').first()
        if not next_grade:
            return Response({'error': 'No higher grade available for promotion.'}, status=status.HTTP_400_BAD_REQUEST)
            
        batch.current_grade = next_grade
        batch.save()
        
        # 4. Handle failed students and create timeline events
        from .models import StudentTimeline
        demoted_assignments = request.data.get('demoted_assignments', {})
        
        for student in failed_students:
            reassigned_batch_id = demoted_assignments.get(str(student.id))
            if reassigned_batch_id:
                try:
                    new_batch = AcademicBatch.objects.get(id=reassigned_batch_id)
                    student.batch = new_batch
                    student.save()
                    StudentTimeline.objects.create(
                        student=student,
                        event_type='DEMOTED',
                        description=f'Failed {batch.current_grade.name} and reassigned to batch {new_batch.name}.',
                        created_by=request.user
                    )
                except AcademicBatch.DoesNotExist:
                    pass
            else:
                student.batch = None # Detach so they can be manually assigned to a repeating batch
                student.save()
                StudentTimeline.objects.create(
                    student=student,
                    event_type='DEMOTED',
                    description=f'Failed {batch.current_grade.name} and detached from batch {batch.name}.',
                    created_by=request.user
                )
            
        for student in passed_students:
            StudentTimeline.objects.create(
                student=student,
                event_type='PROMOTED',
                description=f'Promoted to {next_grade.name} with batch {batch.name}.',
                created_by=request.user
            )
            
        return Response({
            'message': f'Batch promoted to {next_grade.name}.',
            'passed_count': len(passed_students),
            'failed_detached_count': len(failed_students)
        })

class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer

    def get_queryset(self):
        from accounts.permissions import has_dynamic_permission
        qs = Student.objects.select_related('package', 'batch', 'trainer').all()
        
        # Check if user has permission to read all students
        can_read_all = (
            has_dynamic_permission(self.request.user, 'students:read_tenant') or
            has_dynamic_permission(self.request.user, 'students:admin') or
            has_dynamic_permission(self.request.user, 'students:registry_manage') or
            has_dynamic_permission(self.request.user, 'students')
        )
        
        if not can_read_all:
            # Trainers/Users who can only read their own students
            qs = qs.filter(trainer=self.request.user)
            
        # Standard filters
        is_active = self.request.query_params.get('is_active')
        batch = self.request.query_params.get('batch')
        trainer = self.request.query_params.get('trainer')
        location = self.request.query_params.get('location')
        
        if is_active:
            qs = qs.filter(is_active=is_active.lower() == 'true')
        if batch:
            qs = qs.filter(batch_id=batch)
            
        # Admin specific filters
        if can_read_all:
            if trainer:
                qs = qs.filter(trainer_id=trainer)
            if location:
                qs = qs.filter(trainer__location=location)
                
        return qs

    def perform_create(self, serializer):
        student = serializer.save()
        fee_template_id = self.request.data.get('fee_template')
        if fee_template_id:
            from fees.models import FeePlanTemplate, StudentFeeAccount
            try:
                template = FeePlanTemplate.objects.get(id=fee_template_id)
                StudentFeeAccount.objects.create(
                    student=student,
                    template=template,
                    plan_code=template.code,
                    plan_name=template.name,
                    plan_type=template.plan_type,
                    total_due=template.total_amount,
                    balance_due=template.total_amount,
                    registration_amount=template.registration_amount,
                    due_day=template.due_day,
                    created_by=self.request.user
                )
            except FeePlanTemplate.DoesNotExist:
                pass

class ExamResultViewSet(viewsets.ModelViewSet):
    queryset = ExamResult.objects.all()
    serializer_class = ExamResultSerializer

    def get_queryset(self):
        qs = ExamResult.objects.all()
        student = self.request.query_params.get('student')
        if student:
            qs = qs.filter(student_id=student)
        return qs

class BatchAttendanceViewSet(viewsets.ModelViewSet):
    queryset = BatchAttendance.objects.all()
    serializer_class = BatchAttendanceSerializer

    def get_queryset(self):
        qs = BatchAttendance.objects.select_related('student', 'batch', 'grade', 'marked_by').all()
        approval_status = self.request.query_params.get('approval_status')
        batch = self.request.query_params.get('batch')
        date = self.request.query_params.get('date')
        student = self.request.query_params.get('student')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if approval_status:
            qs = qs.filter(approval_status=approval_status)
        if batch:
            qs = qs.filter(batch_id=batch)
        if date:
            qs = qs.filter(date=date)
        if student:
            qs = qs.filter(student_id=student)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        return qs.order_by('date')

    @action(detail=False, methods=['post'])
    def bulk_submit(self, request):
        serializer = BulkAttendanceSubmitSerializer(data=request.data)
        if serializer.is_valid():
            batch_id = serializer.validated_data['batch_id']
            date = serializer.validated_data['date']
            attendances = serializer.validated_data['attendances']
            
            batch = AcademicBatch.objects.get(id=batch_id)
            
            results = []
            for item in attendances:
                student = Student.objects.get(id=item['student_id'])
                attendance_status = item['status']
                
                # Check fees if strict policy
                approval_status = 'APPROVED'
                if student.fee_attendance_policy == 'STRICT' and attendance_status == 'PRESENT':
                    # Check fee due
                    try:
                        fee_account = student.fee_account
                        if fee_account.is_overdue:
                            approval_status = 'PENDING'
                    except StudentFeeAccount.DoesNotExist:
                        pass # No fee account, assume no due
                        
                att, created = BatchAttendance.objects.update_or_create(
                    student=student,
                    date=date,
                    defaults={
                        'batch': batch,
                        'grade': batch.current_grade,
                        'status': attendance_status,
                        'approval_status': approval_status,
                        'marked_by': request.user
                    }
                )
                results.append(BatchAttendanceSerializer(att).data)
                
            return Response({'message': 'Attendance marked successfully', 'data': results})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    @action(detail=True, methods=['post'])
    def regularize(self, request, pk=None):
        attendance = self.get_object()
        attendance.approval_status = 'APPROVED'
        attendance.regularized_by = request.user
        attendance.save()
        return Response({'message': 'Attendance regularized.'})

class DailyRemarkViewSet(viewsets.ModelViewSet):
    queryset = DailyRemark.objects.all()
    serializer_class = DailyRemarkSerializer
