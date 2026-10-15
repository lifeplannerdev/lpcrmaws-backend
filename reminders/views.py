from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q, Case, When, IntegerField, Count
from django.contrib.auth import get_user_model

from .models import Reminder, ReminderUpdate
from .serializers import (
    ReminderSerializer,
    ReminderDetailSerializer,
    ReminderUpdateSerializer,
    ReminderUserBriefSerializer,
)
from .permissions import (
    is_reminders_admin,
    is_reminders_user,
    HasRemindersAccess,
    HasRemindersAdminAccess,
)

User = get_user_model()


def _get_reminder_queryset(user, base_qs=None):
    if base_qs is None:
        base_qs = Reminder.objects.select_related('user', 'created_by', 'approved_by', 'student')

    if is_reminders_admin(user):
        return base_qs

    return base_qs.filter(user=user)


class ReminderListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, HasRemindersAccess]
    serializer_class = ReminderSerializer

    def get_queryset(self):
        user = self.request.user
        qs = _get_reminder_queryset(user)

        # Filters
        status_param = self.request.query_params.get('status')
        priority_param = self.request.query_params.get('priority')
        category_param = self.request.query_params.get('category')
        company_param = self.request.query_params.get('company')
        user_param = self.request.query_params.get('user')
        student_param = self.request.query_params.get('student')
        is_mine_param = self.request.query_params.get('is_mine')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        search_query = self.request.query_params.get('search')
        is_today = self.request.query_params.get('today')
        is_backdated = self.request.query_params.get('backdated')
        is_overdue = self.request.query_params.get('overdue')

        if is_mine_param in ['true', '1']:
            qs = qs.filter(user=user)
        elif user_param and is_reminders_admin(user):
            qs = qs.filter(user_id=user_param)

        if student_param:
            qs = qs.filter(student_id=student_param)

        if status_param and status_param != 'ALL':
            qs = qs.filter(status=status_param)

        if priority_param and priority_param != 'ALL':
            qs = qs.filter(priority=priority_param)

        if category_param and category_param != 'ALL':
            qs = qs.filter(category__iexact=category_param)

        if company_param and company_param != 'ALL' and is_reminders_admin(user):
            qs = qs.filter(company=company_param)

        today_date = timezone.now().date()
        if is_today in ['true', '1']:
            qs = qs.filter(reminder_date=today_date)

        if is_backdated in ['true', '1']:
            qs = qs.filter(reminder_date__lt=today_date)

        if is_overdue in ['true', '1']:
            qs = qs.filter(
                Q(deadline__lt=today_date) | (Q(deadline__isnull=True) & Q(reminder_date__lt=today_date))
            ).exclude(status__in=['COMPLETED', 'CANCELLED', 'PENDING_APPROVAL'])

        if date_from:
            qs = qs.filter(reminder_date__gte=date_from)
        if date_to:
            qs = qs.filter(reminder_date__lte=date_to)

        if search_query:
            qs = qs.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(user__first_name__icontains=search_query) |
                Q(user__last_name__icontains=search_query) |
                Q(user__username__icontains=search_query) |
                Q(student__name__icontains=search_query) |
                Q(student__mobile_number__icontains=search_query)
            )

        # Smart ordering:
        # 1. PENDING_APPROVAL
        # 2. IN_PROGRESS
        # 3. PENDING
        # 4. COMPLETED
        # 5. CANCELLED
        return qs.annotate(
            status_order=Case(
                When(status='PENDING_APPROVAL', then=1),
                When(status='IN_PROGRESS', then=2),
                When(status='PENDING', then=3),
                When(status='COMPLETED', then=4),
                When(status='CANCELLED', then=5),
                default=6,
                output_field=IntegerField(),
            )
        ).order_by('status_order', '-reminder_date', '-created_at')

    def perform_create(self, serializer):
        user = self.request.user
        target_user = user
        target_user_id = self.request.data.get('user')

        # Only admins can create reminders on behalf of other staff
        if target_user_id and is_reminders_admin(user):
            try:
                target_user = User.objects.get(id=target_user_id)
            except User.DoesNotExist:
                raise ValidationError({"user": "Selected user does not exist."})

        company = self.request.data.get('company') or getattr(target_user, 'company', 'LP') or 'LP'

        reminder = serializer.save(
            user=target_user,
            created_by=user,
            company=company,
        )

        # Record initial creation update
        ReminderUpdate.objects.create(
            reminder=reminder,
            author=user,
            notes="Reminder created.",
            previous_status='',
            new_status=reminder.status,
            is_system_event=True,
        )


class ReminderDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, HasRemindersAccess]
    serializer_class = ReminderDetailSerializer

    def get_queryset(self):
        return _get_reminder_queryset(self.request.user)

    def perform_update(self, serializer):
        reminder = self.get_object()
        old_status = reminder.status
        instance = serializer.save()

        if instance.status != old_status:
            ReminderUpdate.objects.create(
                reminder=instance,
                author=self.request.user,
                notes=f"Status changed from {old_status} to {instance.status}.",
                previous_status=old_status,
                new_status=instance.status,
                is_system_event=True,
            )


class ReminderSubmitCompletionAPIView(APIView):
    """
    Submits reminder for completion.
    Requires mandatory completion remarks.
    - If user has processing:reminders_admin: directly transitions to COMPLETED.
    - If user has processing:reminders_users: transitions to PENDING_APPROVAL.
    """
    permission_classes = [IsAuthenticated, HasRemindersAccess]

    def post(self, request, pk):
        reminder = get_object_or_404(_get_reminder_queryset(request.user), pk=pk)

        if reminder.status == 'COMPLETED':
            return Response(
                {"detail": "This reminder is already marked as completed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        remarks = (request.data.get('completion_remarks') or '').strip()
        if not remarks:
            return Response(
                {"detail": "Completion remarks are mandatory to mark the work as complete."},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_status = reminder.status
        is_admin = is_reminders_admin(request.user)
        user_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username

        reminder.completed_by = request.user
        reminder.completed_at = timezone.now()
        reminder.completion_remarks = remarks

        if is_admin:
            # Admin completion does not need approval
            reminder.status = 'COMPLETED'
            reminder.approved_by = request.user
            reminder.approved_at = timezone.now()
            reminder.save()

            ReminderUpdate.objects.create(
                reminder=reminder,
                author=request.user,
                notes=f"Reminder marked completed by {user_name} (Admin Auto-approval).\nCompletion remarks: {remarks}",
                previous_status=old_status,
                new_status='COMPLETED',
                is_system_event=True,
            )

            return Response({
                "detail": "Reminder completed successfully.",
                "status": "COMPLETED",
                "reminder": ReminderSerializer(reminder).data
            })
        else:
            # Regular user completion requires admin approval
            reminder.status = 'PENDING_APPROVAL'
            reminder.save()

            ReminderUpdate.objects.create(
                reminder=reminder,
                author=request.user,
                notes=f"Work completed by {user_name} and submitted for admin approval.\nCompletion remarks: {remarks}",
                previous_status=old_status,
                new_status='PENDING_APPROVAL',
                is_system_event=True,
            )

            return Response({
                "detail": "Reminder marked as complete and submitted for admin approval.",
                "status": "PENDING_APPROVAL",
                "reminder": ReminderSerializer(reminder).data
            })


class ReminderApproveAPIView(APIView):
    """
    Admin approval of completed work.
    """
    permission_classes = [IsAuthenticated, HasRemindersAdminAccess]

    def post(self, request, pk):
        reminder = get_object_or_404(Reminder, pk=pk)

        if reminder.status != 'PENDING_APPROVAL':
            return Response(
                {"detail": f"Reminder cannot be approved because its current status is '{reminder.status}' (expected 'PENDING_APPROVAL')."},
                status=status.HTTP_400_BAD_REQUEST
            )

        notes = (request.data.get('notes') or '').strip()
        admin_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
        approval_note = notes if notes else f"Approved by {admin_name}."

        old_status = reminder.status
        reminder.status = 'COMPLETED'
        reminder.approved_by = request.user
        reminder.approved_at = timezone.now()
        reminder.save()

        ReminderUpdate.objects.create(
            reminder=reminder,
            author=request.user,
            notes=f"Completion Approved by {admin_name}.\n{approval_note}",
            previous_status=old_status,
            new_status='COMPLETED',
            is_system_event=True,
        )

        return Response({
            "detail": "Reminder completion approved successfully.",
            "status": "COMPLETED",
            "reminder": ReminderSerializer(reminder).data
        })


class ReminderRejectAPIView(APIView):
    """
    Admin rejection of completed work (returns to In Progress with required notes).
    """
    permission_classes = [IsAuthenticated, HasRemindersAdminAccess]

    def post(self, request, pk):
        reminder = get_object_or_404(Reminder, pk=pk)

        if reminder.status != 'PENDING_APPROVAL':
            return Response(
                {"detail": f"Reminder cannot be rejected because its current status is '{reminder.status}' (expected 'PENDING_APPROVAL')."},
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = (request.data.get('reason') or '').strip()
        if not reason:
            return Response(
                {"detail": "Rejection reason / feedback notes are mandatory."},
                status=status.HTTP_400_BAD_REQUEST
            )

        new_deadline = request.data.get('new_deadline')
        admin_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username

        old_status = reminder.status
        reminder.status = 'IN_PROGRESS'
        reminder.rejection_reason = reason
        if new_deadline:
            reminder.deadline = new_deadline
        reminder.save()

        notes_content = f"Completion Rejected by {admin_name}: Returned to In Progress.\nFeedback: {reason}"
        if new_deadline:
            notes_content += f"\nNew Deadline: {new_deadline}"

        ReminderUpdate.objects.create(
            reminder=reminder,
            author=request.user,
            notes=notes_content,
            previous_status=old_status,
            new_status='IN_PROGRESS',
            is_system_event=True,
        )

        return Response({
            "detail": "Reminder completion rejected and reverted to In Progress.",
            "status": "IN_PROGRESS",
            "reminder": ReminderSerializer(reminder).data
        })


class ReminderUpdateListCreateAPIView(generics.ListCreateAPIView):
    """
    Two-way communication thread for posting remarks/questions/updates.
    """
    permission_classes = [IsAuthenticated, HasRemindersAccess]
    serializer_class = ReminderUpdateSerializer

    def get_queryset(self):
        reminder = get_object_or_404(_get_reminder_queryset(self.request.user), pk=self.kwargs['pk'])
        return reminder.updates.all().order_by('created_at')

    def perform_create(self, serializer):
        reminder = get_object_or_404(_get_reminder_queryset(self.request.user), pk=self.kwargs['pk'])
        notes = (self.request.data.get('notes') or '').strip()
        if not notes:
            raise ValidationError({"notes": "Update note text cannot be blank."})

        serializer.save(
            reminder=reminder,
            author=self.request.user,
            is_system_event=False
        )


class ReminderChecklistToggleAPIView(APIView):
    """
    Quick API to toggle a single checklist item on a reminder, optionally saving remarks.
    """
    permission_classes = [IsAuthenticated, HasRemindersAccess]

    def post(self, request, pk):
        reminder = get_object_or_404(_get_reminder_queryset(request.user), pk=pk)
        item_id = str(request.data.get('item_id', ''))
        completed = bool(request.data.get('completed', False))
        remarks = (request.data.get('remarks') or '').strip()

        checklist = reminder.checklist or []
        updated = False
        item_text = ""

        user_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username

        for item in checklist:
            if str(item.get('id')) == item_id:
                item['completed'] = completed
                item['completed_at'] = timezone.now().isoformat() if completed else None
                if completed:
                    item['remarks'] = remarks
                    item['completed_by'] = request.user.id
                    item['completed_by_name'] = user_name
                else:
                    item['remarks'] = ''
                    item['completed_by'] = None
                    item['completed_by_name'] = None
                item_text = item.get('text', '')
                updated = True
                break

        if not updated:
            return Response({"detail": "Checklist item not found."}, status=status.HTTP_404_NOT_FOUND)

        reminder.checklist = checklist
        # If reminder is in PENDING and an item is completed, move to IN_PROGRESS
        if reminder.status == 'PENDING' and completed:
            reminder.status = 'IN_PROGRESS'
        reminder.save()

        # Record activity note with remarks if present
        action_verb = "completed" if completed else "unmarked"
        if completed and remarks:
            update_notes = f"Checklist item '{item_text}' was completed by {user_name}.\nRemark: {remarks}"
        elif completed:
            update_notes = f"Checklist item '{item_text}' was completed by {user_name}."
        else:
            update_notes = f"Checklist item '{item_text}' was unmarked by {user_name}."

        ReminderUpdate.objects.create(
            reminder=reminder,
            author=request.user,
            notes=update_notes,
            is_system_event=True
        )

        return Response({
            "detail": f"Item {action_verb} successfully.",
            "checklist": reminder.checklist,
            "status": reminder.status,
            "reminder": ReminderSerializer(reminder).data
        })


class ReminderBriefingToggleAPIView(APIView):
    """
    Toggle completion of the main briefing task itself, with optional remarks.
    """
    permission_classes = [IsAuthenticated, HasRemindersAccess]

    def post(self, request, pk):
        reminder = get_object_or_404(_get_reminder_queryset(request.user), pk=pk)
        completed = bool(request.data.get('completed', False))
        remarks = (request.data.get('remarks') or '').strip()
        user_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username

        reminder.briefing_completed = completed
        reminder.briefing_completed_at = timezone.now() if completed else None
        reminder.briefing_remarks = remarks if completed else ''
        reminder.briefing_completed_by = request.user if completed else None

        if reminder.status == 'PENDING' and completed:
            reminder.status = 'IN_PROGRESS'
        reminder.save()

        if completed and remarks:
            update_notes = f"Main task (Briefing) was marked completed by {user_name}.\nRemark: {remarks}"
        elif completed:
            update_notes = f"Main task (Briefing) was marked completed by {user_name}."
        else:
            update_notes = f"Main task (Briefing) was unmarked by {user_name}."

        ReminderUpdate.objects.create(
            reminder=reminder,
            author=request.user,
            notes=update_notes,
            is_system_event=True
        )

        return Response({
            "detail": "Main task / Briefing updated successfully.",
            "briefing_completed": reminder.briefing_completed,
            "briefing_remarks": reminder.briefing_remarks,
            "status": reminder.status,
            "reminder": ReminderSerializer(reminder).data
        })


class ReminderStatsAPIView(APIView):
    """
    Summary counts for reminders dashboard.
    """
    permission_classes = [IsAuthenticated, HasRemindersAccess]

    def get(self, request):
        user = request.user
        qs = _get_reminder_queryset(user)

        today_date = timezone.now().date()
        is_admin = is_reminders_admin(user)

        stats = {
            "total": qs.count(),
            "today": qs.filter(reminder_date=today_date).count(),
            "pending_approval": qs.filter(status='PENDING_APPROVAL').count(),
            "completed": qs.filter(status='COMPLETED').count(),
            "in_progress": qs.filter(status='IN_PROGRESS').count(),
            "pending": qs.filter(status='PENDING').count(),
            "backdated": qs.filter(reminder_date__lt=today_date).count(),
            "overdue": qs.filter(
                Q(deadline__lt=today_date) | (Q(deadline__isnull=True) & Q(reminder_date__lt=today_date))
            ).exclude(status__in=['COMPLETED', 'CANCELLED', 'PENDING_APPROVAL']).count(),
            "is_admin": is_admin,
            "my_total": Reminder.objects.filter(user=user).count(),
            "my_pending_approval": Reminder.objects.filter(user=user, status='PENDING_APPROVAL').count(),
        }

        return Response(stats)


class ReminderStaffListAPIView(APIView):
    """
    List of active staff members with roles DOCUMENTATION and OPERATION for assigning reminders.
    """
    permission_classes = [IsAuthenticated, HasRemindersAdminAccess]

    def get(self, request):
        doc_ops_roles = ['DOCUMENTATION', 'OPERATION', 'OPERATIONS', 'OPS']
        users = User.objects.filter(
            db_roles__name__in=doc_ops_roles,
            is_active=True
        ).distinct().order_by('first_name', 'last_name', 'username')

        serializer = ReminderUserBriefSerializer(users, many=True)
        return Response(serializer.data)


class ReminderStudentsListAPIView(APIView):
    """
    List of active processing students for optional linking in reminders.
    """
    permission_classes = [IsAuthenticated, HasRemindersAccess]

    def get(self, request):
        from trainers.models import ProcessingStudent
        from .serializers import ReminderProcessingStudentBriefSerializer
        q = (request.query_params.get('q') or '').strip()
        qs = ProcessingStudent.objects.all().order_by('-id')
        if q:
            qs = qs.filter(
                Q(name__icontains=q) |
                Q(mobile_number__icontains=q) |
                Q(email__icontains=q)
            )
        qs = qs[:100]
        serializer = ReminderProcessingStudentBriefSerializer(qs, many=True)
        return Response(serializer.data)
