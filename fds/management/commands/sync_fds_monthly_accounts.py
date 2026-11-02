from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from fds.models import FdsStudent, FdsStudentFeeAccount, FdsFeeStructure

class Command(BaseCommand):
    help = "Sync and backfill FDS monthly recurring fee accounts and schedules"

    def add_arguments(self, parser):
        parser.add_argument(
            '--default-rate',
            type=float,
            default=1600.0,
            help='Default monthly fee rate if unassigned (default: 1600.0)'
        )

    def handle(self, *args, **options):
        default_rate = Decimal(str(options['default_rate']))
        self.stdout.write(self.style.NOTICE(f"Syncing FDS fee accounts with default rate: INR {default_rate}..."))

        today = timezone.localdate()

        # 1. Create fee accounts for any active students lacking one
        students_without_account = FdsStudent.objects.filter(is_active=True, fee_account__isnull=True)
        created_count = 0
        for student in students_without_account:
            is_wed = getattr(student, 'student_type', None) == 'WEDDING_MEMBER' or (
                student.fee_structure and 'WEDDING' in student.fee_structure.category.upper()
            )
            m_fee = student.fee_structure.amount if (student.fee_structure and student.fee_structure.amount > 0) else default_rate
            account = FdsStudentFeeAccount.objects.create(
                student=student,
                active_package=student.fee_structure,
                plan_type='ONE_TIME' if is_wed else 'MONTHLY',
                monthly_fee=Decimal('0.00') if is_wed else m_fee,
                start_date=student.joining_date or today.replace(day=1),
                due_day=10,
                plan_name=student.fee_structure.get_category_display() if student.fee_structure else ('Wedding Package' if is_wed else 'Monthly Dance Tuition'),
                plan_code=student.fee_structure.category if student.fee_structure else ('WEDDING' if is_wed else 'MONTHLY'),
            )
            if not is_wed:
                account.sync_monthly_schedule()
            account.recalculate(save=True)
            created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created_count} missing fee accounts."))

        # 2. Backfill and sync all existing accounts
        accounts = FdsStudentFeeAccount.objects.select_related('student', 'active_package').all()
        synced_count = 0
        for acc in accounts:
            if acc.is_wedding_or_one_time():
                acc.plan_type = 'ONE_TIME'
                if not acc.plan_name:
                    acc.plan_name = acc.active_package.get_category_display() if acc.active_package else 'Wedding Package'
                acc.save(update_fields=['plan_type', 'plan_name'])
                acc.recalculate(save=True)
                synced_count += 1
                continue

            eff_fee = acc.get_effective_monthly_fee()
            if not acc.monthly_fee or acc.monthly_fee <= 0:
                acc.monthly_fee = eff_fee

            if not acc.start_date:
                acc.start_date = (acc.student.joining_date if acc.student else None) or today.replace(day=1)

            if acc.plan_type in ['PACKAGE', 'ONE_TIME', '']:
                acc.plan_type = 'MONTHLY'

            if not acc.plan_name:
                acc.plan_name = (acc.active_package.get_category_display() if acc.active_package else 'Monthly Dance Tuition')

            acc.save(update_fields=['monthly_fee', 'start_date', 'plan_type', 'plan_name'])
            acc.sync_monthly_schedule(months_ahead=1)
            acc.recalculate(save=True)
            synced_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully synced {synced_count} FDS fee accounts."))
