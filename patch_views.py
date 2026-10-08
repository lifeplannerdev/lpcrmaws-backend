import re

with open("students/views.py", "r") as f:
    content = f.read()

replacement = """    @action(detail=True, methods=['post'])
    def promote(self, request, pk=None):
        student = self.get_object()
        if not student.grade_batch:
            return Response({'error': 'Student is not assigned to a Grade Batch.'}, status=400)
        
        current_order = student.grade_batch.grade.order
        academic_batch = student.batch
        
        next_grade_batch = GradeBatch.objects.filter(
            academic_batch=academic_batch,
            grade__order__gt=current_order
        ).order_by('grade__order').first()

        if not next_grade_batch:
            return Response({'error': 'Student has reached the highest grade in this package.'}, status=400)

        StudentBatchHistory.objects.create(
            student=student,
            batch=academic_batch,
            grade_batch=next_grade_batch,
            action='promoted',
            reason=request.data.get('reason', ''),
            done_by=request.user
        )

        student.grade_batch = next_grade_batch
        student.save()
        return Response({'status': 'Student promoted successfully', 'new_grade': next_grade_batch.grade.code})

    @action(detail=True, methods=['post'])
    def demote(self, request, pk=None):
        student = self.get_object()
        target_academic_batch_id = request.data.get('academic_batch_id')
        target_grade_batch_id = request.data.get('grade_batch_id')
        reason = request.data.get('reason', '')

        if not target_academic_batch_id or not target_grade_batch_id:
            return Response({'error': 'Both Academic Batch and Grade Batch must be specified for demotion/reassignment.'}, status=400)

        try:
            new_academic_batch = AcademicBatch.objects.get(id=target_academic_batch_id)
            new_grade_batch = GradeBatch.objects.get(id=target_grade_batch_id, academic_batch=new_academic_batch)
        except (AcademicBatch.DoesNotExist, GradeBatch.DoesNotExist):
            return Response({'error': 'Invalid Academic Batch or Grade Batch selected.'}, status=400)

        StudentBatchHistory.objects.create(
            student=student,
            batch=new_academic_batch,
            grade_batch=new_grade_batch,
            action='demoted',
            reason=reason,
            done_by=request.user
        )

        student.batch = new_academic_batch
        student.grade_batch = new_grade_batch
        student.save()
        return Response({'status': 'Student demoted/reassigned successfully'})"""

# regex replace
content = re.sub(
    r"    @action\(detail=True, methods=\['post'\]\)\s+def promote\(self, request, pk=None\):\s+student = self\.get_object\(\)\s+return Response\(\{'status': 'Not implemented here, use batch promotion'\}, status=400\)",
    replacement,
    content
)

with open("students/views.py", "w") as f:
    f.write(content)
