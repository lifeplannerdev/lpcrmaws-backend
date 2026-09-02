"""
Management command to load all FLAG seed data from the academic_packages_batches_students.txt file.
Loads: 2 campuses, 4 grades, 2 attendance policies, 6 fee policies, 5 packages, 14 batches, 36 students.
Usage: python manage.py loadflagdata
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
import datetime

from students.models import (
    Grade, Campus, AcademicPackage, AcademicBatch,
    Student, AttendancePolicy, StudentBatchHistory
)
from fees.models import FeePlanTemplate


class Command(BaseCommand):
    help = 'Load FLAG German Language School seed data (36 students, 14 batches, 5 packages)'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.MIGRATE_HEADING('=== Loading FLAG Seed Data ==='))

        # ── Grades ─────────────────────────────────────────────
        self.stdout.write('Creating grades...')
        grade_data = [
            ('A1', 'A1 – Beginner', 1),
            ('A2', 'A2 – Elementary', 2),
            ('B1', 'B1 – Intermediate', 3),
            ('B2', 'B2 – Upper Intermediate', 4),
        ]
        grades = {}
        for code, name, order in grade_data:
            g, created = Grade.objects.get_or_create(code=code, defaults={'name': name, 'order': order})
            grades[code] = g
            if created:
                self.stdout.write(f'  [OK] Grade {code}')

        # ── Campuses ────────────────────────────────────────────
        self.stdout.write('Creating campuses...')
        ktm, _ = Campus.objects.get_or_create(
            code='KTM', defaults={'name': 'FLAG Kottayam'}
        )
        chn, _ = Campus.objects.get_or_create(
            code='CHN', defaults={'name': 'FLAG Kochi'}
        )
        self.stdout.write('  ✓ Kottayam (KTM), Kochi (CHN)')

        # ── Attendance Policies ─────────────────────────────────
        self.stdout.write('Creating attendance policies...')
        strict, _ = AttendancePolicy.objects.get_or_create(
            name='Strict',
            defaults={
                'description': 'Standard policy. Students with pending fees get Pending attendance status.',
                'is_active': True,
            }
        )
        flexible, _ = AttendancePolicy.objects.get_or_create(
            name='Flexible',
            defaults={
                'description': 'Lenient policy with more grace absences.',
                'is_active': True,
            }
        )
        self.stdout.write('  ✓ Strict, Flexible')

        # ── Fee Policies ────────────────────────────────────────
        self.stdout.write('Creating fee policies...')
        fee_policies = [
            ('Level Based', 'fee-per-level', 'PACKAGE', 15000, 1),
            ('Installment', 'Installment-based fee plan', 'INSTALLMENT', 15000, 3),
            ('One Time', 'Full payment upfront', 'ONE_TIME', 15000, 1),
            ('Intensive Package', 'Intensive course package fee', 'PACKAGE', 20000, 1),
            ('GCC Package', 'GCC flat-fee A1-A2 package (e.g. ₹40,000)', 'PACKAGE', 40000, 1),
            ('Seat Booking', 'Initial seat booking fee', 'CUSTOM', 5000, 1),
        ]
        fp = {}
        for name, desc, calc, amount, inst in fee_policies:
            # Clean name for code
            code = f"FLAG_{name.replace(' ', '_').upper()}"
            p, created = FeePlanTemplate.objects.get_or_create(
                code=code,
                defaults={'name': name, 'company': 'FLAG', 'notes': desc, 'plan_type': calc, 'total_amount': amount, 'installment_count': inst}
            )
            fp[name] = p
            if created:
                self.stdout.write(f'  ✓ Fee Policy: {name}')

        # ── Academic Packages ───────────────────────────────────
        self.stdout.write('Creating academic packages...')
        packages = [
            ('A1 Foundation', 'A1', 'A1', 'Single-level A1 package for complete beginners.'),
            ('A1 to A2 Package', 'A1', 'A2', 'Two-level package covering A1 and A2.'),
            ('A1 to B2 Package', 'A1', 'B2', 'Full journey from beginner to upper-intermediate.'),
            ('B1 to B2 Package', 'B1', 'B2', 'Advanced package for intermediate learners.'),
            ('B2 Preparation Package', 'B2', 'B2', 'Focused B2 exam preparation.'),
        ]
        pkgs = {}
        for name, sg, eg, desc in packages:
            p, created = AcademicPackage.objects.get_or_create(
                name=name,
                defaults={
                    'description': desc,
                    'starting_grade': grades[sg],
                    'ending_grade': grades[eg],
                }
            )
            pkgs[name] = p
            if created:
                self.stdout.write(f'  ✓ Package: {name}')

        # ── Batches ─────────────────────────────────────────────
        self.stdout.write('Creating batches...')
        batch_data = [
            # (name, campus, package_name, starting_grade, current_grade, mode, schedule, status)
            ('FLAG_KTM-1', ktm, 'A1 Foundation',      'A1', 'A1', 'offline', 'Offline – Confirm schedule', 'active'),
            ('FLAG_KTM-2', ktm, 'A1 to A2 Package',   'A1', 'A2', 'offline', 'Offline – Confirm schedule', 'active'),
            ('FLAG_KTM-3', ktm, 'A1 to B2 Package',   'A1', 'B2', 'offline', 'Offline – Confirm schedule', 'active'),
            ('FLAG_KTM-4', ktm, 'B1 to B2 Package',   'B1', 'B2', 'offline', 'Offline – Confirm schedule', 'active'),
            ('FLAG_KTM-ONLINE-A1',    ktm, 'A1 Foundation',    'A1', 'A1', 'online', 'Online – Mixed/Self-paced', 'active'),
            ('FLAG_KTM-ONLINE-A1-B2', ktm, 'A1 to B2 Package', 'A1', 'B2', 'online', 'Online – Mixed/Self-paced', 'active'),
            ('FLAG_KTM-ONLINE-B2',    ktm, 'B2 Preparation Package', 'B2', 'B2', 'online', 'Online – Mixed/Self-paced', 'active'),

            ('FLAG_CHN-3-NEW',      chn, 'A1 Foundation',    'A1', 'A1', 'offline', 'Offline – Schedule TBD',          'proposed'),
            ('FLAG_CHN-A1-INTENSIVE', chn, 'A1 to B2 Package','A1', 'A1', 'offline', 'Mon–Fri 10:00–12:30',            'active'),
            ('FLAG_CHN-A1-ONGOING',   chn, 'A1 to B2 Package','A1', 'A1', 'offline', 'Mon–Fri 12:30–15:00',            'active'),
            ('FLAG_CHN-A2',           chn, 'A1 to A2 Package','A2', 'A2', 'offline', 'Mon–Fri 10:00–12:30',            'active'),
            ('FLAG_CHN-NEW',          chn, 'A1 to B2 Package','A1', 'B2', 'offline', 'Offline – Schedule TBD',          'proposed'),
            ('FLAG_CHN-ONLINE-A1',    chn, 'A1 Foundation',   'A1', 'A1', 'online',  'Online – Mixed/Self-paced',       'proposed'),
            ('FLAG_CHN-ONLINE-INTERVIEW-PREP', chn, 'A1 Foundation', 'A1', 'A1', 'online', 'Online 15:00–16:00', 'active'),
        ]
        batches = {}
        for name, campus, pkg_name, sg, cg, mode, schedule, status in batch_data:
            b, created = AcademicBatch.objects.get_or_create(
                name=name,
                defaults={
                    'campus': campus,
                    'package': pkgs[pkg_name],
                    'starting_grade': grades[sg],
                    'current_grade': grades[cg],
                    'mode': mode,
                    'schedule': schedule,
                    'status': status,
                    'attendance_policy': strict,
                    'start_date': datetime.date(2026, 6, 8),
                }
            )
            batches[name] = b
            if created:
                self.stdout.write(f'  ✓ Batch: {name} [{status}]')

        # ── Students ────────────────────────────────────────────
        self.stdout.write('Creating students (36 total)...')

        # All 36 students: (name, phone, email, parent_name, parent_phone, campus, package, batch, mode, fee_plan_note)
        students_data = [
            # ── KTM STUDENTS ──
            # FLAG_KTM-1 (A1 Foundation)
            ('Amal Mariya',  '9747964080', '',                      '',                    '',           ktm, 'A1 Foundation',    'FLAG_KTM-1',       'offline', 'Level Based'),
            ('Amal S',       '8547997151', '',                      'Rani',                '8547997151', ktm, 'A1 Foundation',    'FLAG_KTM-1',       'offline', 'Level Based'),
            ('Ashik S.K',    '9846854479', 'sajisajiashik@gmail.com','Saji',               '9846854479', ktm, 'A1 Foundation',    'FLAG_KTM-1',       'offline', 'Level Based'),
            ('Shamon T S',   '',           '',                      '',                    '',           ktm, 'A1 Foundation',    'FLAG_KTM-1',       'offline', 'Intensive'),

            # FLAG_KTM-2 (A1-A2)
            ('Ahalya Anil',   '8848805086', 'ahalyaanil51@gmail.com',   'Anil Kumar T.R',   '9947614541', ktm, 'A1 to A2 Package', 'FLAG_KTM-2', 'offline', 'Level Based'),
            ('Alona Jayan',   '8590711031', '',                          'Jayan',            '',           ktm, 'A1 to A2 Package', 'FLAG_KTM-2', 'offline', 'Level Based'),
            ('Amalu Abraham', '9400462772', 'amaluabraham03@gmail.com',  'Jolly Abraham',   '9496479391', ktm, 'A1 to A2 Package', 'FLAG_KTM-2', 'offline', 'GCC Package'),
            ('Reshma Murali S','7306702086','reshmamurali97@gmail.com',  'Muraleedharan Pillai','7025091688',ktm,'A1 to A2 Package','FLAG_KTM-2', 'offline', 'GCC Package'),

            # FLAG_KTM-3 (A1-B2)
            ('Feba Mary Renil', '7510180626', '',                     '',    '',           ktm, 'A1 to B2 Package', 'FLAG_KTM-3', 'offline', 'Seat Booking'),
            ('Helna PC',         '',          '',                     '',    '',           ktm, 'A1 to B2 Package', 'FLAG_KTM-3', 'offline', 'Intensive (Installment)'),
            ('Jerin Jim',       '9061432689', 'jerinjim3330@gmail.com','',   '8281503268', ktm, 'A1 to B2 Package', 'FLAG_KTM-3', 'offline', 'Installment'),
            ('Juna Mariya',     '9497032338', 'shaijuabraham33@gmail.com','','9497032338', ktm, 'A1 to B2 Package', 'FLAG_KTM-3', 'offline', 'Seat Booking'),
            ('Meenu Viswam',    '9605102512', '',                     'Viswam','9847277648',ktm, 'A1 to B2 Package', 'FLAG_KTM-3', 'offline', 'A1-B2 Package'),

            # FLAG_KTM-4 (B1-B2)
            ('Dona Mathew', '',           'donamathew845@gmail.com',   '', '',           ktm, 'B1 to B2 Package', 'FLAG_KTM-4', 'offline', 'Level Based'),
            ('Gopika',      '',           'gopikapramod433@gmail.com', '', '',           ktm, 'B1 to B2 Package', 'FLAG_KTM-4', 'offline', 'Level Based'),
            ('Jisha T S',   '9605835386', 'jisha3130@gmail.com', 'Vijayakumary','9544127661',ktm,'B1 to B2 Package','FLAG_KTM-4', 'offline', 'Package'),
            ('Nandana',     '',           'nandana210707@gmail.com',   '', '',           ktm, 'B1 to B2 Package', 'FLAG_KTM-4', 'offline', 'Level Based'),

            # KTM ONLINE
            ('Neenu Viswam',    '', '', '', '', ktm, 'A1 Foundation',         'FLAG_KTM-ONLINE-A1',    'online', ''),
            ('Maneesha Mol KS', '', '', '', '', ktm, 'A1 to B2 Package',      'FLAG_KTM-ONLINE-A1-B2', 'online', 'Intensive (Installment)'),
            ('Sana Salja',      '', '', '', '', ktm, 'B2 Preparation Package', 'FLAG_KTM-ONLINE-B2',    'online', 'Level Based'),

            # ── KOCHI STUDENTS ──
            # FLAG_CHN-3-NEW (proposed)
            ('Anto Varghese',   '', 'antovarghese4026@gmail.com',   '', '', chn, 'A1 Foundation', 'FLAG_CHN-3-NEW', 'offline', 'Intensive'),
            ('Avani Shine',     '', '',                              '', '', chn, 'A1 Foundation', 'FLAG_CHN-3-NEW', 'offline', 'Intensive'),
            ('Sharon T Joseph', '', 'sharontharakan17@gmail.com',   '', '', chn, 'A1 Foundation', 'FLAG_CHN-3-NEW', 'offline', 'Intensive'),

            # FLAG_CHN-A1-INTENSIVE
            ('Alan Baiju',  '', 'alanbaiju618@gmail.com', '', '', chn, 'A1 to B2 Package', 'FLAG_CHN-A1-INTENSIVE', 'offline', 'Intensive'),
            ('Anandhu D',   '', '',                       '', '', chn, 'A1 to B2 Package', 'FLAG_CHN-A1-INTENSIVE', 'offline', 'Intensive (Installment)'),

            # FLAG_CHN-A1-ONGOING
            ('Jison Johnson', '702529161',  'jjison809@gmail.com',  'Johnson C J', '9447074397', chn, 'A1 to B2 Package', 'FLAG_CHN-A1-ONGOING', 'offline', 'One Time'),
            ('Sera Alias',    '8891956834', 'sera.alias08@gmail.com','Alias A.K',  '9895073840', chn, 'A1 Foundation',    'FLAG_CHN-A1-ONGOING', 'offline', 'Level Based'),

            # FLAG_CHN-A2
            ('Abhiya Kuriakose', '', '',                       '',        '9447104279', chn, 'A1 to A2 Package', 'FLAG_CHN-A2', 'offline', 'Level Based'),
            ('Anna George',      '9497036672', '',             '',        '9446744587', chn, 'A1 to B2 Package', 'FLAG_CHN-A2', 'offline', 'Seat Booking'),
            ('Anu CR',           '8907737587', '',             '',        '8907737587', chn, 'A1 to A2 Package', 'FLAG_CHN-A2', 'offline', 'Level Based'),
            ('Evina VJ',         '9495634016', '',             '',        '9895456988', chn, 'A1 to A2 Package', 'FLAG_CHN-A2', 'offline', 'Level Based'),
            ('Gouri Priya',      '7510448015', 'gourivimeesh@gmail.com','Vimeesh','9846356018',chn,'A1 to A2 Package','FLAG_CHN-A2','offline','Level Based'),
            ('Meenakshi A G',    '8714174133', '',             '',        '9645541129', chn, 'A1 to A2 Package', 'FLAG_CHN-A2', 'offline', 'Level Based'),

            # Others
            ('Indraj A',    '', '', '', '', chn, 'A1 to B2 Package', 'FLAG_CHN-NEW',                  'offline', 'Intensive (Installment)'),
            ('Sheba Stanly','', '', '', '', chn, 'A1 Foundation',    'FLAG_CHN-ONLINE-A1',             'online',  'Level Based'),
            ('Mariya Ev',   '', 'mariyapv6720@gmail.com', '', '', chn, 'A1 Foundation', 'FLAG_CHN-ONLINE-INTERVIEW-PREP', 'offline', 'One Time'),
        ]

        created_count = 0
        for row in students_data:
            name, phone, email, parent_name, parent_phone, campus, pkg_name, batch_name, mode, fee_note = row
            if Student.objects.filter(name=name, campus=campus).exists():
                continue

            s = Student.objects.create(
                name=name,
                phone=phone,
                email=email,
                parent_name=parent_name,
                parent_phone=parent_phone,
                company='FLAG',
                campus=campus,
                academic_package=pkgs[pkg_name],
                batch=batches.get(batch_name),
                mode_of_study=mode,
                notes=f"Original Fee Plan: {fee_note}" if fee_note else "",
                status='active',
                joined_date=datetime.date(2026, 6, 8),
            )
            # Record enrollment in batch history
            if s.batch:
                StudentBatchHistory.objects.create(
                    student=s,
                    batch=s.batch,
                    grade_at_time=s.batch.current_grade,
                    action='enrolled',
                    from_date=s.joined_date,
                    reason='Initial enrollment from FLAG_ADMISSIONS-_2026.xlsx',
                )
            created_count += 1
            self.stdout.write(f'  ✓ Student: {name} → {batch_name}')

        self.stdout.write(self.style.SUCCESS(
            f'\n=== Done! ===\n'
            f'  Grades: 4\n'
            f'  Campuses: 2 (KTM, CHN)\n'
            f'  Packages: {AcademicPackage.objects.count()}\n'
            f'  Batches: {AcademicBatch.objects.count()}\n'
            f'  Students created: {created_count}\n'
            f'  Total students in DB: {Student.objects.count()}\n'
        ))

