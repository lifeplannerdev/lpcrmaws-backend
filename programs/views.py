from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from .models import (
    Program,
    ProgramCountry,
    ProgramUniversity,
    ProgramIntake,
    AssignedProgram,
    AssignedProgramChangeLog,
    AssignedStudentRecord,
    AssignedStudentChangeLog,
)
from .permissions import HasProgStudAccess, CanManageProgStud, is_prog_stud_manager
from .serializers import (
    ProgramSerializer,
    ProgramCountrySerializer,
    ProgramUniversitySerializer,
    ProgramIntakeSerializer,
    AssignedProgramSerializer,
    AssignedProgramChangeLogSerializer,
    AssignedStudentRecordSerializer,
    AssignedStudentChangeLogSerializer,
)

User = get_user_model()

def _has_perm(user, perm):
    if user.is_superuser:
        return True
    
    permissions_list = []
    # Pre-load permissions via db_roles
    for role in user.db_roles.prefetch_related('permissions').all():
        for p in role.permissions.all():
            permissions_list.append(p.name)

    # Include user-specific JSON permissions
    if hasattr(user, 'permissions') and isinstance(user.permissions, list):
        permissions_list.extend(user.permissions)
        
    # Superuser wildcard in JSON
    if "*" in permissions_list or "*:*" in permissions_list:
        return True
        
    resource, action = perm.split(':')
    wildcard_perm = f"{resource}:*"
    
    return perm in permissions_list or wildcard_perm in permissions_list


class ProgramPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        if view.action in ['list', 'retrieve']:
            return _has_perm(request.user, 'programs:view') or _has_perm(request.user, 'programs:manage')
        else:
            return _has_perm(request.user, 'programs:manage')

class ProgramViewSet(viewsets.ModelViewSet):
    serializer_class = ProgramSerializer
    permission_classes = [ProgramPermission]

    def get_queryset(self):
        qs = Program.objects.all().order_by('-created_at')
        if not self.request.user.is_superuser:
            # Also check if they have manage permission
            if not _has_perm(self.request.user, 'programs:manage'):
                qs = qs.filter(is_hidden=False)
        return qs

class ProgramCountryViewSet(viewsets.ModelViewSet):
    queryset = ProgramCountry.objects.all().order_by('name')
    serializer_class = ProgramCountrySerializer
    permission_classes = [ProgramPermission]

class ProgramUniversityViewSet(viewsets.ModelViewSet):
    queryset = ProgramUniversity.objects.all().order_by('name')
    serializer_class = ProgramUniversitySerializer
    permission_classes = [ProgramPermission]

class ProgramIntakeViewSet(viewsets.ModelViewSet):
    queryset = ProgramIntake.objects.all().order_by('name')
    serializer_class = ProgramIntakeSerializer
    permission_classes = [ProgramPermission]


def _format_field_val(instance, field_name):
    val = getattr(instance, field_name, '')
    if field_name == 'assigned_to':
        if not val:
            return 'Unassigned'
        return val.get_full_name().strip() or val.username
    return '' if val is None else str(val)


