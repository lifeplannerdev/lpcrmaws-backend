from accounts.permissions import has_dynamic_permission
from rest_framework.permissions import BasePermission


FULL_ACCESS_ROLES = ['ADMIN', 'CEO', 'OPS', 'OPERATION', 'BUSINESS_HEAD', 'MANAGING_DIRECTOR', 'managing_director']


MANAGER_ROLES = [
    'ADM_MANAGER',
    'SENIOR ADM',
    'SENIOR_ADM',
    'ADM_COUNSELLOR',
    'CM',
    'BDM',
    'BMCO',
]


EXECUTIVE_ROLES = [
    'ADM_EXEC',
    'FOE',
    'EXEC',
]


NON_LEAD_ROLES = [
    'PROCESSING',
    'MEDIA',
    'TRAINER',
    'HR',
    'ACCOUNTS',
    'DOCUMENTATION'
]

LEAD_ACCESS_ROLES = FULL_ACCESS_ROLES + MANAGER_ROLES + EXECUTIVE_ROLES


LEAD_VIEW_ALL_ROLES = FULL_ACCESS_ROLES

def is_full_access(user):
    return (
        user.is_superuser or
        has_dynamic_permission(user, 'leads:read_any') or
        has_dynamic_permission(user, 'leads:read_tenant') or
        user.db_roles.filter(name__in=FULL_ACCESS_ROLES).exists()
    )

def is_full_access_or_manager(user):
    return (
        is_full_access(user) or
        has_dynamic_permission(user, 'staff_analysis:admin') or
        user.db_roles.filter(name__in=MANAGER_ROLES + ['SENIOR ADM', 'SENIOR_ADM']).exists()
    )


class CanAccessLeads(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            (has_dynamic_permission(request.user, 'leads:read_any') or
             has_dynamic_permission(request.user, 'leads:read_tenant') or
             has_dynamic_permission(request.user, 'leads:read_own') or
             has_dynamic_permission(request.user, 'staff_analysis:admin'))
        )


class CanAssignLeads(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return (
            user.is_authenticated and
            (has_dynamic_permission(user, 'leads:read_tenant') or 
             has_dynamic_permission(user, 'leads:read_any') or
             has_dynamic_permission(user, 'leads:edit_tenant') or
             has_dynamic_permission(user, 'staff_analysis:admin'))
        )


class CanViewAllLeads(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            (has_dynamic_permission(request.user, 'leads:read_tenant') or
             has_dynamic_permission(request.user, 'leads:read_any'))
        )


class CanModifyAllLeads(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            has_dynamic_permission(request.user, 'staff:read_tenant')
        )


class CanManageConversion(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            has_dynamic_permission(request.user, 'leads:read_tenant')
        )
