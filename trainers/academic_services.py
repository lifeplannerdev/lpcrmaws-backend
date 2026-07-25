from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    AcademicBatch,
    AcademicPackage,
    CourseLevel,
    ExamResult,
    StudentAcademicPlacement,
    StudentPackageEnrollment,
    StudentTimeline,
)


class AcademicWorkflowError(Exception):
    """A domain validation error that API views can safely return to clients."""


def _timeline(student, event_type, description, actor=None):
    StudentTimeline.objects.create(
        student=student,
        event_type=event_type,
        description=description,
        created_by=actor,
    )


def get_active_package_enrollment(student, *, for_update=False):
    queryset = StudentPackageEnrollment.objects.select_related(
        'package', 'package__minimum_level', 'package__maximum_level'
    ).filter(student=student, status='ACTIVE')
    if for_update:
        queryset = queryset.select_for_update()
    enrollment = queryset.first()
    if not enrollment:
        raise AcademicWorkflowError('Student has no active academic package.')
    return enrollment


def get_active_placement(student, *, for_update=False):
    queryset = StudentAcademicPlacement.objects.select_related(
        'academic_batch', 'academic_batch__branch', 'level', 'package_enrollment__package'
    ).filter(student=student, status='ACTIVE')
    if for_update:
        queryset = queryset.select_for_update()
    return queryset.first()


def _assert_eligible(student, academic_batch, level, package_enrollment):
    if student.company != 'FLAG':
        raise AcademicWorkflowError('Academic batches are available only for FLAG students.')
    if not student.branch_id or student.branch_id != academic_batch.branch_id:
        raise AcademicWorkflowError('Student and academic batch must belong to the same branch.')
    if package_enrollment.student_id != student.id:
        raise AcademicWorkflowError('Academic package enrollment does not belong to this student.')
    if not package_enrollment.package.allows_level(level):
        raise AcademicWorkflowError(
            f'{level.name} is outside the student\'s {package_enrollment.package.name} package.'
        )


def _sync_student_current_placement(student, placement=None, *, inactive_status=None):
    """Keep legacy student fields as projections of the immutable placement record."""
    update_fields = ['academic_batch', 'current_level', 'batch', 'status']
    if placement:
        student.academic_batch = placement.academic_batch
        student.current_level = placement.level
        student.batch = placement.level.name
        student.status = 'ACTIVE'
    else:
        student.academic_batch = None
        if inactive_status:
            student.status = inactive_status
    student.save(update_fields=update_fields)


def _create_placement(student, academic_batch, level, package_enrollment, *, entry_reason, effective_date):
    _assert_eligible(student, academic_batch, level, package_enrollment)
    if get_active_placement(student, for_update=True):
        raise AcademicWorkflowError('Student already has an active academic placement.')
    placement = StudentAcademicPlacement.objects.create(
        student=student,
        academic_batch=academic_batch,
        level=level,
        package_enrollment=package_enrollment,
        entry_reason=entry_reason,
        entered_on=effective_date,
    )
    _sync_student_current_placement(student, placement)
    return placement


def _close_placement(placement, *, exit_reason, effective_date):
    if effective_date <= placement.entered_on:
        raise AcademicWorkflowError('Effective date must be after the placement start date.')

    placement.status = 'CLOSED'
    placement.exit_reason = exit_reason
    # The new placement begins on effective_date, so the closed placement ends
    # on the preceding date.  This keeps date-based attendance unambiguous.
    placement.exited_on = effective_date - timedelta(days=1)
    placement.save(update_fields=['status', 'exit_reason', 'exited_on', 'updated_at'])