class AssignedTrackerBaseViewSet(viewsets.ModelViewSet):
    """Shared ViewSet implementing strict manage vs assigned RBAC, change timelines, bulk assign, and bulk import."""
    log_model = None
    log_serializer_class = None
    log_fk_field = None
    field_labels = {}
    search_fields = []

    def get_permissions(self):
        if self.action in ['create', 'destroy', 'bulk_assign', 'bulk_import']:
            return [CanManageProgStud()]
        return [HasProgStudAccess()]

    def get_queryset(self):
        qs = self.queryset.select_related('assigned_to', 'created_by')
        user = self.request.user
        if not is_prog_stud_manager(user):
            qs = qs.filter(assigned_to=user)
        else:
            assigned_to_param = self.request.query_params.get('assigned_to')
            if assigned_to_param == 'unassigned':
                qs = qs.filter(assigned_to__isnull=True)
            elif assigned_to_param and assigned_to_param != 'all':
                qs = qs.filter(assigned_to_id=assigned_to_param)

        search = (self.request.query_params.get('search') or '').strip()
        if search and self.search_fields:
            q_obj = Q()
            for field in self.search_fields:
                q_obj |= Q(**{f"{field}__icontains": search})
            qs = qs.filter(q_obj)

        return qs

    def _next_sl_no(self):
        max_sl = self.queryset.aggregate(m=Max('sl_no'))['m'] or 0
        return max_sl + 1

    def _log_entries(self, instance, entries):
        if not entries:
            return
        objs = [
            self.log_model(**{self.log_fk_field: instance}, **entry)
            for entry in entries
        ]
        self.log_model.objects.bulk_create(objs)

    def perform_create(self, serializer):
        sl_no = serializer.validated_data.get('sl_no') or self._next_sl_no()
        instance = serializer.save(created_by=self.request.user, sl_no=sl_no)
        entries = [
            {
                'action': 'CREATED',
                'field_name': '',
                'field_label': 'Record',
                'old_value': '',
                'new_value': str(instance),
                'changed_by': self.request.user,
            }
        ]
        if instance.assigned_to:
            entries.append(
                {
                    'action': 'ASSIGNED',
                    'field_name': 'assigned_to',
                    'field_label': 'Assigned To',
                    'old_value': 'Unassigned',
                    'new_value': _format_field_val(instance, 'assigned_to'),
                    'changed_by': self.request.user,
                }
            )
        self._log_entries(instance, entries)

    def update(self, request, *args, **kwargs):
        if not is_prog_stud_manager(request.user) and 'assigned_to' in request.data:
            raise PermissionDenied('Only managers can reassign rows.')
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        tracked_fields = list(self.field_labels.keys())
        old_snapshot = {f: _format_field_val(instance, f) for f in tracked_fields}

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        instance.refresh_from_db()

        entries = []
        for field in tracked_fields:
            old_val = old_snapshot[field]
            new_val = _format_field_val(instance, field)
            if old_val != new_val:
                entries.append(
                    {
                        'action': 'ASSIGNED' if field == 'assigned_to' else 'UPDATED',
                        'field_name': field,
                        'field_label': self.field_labels[field],
                        'old_value': old_val,
                        'new_value': new_val,
                        'changed_by': request.user,
                    }
                )
        self._log_entries(instance, entries)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='timeline')
    def timeline(self, request, pk=None):
        instance = self.get_object()
        logs = self.log_model.objects.filter(**{self.log_fk_field: instance}).select_related('changed_by')
        return Response(self.log_serializer_class(logs, many=True).data)

    @action(detail=False, methods=['post'], url_path='bulk-assign')
    def bulk_assign(self, request):
        ids = request.data.get('ids') or []
        assigned_to_id = request.data.get('assigned_to')
        if not isinstance(ids, list) or not ids:
            return Response({'error': 'ids list is required.'}, status=status.HTTP_400_BAD_REQUEST)

        assignee = None
        if assigned_to_id:
            try:
                assignee = User.objects.get(id=assigned_to_id, is_active=True)
            except (User.DoesNotExist, TypeError, ValueError):
                return Response({'error': 'Valid active assignee is required.'}, status=status.HTTP_400_BAD_REQUEST)

        new_label = assignee.get_full_name().strip() or assignee.username if assignee else 'Unassigned'
        rows = list(self.queryset.filter(id__in=ids).select_related('assigned_to'))

        with transaction.atomic():
            logs = []
            for row in rows:
                old_label = _format_field_val(row, 'assigned_to')
                if old_label == new_label:
                    continue
                row.assigned_to = assignee
                logs.append(
                    self.log_model(
                        **{self.log_fk_field: row},
                        action='ASSIGNED',
                        field_name='assigned_to',
                        field_label='Assigned To',
                        old_value=old_label,
                        new_value=new_label,
                        changed_by=request.user,
                    )
                )
            if rows:
                self.queryset.model.objects.bulk_update(rows, ['assigned_to'])
            if logs:
                self.log_model.objects.bulk_create(logs)

        return Response({'updated_count': len(rows)})

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        rows = request.data.get('rows') or []
        default_assigned_to_id = request.data.get('default_assigned_to')
        if not isinstance(rows, list) or not rows:
            return Response({'error': 'rows list is required.'}, status=status.HTTP_400_BAD_REQUEST)

        default_assignee = None
        if default_assigned_to_id:
            try:
                default_assignee = User.objects.get(id=default_assigned_to_id, is_active=True)
            except (User.DoesNotExist, TypeError, ValueError):
                return Response({'error': 'Invalid default assignee.'}, status=status.HTTP_400_BAD_REQUEST)

        created_instances = []
        next_sl = self._next_sl_no()

        with transaction.atomic():
            for raw_row in rows:
                payload = dict(raw_row)
                if not payload.get('sl_no'):
                    payload['sl_no'] = next_sl
                    next_sl += 1
                if not payload.get('assigned_to') and default_assignee:
                    payload['assigned_to'] = default_assignee.id

                ser = self.get_serializer(data=payload)
                ser.is_valid(raise_exception=True)
                inst = ser.save(created_by=request.user)
                created_instances.append(inst)
                entries = [
                    {
                        'action': 'CREATED',
                        'field_name': '',
                        'field_label': 'Imported Row',
                        'old_value': '',
                        'new_value': str(inst),
                        'changed_by': request.user,
                    }
                ]
                if inst.assigned_to:
                    entries.append(
                        {
                            'action': 'ASSIGNED',
                            'field_name': 'assigned_to',
                            'field_label': 'Assigned To',
                            'old_value': 'Unassigned',
                            'new_value': _format_field_val(inst, 'assigned_to'),
                            'changed_by': request.user,
                        }
                    )
                self._log_entries(inst, entries)

        return Response(
            {
                'created_count': len(created_instances),
                'rows': self.get_serializer(created_instances, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class AssignedProgramViewSet(AssignedTrackerBaseViewSet):
    queryset = AssignedProgram.objects.all().order_by('sl_no', 'id')
    serializer_class = AssignedProgramSerializer
    log_model = AssignedProgramChangeLog
    log_serializer_class = AssignedProgramChangeLogSerializer
    log_fk_field = 'program'
    search_fields = ['project', 'country', 'assignment', 'completed', 'presentation', 'training_to_team']
    field_labels = {
        'sl_no': 'SL.NO.',
        'project': 'PROJECT',
        'country': 'COUNTRY',
        'assignment': 'ASSIGNMENT',
        'completed': 'COMPLETED',
        'presentation': 'PRESENTATION',
        'training_to_team': 'TRAINING TO TEAM',
        'assigned_to': 'Assigned To',
    }


class AssignedStudentRecordViewSet(AssignedTrackerBaseViewSet):
    queryset = AssignedStudentRecord.objects.all().order_by('sl_no', 'id')
    serializer_class = AssignedStudentRecordSerializer
    log_model = AssignedStudentChangeLog
    log_serializer_class = AssignedStudentChangeLogSerializer
    log_fk_field = 'student_record'
    search_fields = [
        'name', 'phone', 'email_address', 'place',
        'qualification', 'preferred_country', 'preferred_program',
        'intake', 'aps_status', 'ielts_status', 'german_status', 'source',
    ]
    field_labels = {
        'sl_no': 'SL NO',
        'name': 'NAME',
        'age': 'AGE',
        'phone': 'PHONE',
        'email_address': 'EMAIL ADDRESS',
        'place': 'PLACE',
        'qualification': 'QUALIFICATION',
        'preferred_country': 'PREFERRED COUNTRY',
        'preferred_program': 'PREFERRED PROGRAM',
        'intake': 'INTAKE',
        'aps_status': 'APS STATUS',
        'ielts_status': 'IELTS STATUS',
        'german_status': 'GERMAN STATUS',
        'source': 'SOURCE',
        'assigned_to': 'Assigned To',
    }

