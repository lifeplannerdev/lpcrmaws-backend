from rest_framework.permissions import BasePermission


def _has_perm(user, perm):
    return user.is_authenticated and perm in (user.permissions or [])


class CanViewFees(BasePermission):
    def has_permission(self, request, view):
        return _has_perm(request.user, 'view_fees') or _has_perm(request.user, 'manage_fees') or _has_perm(request.user, 'view_fee_reports')


class CanManageFees(BasePermission):
    def has_permission(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return _has_perm(request.user, 'view_fees') or _has_perm(request.user, 'manage_fees') or _has_perm(request.user, 'view_fee_reports')
        return _has_perm(request.user, 'manage_fees')


class CanRestructureFees(BasePermission):
    def has_permission(self, request, view):
        return _has_perm(request.user, 'restructure_fees') or _has_perm(request.user, 'manage_fees')


class CanRecordPartialPayment(BasePermission):
    def has_permission(self, request, view):
        return _has_perm(request.user, 'record_partial_payment') or _has_perm(request.user, 'manage_fees')


class CanIssueFeeNotice(BasePermission):
    def has_permission(self, request, view):
        return _has_perm(request.user, 'issue_fee_notice') or _has_perm(request.user, 'manage_fees')
