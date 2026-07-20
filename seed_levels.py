import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from trainers.models import CourseLevel, CourseModule

def seed():
    levels = [
        ('A1', 1, ['A1.1', 'A1.2']),
        ('A2', 2, ['A2.1', 'A2.2']),
        ('B1', 3, ['B1.1', 'B1.2']),
        ('B2', 4, ['B2.1', 'B2.2']),
    ]

    print("Seeding Course Levels and Modules...")
    for level_name, level_order, modules in levels:
        level, created = CourseLevel.objects.get_or_create(
            name=level_name,
            defaults={'order': level_order}
        )
        if not created:
            level.order = level_order
            level.save()
            print(f"Updated Level: {level.name}")
        else:
            print(f"Created Level: {level.name}")

        for order, module_name in enumerate(modules, start=1):
            module, m_created = CourseModule.objects.get_or_create(
                level=level,
                name=module_name,
                defaults={'order': order}
            )
            if not m_created:
                module.order = order
                module.save()
                print(f"  Updated Module: {module.name}")
            else:
                print(f"  Created Module: {module.name}")
                
    print("Seeding complete.")

if __name__ == '__main__':
    seed()
