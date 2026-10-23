from accounts.permissions import has_dynamic_permission
from rest_framework.permissions import BasePermission


def _has_perm(user, perm):
    return user.is_authenticated and has_dynamic_permission(user, perm)


def is_trainer_user(user):
    """
    Returns True if user has the TRAINER role (or flag:trainer permission)
    and does NOT possess administrative / finance override permissions
    (flag:admin, fees:manage, or superuser).
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return False
    if _has_perm(user, 'flag:admin') or _has_perm(user, 'fees:manage'):
        return False
    if hasattr(user, 'db_roles') and user.db_roles.filter(name__iexact='TRAINER').exists():
        return True
    if _has_perm(user, 'flag:trainer'):
        return True
    return False


class CanViewFees(BasePermission):
    def has_permission(self, request, view):
        return (
            _has_perm(request.user, 'fees:read_tenant') or 
            _has_perm(request.user, 'fees:manage') or 
            _has_perm(request.user, 'fees:view_reports') or 
            _has_perm(request.user, 'fees:read_own') or
            _has_perm(request.user, 'flag:admin') or
            _has_perm(request.user, 'flag:fees') or
            _has_perm(request.user, 'flag:view') or
            (hasattr(request.user, 'db_roles') and request.user.db_roles.filter(name__iexact='TRAINER').exists())
        )


class CanManageFees(BasePermission):
    def has_permission(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return _has_perm(request.user, 'fees:read_tenant') or _has_perm(request.user, 'fees:manage') or _has_perm(request.user, 'fees:view_reports') or _has_perm(request.user, 'fees:read_own')
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


def _can_manage_receipt_admin_actions(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if is_trainer_user(user):
        return False
    return (
        _has_perm(user, 'fees:manage') or
        _has_perm(user, 'flag:admin') or
        _has_perm(user, 'flag:fees')
    )


def _can_view_fee_account(user, account):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if (
        getattr(user, 'is_superuser', False) or
        _has_perm(user, 'fees:read_tenant') or
        _has_perm(user, 'fees:view_reports') or
        _has_perm(user, 'fees:manage') or
        _has_perm(user, 'flag:admin') or
        _has_perm(user, 'flag:fees')
    ):
        return True
    if not account:
        return False
    student = getattr(account, 'student', None)
    if not student:
        return False
    if getattr(student, 'trainer_id', None) == user.id:
        return True
    batch = getattr(student, 'batch', None)
    if batch and getattr(batch, 'trainer_id', None) == user.id:
        return True
    return hasattr(user, 'trainer_profile') and student.trainer_id == user.trainer_profile.id


class CanManageReceipts(BasePermission):
    def has_permission(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return CanViewFees().has_permission(request, view)

        # WRITE actions (create, edit, update, delete, void) are strictly denied for trainers
        if is_trainer_user(request.user):
            return False

        return (
            _can_manage_receipt_admin_actions(request.user) or
            _has_perm(request.user, 'fees:partial_payment')
        )
