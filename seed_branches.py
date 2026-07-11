import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from trainers.models import Branch

def seed_branches():
    branches = [
        {'name': 'KOTTAYAM', 'location': 'Kottayam'},
        {'name': 'KOCHI', 'location': 'Kochi'}
    ]
    for b in branches:
        branch, created = Branch.objects.get_or_create(name=b['name'], defaults={'location': b['location']})
        if created:
            print(f"Created branch: {branch.name}")
        else:
            print(f"Branch already exists: {branch.name}")

if __name__ == '__main__':
    seed_branches()
