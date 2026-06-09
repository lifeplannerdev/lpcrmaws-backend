from rest_framework import status, generics, filters
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.db.models import Count, Q, Case, When, IntegerField
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from django.utils.timezone import now
import logging

from .models import Task, TaskUpdate
from .serializers import (
    TaskSerializer,
    TaskUpdateSerializer,
    EmployeeSerializer,
    UpcomingTaskSerializer,
)
from django.contrib.auth import get_user_model
from accounts.filters import CompanyFilterBackend
from .permissions import (
    IsTaskAssigner,
    TASK_ASSIGNERS,
    TASK_ASSIGNEES,
    TOP_MANAGEMENT,
    OPERATIONS,
)

# removed duplicate local pusher definitions — import from utils (single source of truth)
from utils import notify_task_assigned, notify_task_status_updated

User = get_user_model()
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _task_queryset_for_user(user, base_qs=None):
    if base_qs is None:
        base_qs = Task.objects.select_related("assigned_to", "assigned_by")

    user_perms = getattr(user, 'permissions', []) or []

    if 'tasks:read_all' in user_perms or user.db_roles.filter(name__in=TOP_MANAGEMENT).exists():
        return base_qs

    if 'tasks:edit_any' in user_perms or user.db_roles.filter(name__in=OPERATIONS).exists():
        return base_qs.filter(
            Q(assigned_to=user) | Q(assigned_by=user)
        ).distinct()

    return base_qs.filter(assigned_to=user)


def _apply_status_ordering(qs):
    """Order tasks: OVERDUE → PENDING → IN_PROGRESS → COMPLETED → CANCELLED."""
    return qs.annotate(
        status_priority=Case(
            When(status='OVERDUE',     then=1),
            When(status='PENDING',     then=2),
            When(status='IN_PROGRESS', then=3),
            When(status='COMPLETED',   then=4),
            When(status='CANCELLED',   then=5),
            default=6,
            output_field=IntegerField(),
        )
    ).order_by('status_priority', '-created_at')


def _apply_priority_ordering(qs):
    """Order tasks: URGENT → HIGH → MEDIUM → LOW."""
    return qs.annotate(
        priority_order=Case(
            When(priority='URGENT', then=1),
            When(priority='HIGH',   then=2),
            When(priority='MEDIUM', then=3),
            When(priority='LOW',    then=4),
            default=5,
            output_field=IntegerField(),
        )
    )


# ── Pagination ────────────────────────────────────────────────────────────────

class TaskPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 50


class TaskUpdatePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ── Task Stats ────────────────────────────────────────────────────────────────

class TaskStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        qs = _task_queryset_for_user(user)
        qs = CompanyFilterBackend().filter_queryset(request, qs, self)

        # Apply month/year filters if provided
        month = request.query_params.get('month')
        year = request.query_params.get('year')
        
        if year and year != 'all':
            qs = qs.filter(created_at__year=year)
        if month and month != 'all':
            qs = qs.filter(created_at__month=month)

        user_filter = request.query_params.get('user')
        if user_filter:
            qs = qs.filter(assigned_to_id=user_filter)

        now_dt = timezone.now()
        overdue_count = qs.filter(
            Q(deadline__lt=now_dt) &
            ~Q(status='COMPLETED') &
            ~Q(status='CANCELLED')
        ).count()

        stats = qs.aggregate(
            total=Count('id'),
            pending=Count('id',     filter=Q(status='PENDING')),
            in_progress=Count('id', filter=Q(status='IN_PROGRESS')),
            completed=Count('id',   filter=Q(status='COMPLETED')),
        )
        stats['overdue'] = overdue_count

        return Response(stats)


# ── Employee List ─────────────────────────────────────────────────────────────

class EmployeeListAPIView(generics.ListAPIView):
    permission_classes = [IsTaskAssigner]
    serializer_class = EmployeeSerializer
    filter_backends = [CompanyFilterBackend]

    def get_queryset(self):
        user = self.request.user
        if user.db_roles.filter(name__in=TOP_MANAGEMENT).exists():
            return User.objects.filter(is_active=True).exclude(id=user.id)
        return User.objects.filter(
            is_active=True,
            db_roles__name__in=TASK_ASSIGNEES
        ).exclude(id=user.id)


