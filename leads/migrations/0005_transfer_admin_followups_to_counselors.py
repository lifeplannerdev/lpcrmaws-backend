from django.db import migrations
from leads.assignment_utils import resolve_counselor_from_context


def transfer_admin_assignments(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    FollowUp = apps.get_model('leads', 'FollowUp')
    Lead = apps.get_model('leads', 'Lead')
    RemarkHistory = apps.get_model('leads', 'RemarkHistory')
    LeadAssignment = apps.get_model('leads', 'LeadAssignment')

    admin_followups = FollowUp.objects.filter(assigned_to__is_superuser=True).select_related(
        'lead', 'lead__assigned_to', 'lead__sub_assigned_to'
    )
    for fu in admin_followups:
        counselor = resolve_counselor_from_context(
            lead=fu.lead,
            notes=fu.notes or '',
            User=User,
            RemarkHistory=RemarkHistory,
            LeadAssignment=LeadAssignment,
        )
        if counselor:
            fu.assigned_to = counselor
            fu.save(update_fields=['assigned_to'])
            if fu.lead_id and (fu.lead.assigned_to is None or fu.lead.assigned_to.is_superuser):
                fu.lead.assigned_to = counselor
                fu.lead.save(update_fields=['assigned_to'])

    admin_leads = Lead.objects.filter(assigned_to__is_superuser=True).select_related('sub_assigned_to')
    for lead in admin_leads:
        counselor = resolve_counselor_from_context(
            lead=lead,
            notes=lead.remarks or '',
            User=User,
            RemarkHistory=RemarkHistory,
            LeadAssignment=LeadAssignment,
        )
        lead.assigned_to = counselor
        lead.save(update_fields=['assigned_to'])


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0004_prune_non_command_centre_batches'),
    ]

    operations = [
        migrations.RunPython(transfer_admin_assignments, migrations.RunPython.noop),
    ]
