import re
from django.utils import timezone


REMARK_AUTHOR_RE = re.compile(r'\[[^\]]+\]\s+([^:\n]+):')


def transfer_admin_owned_records(lead, counselor):
    """
    Transfer a lead and its admin-assigned pending follow-ups to a non-superuser counselor.
    Never transfers to a superuser or inactive user.
    """
    if not counselor or getattr(counselor, 'is_superuser', False) or not getattr(counselor, 'is_active', True):
        return False

    from leads.models import FollowUp, LeadAssignment

    transferred = False
    if lead is not None:
        current_assigned = lead.assigned_to
        if current_assigned is None or getattr(current_assigned, 'is_superuser', False):
            lead.assigned_to = counselor
            lead.assigned_date = timezone.now()
            lead.save(update_fields=['assigned_to', 'assigned_date'])
            LeadAssignment.objects.create(
                lead=lead,
                assigned_to=counselor,
                assigned_by=None,
                assignment_type='PRIMARY',
                notes='Auto-transferred from admin/unassigned to active counselor',
            )
            transferred = True

        updated_fu = FollowUp.objects.filter(
            lead=lead,
            status='pending',
            assigned_to__is_superuser=True,
        ).update(assigned_to=counselor)
        if updated_fu:
            transferred = True

    return transferred


def find_user_by_display_name(name, User):
    """Match an active non-superuser by full name or username."""
    cleaned = (name or '').strip()
    if not cleaned:
        return None
    lower_target = cleaned.lower()
    for user in User.objects.filter(is_active=True, is_superuser=False):
        full_name = f"{user.first_name} {user.last_name}".strip().lower()
        if full_name == lower_target or (user.username or '').lower() == lower_target:
            return user
    return None


def resolve_counselor_from_context(lead=None, notes='', User=None, RemarkHistory=None, LeadAssignment=None):
    """Find the active non-superuser counselor who owns or interacted with a lead/follow-up."""
    if User is None:
        from accounts.models import User as DefaultUser
        User = DefaultUser
    if RemarkHistory is None:
        from leads.models import RemarkHistory as DefaultRH
        RemarkHistory = DefaultRH
    if LeadAssignment is None:
        from leads.models import LeadAssignment as DefaultLA
        LeadAssignment = DefaultLA

    if lead is not None:
        for candidate in (getattr(lead, 'sub_assigned_to', None), getattr(lead, 'assigned_to', None)):
            if candidate and candidate.is_active and not candidate.is_superuser:
                return candidate

        remark = (
            RemarkHistory.objects.filter(
                lead=lead,
                changed_by__isnull=False,
                changed_by__is_active=True,
                changed_by__is_superuser=False,
            )
            .select_related('changed_by')
            .order_by('-changed_at', '-id')
            .first()
        )
        if remark:
            return remark.changed_by

        assignment = (
            LeadAssignment.objects.filter(
                lead=lead,
                assigned_to__isnull=False,
                assigned_to__is_active=True,
                assigned_to__is_superuser=False,
            )
            .select_related('assigned_to')
            .order_by('-timestamp', '-id')
            .first()
        )
        if assignment:
            return assignment.assigned_to

    for text in (notes or '', getattr(lead, 'remarks', '') or ''):
        for match in REMARK_AUTHOR_RE.finditer(text):
            matched_user = find_user_by_display_name(match.group(1), User)
            if matched_user:
                return matched_user

    return None
