from rest_framework import viewsets, permissions
from rest_framework.exceptions import PermissionDenied
from .models import Program, ProgramCountry, ProgramUniversity, ProgramIntake
from .serializers import ProgramSerializer, ProgramCountrySerializer, ProgramUniversitySerializer, ProgramIntakeSerializer

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

