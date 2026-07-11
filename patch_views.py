import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

with open('trainers/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add imports if not present
if 'StudentTimeline' not in content:
    content = content.replace('AcademicBatch\n', 'AcademicBatch, StudentTimeline\n')

if 'StudentTimelineSerializer' not in content:
    content = content.replace('AcademicBatchSerializer,\n', 'AcademicBatchSerializer,\n    StudentTimelineSerializer,\n')

# Add views to the end
new_views = """
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
        new_batch = request.data.get('batch') # For promote

        if not action or not new_academic_batch_id:
            return Response({"error": "action and academic_batch_id are required"}, status=400)

        academic_batch = get_object_or_404(AcademicBatch, pk=new_academic_batch_id)

        desc = ""
        if action == 'PROMOTE':
            if not new_batch:
                return Response({"error": "batch is required for PROMOTE action"}, status=400)
            old_batch = student.batch
            old_acad = student.academic_batch.name if student.academic_batch else 'None'
            student.batch = new_batch
            student.academic_batch = academic_batch
            student.status = 'PENDING_BATCH_ASSIGNMENT'
            desc = f"Promoted from {old_batch} ({old_acad}) to {new_batch} ({academic_batch.name})"
        elif action == 'FALLBACK':
            old_acad = student.academic_batch.name if student.academic_batch else 'None'
            student.academic_batch = academic_batch
            desc = f"Fallbacked from {old_acad} to {academic_batch.name} within {student.batch}"
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
"""

if 'StudentTimelineAPIView' not in content:
    content += new_views

# Update StudentDetailAPIView put method
old_put = """    def put(self, request, pk):
        if not _has_perm(request.user, 'students:edit_any'):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        student = self.get_object(request, pk)
        serializer = StudentSerializer(student, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)"""

new_put = """    def put(self, request, pk):
        if not (_has_perm(request.user, 'students:edit_any') or hasattr(request.user, 'trainer_profile')):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        student = self.get_object(request, pk)
        
        old_status = student.status
        old_batch = student.academic_batch_id
        
        serializer = StudentSerializer(student, data=request.data)
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
        return Response(serializer.errors, status=400)"""

if 'old_status = student.status' not in content:
    content = content.replace(old_put, new_put)

with open('trainers/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated views.py")
