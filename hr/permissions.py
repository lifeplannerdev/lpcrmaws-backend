from rest_framework.permissions import BasePermission
from accounts.permissions import has_dynamic_permission

class HasPenaltyPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return has_dynamic_permission(request.user, 'penalties:read_any') or \
                   has_dynamic_permission(request.user, 'penalties:read_tenant') or \
                   has_dynamic_permission(request.user, 'penalties:read_own')
        elif request.method == 'POST':
            return has_dynamic_permission(request.user, 'penalties:create')
        else:
            return has_dynamic_permission(request.user, 'penalties:edit_any') or \
                   has_dynamic_permission(request.user, 'penalties:edit_tenant') or \
                   has_dynamic_permission(request.user, 'penalties:delete_any')


class HasStaffPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return has_dynamic_permission(request.user, 'staff:read_any') or \
                   has_dynamic_permission(request.user, 'staff:read_tenant') or \
                   has_dynamic_permission(request.user, 'staff:read_own')
        elif request.method == 'POST':
            return has_dynamic_permission(request.user, 'staff:create')
        else:
            return has_dynamic_permission(request.user, 'staff:edit_any') or \
                   has_dynamic_permission(request.user, 'staff:edit_tenant') or \
                   has_dynamic_permission(request.user, 'staff:delete_any')


class HasAttendancePermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return has_dynamic_permission(request.user, 'attendance:read_any') or \
                   has_dynamic_permission(request.user, 'attendance:read_tenant') or \
                   has_dynamic_permission(request.user, 'attendance:read_own')
        elif request.method == 'POST':
            return has_dynamic_permission(request.user, 'attendance:create_any') or \
                   has_dynamic_permission(request.user, 'attendance:create') or \
                   has_dynamic_permission(request.user, 'attendance:create_own')
        else:
            return has_dynamic_permission(request.user, 'attendance:edit_any') or \
                   has_dynamic_permission(request.user, 'attendance:edit_tenant')


class HasCandidatePermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return has_dynamic_permission(request.user, 'candidates:read_any') or \
                   has_dynamic_permission(request.user, 'candidates:read_tenant')
        elif request.method == 'POST':
            return has_dynamic_permission(request.user, 'candidates:create')
        else:
            return has_dynamic_permission(request.user, 'candidates:edit_any') or \
                   has_dynamic_permission(request.user, 'candidates:delete_any')


class HasAssetPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
            
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return has_dynamic_permission(request.user, 'assets:read_any') or \
                   has_dynamic_permission(request.user, 'assets:read_tenant') or \
                   has_dynamic_permission(request.user, 'assets:read_own')
        elif request.method == 'POST':
            return has_dynamic_permission(request.user, 'assets:create')
        else:
            return has_dynamic_permission(request.user, 'assets:edit_any') or \
                   has_dynamic_permission(request.user, 'assets:edit_tenant') or \
                   has_dynamic_permission(request.user, 'assets:delete_any')
