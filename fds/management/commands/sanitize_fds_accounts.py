from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from fds.models import FdsStudentFeeAccount

class Command(BaseCommand):
    help = "Audit and sanitize corrupted FDS student fee accounts erroneously marked with Wedding Package"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Audit and report corrupted accounts without modifying the database'
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.NOTICE(f"{prefix}Auditing FDS student fee accounts for corruption..."))

        accounts = FdsStudentFeeAccount.objects.select_related(
            'student', 'active_package', 'student__fee_structure'
        ).all()

        total_audited = accounts.count()
        corrupted_count = 0
        fixed_count = 0

        for acc in accounts:
            student = acc.student
            is_wedding_student = (
                student and getattr(student, 'student_type', None) == 'WEDDING_MEMBER'
            )
            has_wedding_package = (
                acc.active_package and 'WEDDING' in (acc.active_package.category or '').upper()
            )

            # An account is corrupted if it has Wedding stamps but is neither a wedding student nor a wedding package
            is_corrupted = False
            reasons = []

            if not is_wedding_student and not has_wedding_package:
                if acc.plan_name and 'WEDDING' in acc.plan_name.upper():
                    is_corrupted = True
                    reasons.append(f"Erronenous plan_name '{acc.plan_name}'")
                if acc.plan_code and 'WEDDING' in acc.plan_code.upper():
                    is_corrupted = True
                    reasons.append(f"Erronenous plan_code '{acc.plan_code}'")
                if acc.plan_type == 'ONE_TIME' and (not acc.active_package or acc.active_package.category not in ['ADMISSION', 'TRIAL']):
                    is_corrupted = True
                    reasons.append(f"Erronenous plan_type 'ONE_TIME' for regular dance student")

            if is_corrupted:
                corrupted_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Account ID {acc.id} (Student: {student.name if student else 'None'}) corrupted: {', '.join(reasons)}"
                    )
                )

                if not dry_run:
                    # Sanitize plan_name
                    if acc.active_package:
                        acc.plan_name = acc.active_package.get_category_display()
                        acc.plan_code = acc.active_package.category
                    elif student and student.fee_structure:
                        acc.plan_name = student.fee_structure.get_category_display()
                        acc.plan_code = student.fee_structure.category
                    else:
                        acc.plan_name = 'Monthly Dance Tuition'
                        acc.plan_code = 'MONTHLY'

                    # Sanitize plan_type
                    if acc.plan_type == 'ONE_TIME':
                        acc.plan_type = 'MONTHLY'

                    # Ensure monthly fee
                    eff_fee = acc.get_effective_monthly_fee()
                    if not acc.monthly_fee or acc.monthly_fee <= 0:
                        acc.monthly_fee = eff_fee

                    acc.save(update_fields=['plan_name', 'plan_code', 'plan_type', 'monthly_fee'])
                    acc.sync_monthly_schedule(months_ahead=1)
                    acc.recalculate(save=True)
                    fixed_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  -> Fixed Account ID {acc.id}: restored to '{acc.plan_name}' ({acc.plan_type}), monthly_fee: {acc.monthly_fee}"
                        )
                    )

        self.stdout.write(self.style.NOTICE("──────────────────────────────────────────────────"))
        self.stdout.write(f"Total audited: {total_audited}")
        self.stdout.write(f"Corrupted accounts found: {corrupted_count}")
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry run complete. No database modifications made."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Successfully sanitized {fixed_count} accounts."))