# ── Task List / Create ────────────────────────────────────────────────────────

class TaskListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = TaskSerializer
    pagination_class = TaskPagination
    filter_backends = [filters.SearchFilter, CompanyFilterBackend]
    search_fields = ['title', 'description']

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsTaskAssigner()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = _apply_status_ordering(
            _task_queryset_for_user(self.request.user)
        )

        status_filter = self.request.query_params.get('status')
        if status_filter and status_filter != 'all':
            qs = qs.filter(status=status_filter)

        priority_filter = self.request.query_params.get('priority')
        if priority_filter and priority_filter != 'all':
            qs = qs.filter(priority=priority_filter)

        date_filter = self.request.query_params.get('date_filter')
        if date_filter and date_filter != 'all':
            if date_filter == 'today':
                qs = qs.filter(created_at__date=timezone.now().date())
            elif date_filter == 'yesterday':
                qs = qs.filter(created_at__date=timezone.now().date() - timezone.timedelta(days=1))
            else:
                # Assuming specific date format YYYY-MM-DD
                try:
                    qs = qs.filter(created_at__date=date_filter)
                except ValueError:
                    pass

        month_filter = self.request.query_params.get('month')
        if month_filter and month_filter != 'all':
            qs = qs.filter(created_at__month=month_filter)
            
        year_filter = self.request.query_params.get('year')
        if year_filter and year_filter != 'all':
            qs = qs.filter(created_at__year=year_filter)

        user_filter = self.request.query_params.get('user')
        if user_filter:
            qs = qs.filter(assigned_to_id=user_filter)

        return qs

    def perform_create(self, serializer):
        user = self.request.user
        assigned_to = serializer.validated_data.get('assigned_to')

        # OPS / CM cannot assign tasks to ADMIN or CEO
        if user.db_roles.filter(name__in=OPERATIONS).exists() and assigned_to:
            if assigned_to.db_roles.filter(name__in=TOP_MANAGEMENT).exists():
                raise ValidationError(
                    "OPS and CM can only assign tasks to execution-level employees."
                )

        task = serializer.save(assigned_by=user, company=user.company)

        # 🔔 Notify the assignee about the new task
        notify_task_assigned(task=task, assigned_by=user)


# ── Task Detail / Update / Delete ─────────────────────────────────────────────

class TaskDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return _task_queryset_for_user(self.request.user)

    def _check_edit_permission(self, task):
        user = self.request.user
        user_perms = getattr(user, 'permissions', []) or []
        
        if 'tasks:edit_any' in user_perms or user.db_roles.filter(name__in=TOP_MANAGEMENT).exists():
            return
            
        if user.db_roles.filter(name__in=OPERATIONS).exists() and task.assigned_by == user:
            return
            
        raise PermissionDenied(
            "Only the creator of this task or an authorized assigner can edit or delete it."
        )

    def update(self, request, *args, **kwargs):
        self._check_edit_permission(self.get_object())
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._check_edit_permission(self.get_object())
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self._check_edit_permission(self.get_object())
        return super().destroy(request, *args, **kwargs)

    def perform_update(self, serializer):
        task = self.get_object()
        old_status = task.status
        new_status = serializer.validated_data.get('status', old_status)

        instance = serializer.save()

        if old_status != new_status:
            TaskUpdate.objects.create(
                task=instance,
                updated_by=self.request.user,
                previous_status=old_status,
                new_status=new_status,
                notes=f"Status changed by {self.request.user.username}"
            )

        
            notify_task_status_updated(
                task=instance,
                updated_by=self.request.user,
                old_status=old_status,
                new_status=new_status,
                notes=f"Status changed by {self.request.user.username}",
            )


# ── Task Updates ─────────────────────────────────────