def create_initial_academic_enrollment(student, package, academic_batch, *, actor=None, effective_date=None):
    effective_date = effective_date or timezone.localdate()
    if not package.is_active:
        raise AcademicWorkflowError('Selected academic package is inactive.')
    if academic_batch.starting_level_id is None or academic_batch.branch_id is None:
        raise AcademicWorkflowError('Academic batch must have a starting level and branch.')

    with transaction.atomic():
        package_enrollment = StudentPackageEnrollment.objects.create(
            student=student,
            package=package,
            started_on=effective_date,
            assigned_by=actor,
        )
        placement = _create_placement(
            student,
            academic_batch,
            academic_batch.starting_level,
            package_enrollment,
            entry_reason='INITIAL',
            effective_date=effective_date,
        )
        _timeline(
            student,
            'BATCH_ASSIGNMENT',
            f'Initially enrolled in {academic_batch.name} at {academic_batch.starting_level.name} under {package.name}.',
            actor,
        )
    return placement


def upgrade_academic_package(student, package, *, actor=None, effective_date=None):
    effective_date = effective_date or timezone.localdate()
    if not package.is_active:
        raise AcademicWorkflowError('Selected academic package is inactive.')

    with transaction.atomic():
        current = get_active_package_enrollment(student, for_update=True)
        current.status = 'REPLACED'
        current.ended_on = effective_date
        current.save(update_fields=['status', 'ended_on'])
        replacement = StudentPackageEnrollment.objects.create(
            student=student,
            package=package,
            started_on=effective_date,
            assigned_by=actor,
        )

        resumed_placement = None
        if student.status == 'AWAITING_PACKAGE_UPGRADE':
            completed_placement = StudentAcademicPlacement.objects.select_related(
                'academic_batch', 'level'
            ).filter(
                student=student,
                status='CLOSED',
                exit_reason='PACKAGE_COMPLETE',
            ).order_by('-exited_on', '-id').first()
            if not completed_placement:
                raise AcademicWorkflowError('No package-complete placement is available to resume.')
            next_level = CourseLevel.objects.filter(
                order__gt=completed_placement.level.order
            ).order_by('order').first()
            if not next_level:
                raise AcademicWorkflowError('Student has already completed the highest academic grade.')
            resumed_placement = _create_placement(
                student,
                completed_placement.academic_batch,
                next_level,
                replacement,
                entry_reason='PACKAGE_UPGRADE',
                effective_date=effective_date,
            )

        _timeline(
            student,
            'PACKAGE_UPGRADE',
            f'Academic package changed from {current.package.name} to {package.name}.',
            actor,
        )
    return replacement, resumed_placement


