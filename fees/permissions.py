from rest_framework.permissions import BasePermission


def _has_perm(user, perm):
    return user.is_authenticated and has_dynamic_permission(user, perm)


class CanViewFees(BasePermission):
    def has_permission(self, request, view):
        return _has_perm(request.user, 'fees:read_tenant') or _has_perm(request.user, 'fees:manage') or _has_perm(request.user, 'fees:view_reports')


class CanManageFees(BasePermission):
    def has_permission(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return _has_perm(request.user, 'fees:read_tenant') or _has_perm(request.user, 'fees:manage') or _has_perm(request.user, 'fees:view_reports')
        return _has_perm(request.user, 'fees:manage')


class CanRestructureFees(BasePermission):
    def has_permission(self, request, view):
        return _has_perm(request.user, 'fees:restructure') or _has_perm(request.user, 'fees:manage')


class CanRecordPartialPayment(BasePermission):
    def has_permission(self, request, view):
        return _has_perm(request.user, 'fees:partial_payment') or _has_perm(request.user, 'fees:manage')


class CanIssueFeeNotice(BasePermission):
    def has_permission(self, request, view):
        return _has_perm(request.user, 'fees:issue_notice') or _has_perm(request.user, 'fees:manage')

