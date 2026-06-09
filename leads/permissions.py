from rest_framework.permissions import BasePermission


FULL_ACCESS_ROLES = ['ADMIN', 'CEO', 'OPS']


MANAGER_ROLES = [
    'ADM_MANAGER',
    'ADM_COUNSELLOR',
    'CM',
    'BDM',
]


EXECUTIVE_ROLES = [
    'ADM_EXEC',
    'FOE',
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


class CanAccessLeads(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            'leads:read_tenant' in request.user.permissions
        )


class CanAssignLeads(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return (
            user.is_authenticated and
            'leads:read_tenant' in user.permissions
        )


class CanViewAllLeads(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            'leads:read_tenant' in request.user.permissions
        )


class CanModifyAllLeads(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            'staff:read_tenant' in request.user.permissions
        )


class CanManageConversion(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            'leads:read_tenant' in request.user.permissions
        )
