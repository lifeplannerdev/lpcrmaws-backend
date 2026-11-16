import re
from django.db import migrations
from django.db.models import Q
from django.utils import timezone


def prune_non_command_centre_batches(apps, schema_editor):
    Lead = apps.get_model('leads', 'Lead')
    LeadAssignment = apps.get_model('leads', 'LeadAssignment')
    LeadAssignmentBatch = apps.get_model('leads', 'LeadAssignmentBatch')

    valid_batch_ids = set(
        LeadAssignment.objects.filter(
            batch__isnull=False,
            assigned_by__isnull=False,
        )
        .filter(
            Q(notes__icontains='Transferred from')
            | Q(notes__icontains='Command Centre')
            | Q(notes='Bulk Reassigned')
        )
        .values_list('batch_id', flat=True)
        .distinct()
    )

    Lead.objects.exclude(current_assignment_batch_id__in=valid_batch_ids).update(current_assignment_batch=None)
    LeadAssignment.objects.exclude(batch_id__in=valid_batch_ids).update(batch=None)
    LeadAssignmentBatch.objects.exclude(id__in=valid_batch_ids).delete()

    for batch in LeadAssignmentBatch.objects.filter(id__in=valid_batch_ids):
        sample_notes = list(
            LeadAssignment.objects.filter(batch_id=batch.id).values_list('notes', flat=True)[:50]
        )
        prev_owners = []
        seen = set()
        for note in sample_notes:
            for match in re.findall(r'\[Transferred from ([^\]]+)\]', note or ''):
                name = match.strip()
                if name and name not in seen:
                    seen.add(name)
                    prev_owners.append(name)

        if len(prev_owners) == 1:
            source_summary = f"From {prev_owners[0]}"
        elif len(prev_owners) > 1:
            preview = ", ".join(prev_owners[:2])
            extra = f" +{len(prev_owners) - 2} more" if len(prev_owners) > 2 else ""
            source_summary = f"From {preview}{extra}"
        else:
            source_summary = batch.source_summary or "Manual Command Centre Transfer"

        clean_note = re.sub(r'\s*\[Transferred from [^\]]+\]', '', batch.notes or '').strip()
        ts_label = timezone.localtime(batch.created_at).strftime('%d %b %Y, %I:%M %p')
        noun = 'lead' if batch.total_leads_count == 1 else 'leads'
        new_title = f"{batch.total_leads_count} {noun} ({source_summary}) · {ts_label}"

        batch.source_type = 'BULK_REASSIGN' if batch.notes == 'Bulk Reassigned' else 'COMMAND_CENTRE'
        batch.source_summary = source_summary[:255]
        batch.title = new_title[:255]
        batch.notes = clean_note
        batch.save(update_fields=['source_type', 'source_summary', 'title', 'notes'])


class Migration(migrations.Migration):

    dependencies = [
        ('leads', '0003_leadassignmentbatch_source_type'),
    ]

    operations = [
        migrations.RunPython(prune_non_command_centre_batches, migrations.RunPython.noop),
    ]