class TaskUpdateListCreateAPIView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TaskUpdateSerializer
    pagination_class = TaskUpdatePagination

    def _get_task(self):
        return get_object_or_404(Task, pk=self.kwargs["task_id"])

    def get_queryset(self):
        task = self._get_task()
        user = self.request.user

        if user.db_roles.filter(name__in=TOP_MANAGEMENT).exists():
            return TaskUpdate.objects.filter(task=task).select_related('updated_by').order_by("-created_at")

        if user.db_roles.filter(name__in=OPERATIONS).exists() and task.assigned_by == user:
            return TaskUpdate.objects.filter(task=task).select_related('updated_by').order_by("-created_at")

        if task.assigned_to == user:
            return TaskUpdate.objects.filter(task=task).select_related('updated_by').order_by("-created_at")

        raise PermissionDenied("You do not have access to this task.")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['task'] = self._get_task()
        return context

    def perform_create(self, serializer):
        task = self._get_task()

        if task.assigned_to != self.request.user:
            raise PermissionDenied("Only the assigned employee can post updates on this task.")

        old_status = task.status

        # Notes-only update — status changes go through /tasks/<id>/status/
        serializer.save(
            task=task,
            updated_by=self.request.user,
            previous_status=old_status,
            new_status=old_status,  # status unchanged here
        )


# ── Tasks Assigned By Me ──────────────────────────────────────────────────────

class TasksAssignedByMeAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TaskSerializer
    pagination_class = TaskPagination

    def get_queryset(self):
        user = self.request.user
        if not user.db_roles.filter(name__in=TASK_ASSIGNERS).exists():
            return Task.objects.none()
        qs = Task.objects.filter(assigned_by=user).select_related('assigned_to', 'assigned_by')
        qs = CompanyFilterBackend().filter_queryset(self.request, qs, self)
        return _apply_status_ordering(qs)


# ── Task Status Update ────────────────────────────────────────────────────────
# Single endpoint for all status changes by the assignee.

class TaskStatusUpdateAPIView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TaskUpdateSerializer

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)

        if request.user != task.assigned_to:
            return Response(
                {"detail": "Only the assigned employee can change the task status."},
                status=status.HTTP_403_FORBIDDEN
            )

        new_status = request.data.get("status")
        notes = request.data.get("notes", "").strip()

        if not new_status or new_status not in dict(Task.STATUS_CHOICES):
            return Response(
                {"detail": "Invalid or missing status."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_status == task.status:
            return Response(
                {"detail": "New status must differ from the current status."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_status in ['COMPLETED', 'CANCELLED'] and not notes:
            return Response(
                {"detail": "Notes are required when completing or cancelling a task."},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_status = task.status

        try:
            update = TaskUpdate.objects.create(
                task=task,
                updated_by=request.user,
                previous_status=old_status,
                new_status=new_status,
                notes=notes
            )
        except Exception as e:
            logger.error(f"Error creating TaskUpdate: {str(e)}", exc_info=True)
            return Response(
                {"detail": f"Failed to create update: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            task.status = new_status
            task.save(update_fields=['status', 'updated_at'])
        except Exception as e:
            logger.error(f"Error updating task status: {str(e)}", exc_info=True)
            return Response(
                {"detail": f"Failed to update task: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 🔔 Notify the task creator that status was updated
        notify_task_status_updated(
            task=task,
            updated_by=request.user,
            old_status=old_status,
            new_status=new_status,
            notes=notes,
        )

        return Response({
            "detail": "Status updated successfully",
            "update_id": update.id
        })


# ── Pending Tasks ─────────────────────────────────────────────────────────────

class PendingTasksAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        base_qs = Task.objects.filter(
            status__in=['PENDING', 'IN_PROGRESS']
        ).select_related('assigned_to', 'assigned_by')
        qs = _task_queryset_for_user(user, base_qs=base_qs)
        qs = CompanyFilterBackend().filter_queryset(request, qs, self)
        qs = _apply_priority_ordering(qs).order_by('priority_order', 'deadline')
        return Response(TaskSerializer(qs, many=True).data)


# ── Upcoming Tasks ────────────────────────────────────────────────────────────

class UpcomingTasksAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        base_qs = Task.objects.filter(deadline__gte=now()).exclude(status__in=['COMPLETED', 'CANCELLED']).select_related('assigned_to', 'assigned_by')
        qs = _task_queryset_for_user(user, base_qs=base_qs)
        qs = CompanyFilterBackend().filter_queryset(request, qs, self)
        qs = qs.order_by("deadline")[:5]
        return Response(UpcomingTaskSerializer(qs, many=True).data)
