import re

with open("students/views.py", "r") as f:
    content = f.read()

bulk_action = """    @action(detail=False, methods=['post'])
    def bulk_entry(self, request):
        grade_batch_id = request.data.get('grade_batch')
        date = request.data.get('date')
        records = request.data.get('records', [])
        
        if not grade_batch_id or not date:
            return Response({'error': 'grade_batch and date are required'}, status=400)
            
        session, created = AttendanceSession.objects.get_or_create(
            grade_batch_id=grade_batch_id,
            date=date,
            defaults={'created_by': request.user}
        )
        
        for rec in records:
            student_id = rec.get('student')
            status = rec.get('status')
            if student_id and status:
                AttendanceRecord.objects.update_or_create(
                    session=session,
                    student_id=student_id,
                    defaults={'status': status}
                )
                
        return Response({'status': 'success', 'session_id': session.id})

"""

# Insert right after `def perform_create(self, serializer): serializer.save(created_by=self.request.user)`
# Wait, let's just insert before `class AttendanceRecordViewSet`

content = content.replace("class AttendanceRecordViewSet", bulk_action + "class AttendanceRecordViewSet")

with open("students/views.py", "w") as f:
    f.write(content)