def finalize_batch_level(academic_batch, level, *, actor=None, effective_date=None):
    effective_date = effective_date or timezone.localdate()
    with transaction.atomic():
        placements = list(StudentAcademicPlacement.objects.select_for_update().select_related(
            'student', 'academic_batch', 'level'
        ).filter(
            academic_batch=academic_batch,
            level=level,
            status='ACTIVE',
        ).order_by('student__name', 'id'))

        if not placements:
            return {'processed': [], 'already_finalized': True}

        results = {
            result.placement_id: result
            for result in ExamResult.objects.select_for_update().filter(
                placement__in=placements,
                exam_type='FINAL',
            )
        }
        incomplete = [
            placement.id for placement in placements
            if placement.id not in results or results[placement.id].outcome == 'PENDING'
        ]
        if incomplete:
            raise AcademicWorkflowError(
                f'Every active student in {academic_batch.name} / {level.name} needs a final PASS or FAIL outcome before finalization. '
                f'Missing placement IDs: {incomplete}'
            )

        processed = []
        for placement in placements:
            result = results[placement.id]
            student = placement.student
            action = None

            if result.outcome == 'FAIL':
                _close_placement(placement, exit_reason='FAILED', effective_date=effective_date)
                _sync_student_current_placement(student, inactive_status='AWAITING_REPEAT_TRANSFER')
                _timeline(
                    student,
                    'EXAM_FINALIZED',
                    f'Final exam failed at {level.name}; repeat transfer is required.',
                    actor,
                )
                action = 'AWAITING_REPEAT_TRANSFER'
            else:
                next_level = CourseLevel.objects.filter(order__gt=level.order).order_by('order').first()
                if not next_level:
                    _close_placement(placement, exit_reason='B2_COMPLETE', effective_date=effective_date)
                    _sync_student_current_placement(student, inactive_status='COMPLETED')
                    _timeline(student, 'EXAM_FINALIZED', 'Passed final B2 exam and completed the course.', actor)
                    action = 'COMPLETED'
                else:
                    package_enrollment = get_active_package_enrollment(student, for_update=True)
                    if not package_enrollment.package.allows_level(next_level):
                        _close_placement(placement, exit_reason='PACKAGE_COMPLETE', effective_date=effective_date)
                        _sync_student_current_placement(student, inactive_status='AWAITING_PACKAGE_UPGRADE')
                        _timeline(
                            student,
                            'PACKAGE_COMPLETE',
                            f'Passed {level.name}; an upgraded package is required before entering {next_level.name}.',
                            actor,
                        )
                        action = 'AWAITING_PACKAGE_UPGRADE'
                    else:
                        _close_placement(placement, exit_reason='PROMOTION', effective_date=effective_date)
                        next_placement = _create_placement(
                            student,
                            academic_batch,
                            next_level,
                            package_enrollment,
                            entry_reason='PROMOTION',
                            effective_date=effective_date,
                        )
                        _timeline(
                            student,
                            'PROMOTE',
                            f'Passed {level.name} and advanced to {next_level.name} in {academic_batch.name}.',
                            actor,
                        )
                        action = f'PROMOTED_TO_{next_placement.level.name}'

            result.processed_at = timezone.now()
            result.processed_by = actor
            result.save(update_fields=['processed_at', 'processed_by'])
            processed.append({'student_id': student.id, 'placement_id': placement.id, 'action': action})

    return {'processed': processed, 'already_finalized': False}


def transfer_failed_student(student, target_batch, *, actor=None, effective_date=None):
    effective_date = effective_date or timezone.localdate()
    with transaction.atomic():
        if get_active_placement(student, for_update=True):
            raise AcademicWorkflowError('Student already has an active academic placement.')
        failed_placement = StudentAcademicPlacement.objects.select_related(
            'academic_batch', 'level'
        ).filter(
            student=student,
            status='CLOSED',
            exit_reason='FAILED',
        ).order_by('-exited_on', '-id').first()
        if not failed_placement or student.status != 'AWAITING_REPEAT_TRANSFER':
            raise AcademicWorkflowError('Student is not awaiting a repeat transfer.')
        if target_batch.id == failed_placement.academic_batch_id:
            raise AcademicWorkflowError('Repeat transfer must use a different academic batch.')
        if target_batch.branch_id != student.branch_id:
            raise AcademicWorkflowError('Repeat batch must belong to the student\'s branch.')
        if target_batch.starting_level_id != failed_placement.level_id:
            raise AcademicWorkflowError('Repeat batch must start at the failed grade.')

        package_enrollment = get_active_package_enrollment(student, for_update=True)
        placement = _create_placement(
            student,
            target_batch,
            failed_placement.level,
            package_enrollment,
            entry_reason='REPEAT',
            effective_date=effective_date,
        )
        _timeline(
            student,
            'REPEAT_TRANSFER',
            f'Transferred to {target_batch.name} to repeat {failed_placement.level.name}.',
            actor,
        )
    return placement


def placement_for_attendance(student, attendance_date):
    placement = StudentAcademicPlacement.objects.select_related(
        'academic_batch', 'level'
    ).filter(
        student=student,
        entered_on__lte=attendance_date,
    ).filter(
        Q(exited_on__isnull=True) | Q(exited_on__gte=attendance_date)
    ).order_by('-entered_on', '-id').first()
    if not placement:
        raise AcademicWorkflowError('Student does not have an academic placement active on this attendance date.')
    return placement
