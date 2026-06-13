import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from hr.models import Branch, Location

# Create Kochi Office
kochi_branch, created = Branch.objects.get_or_create(name='Kochi Office', company='LP')
print(f"Kochi Office branch created: {created}")

# Assign all locations without a branch to Kochi Office
locations = Location.objects.filter(branch__isnull=True)
count = locations.count()
locations.update(branch=kochi_branch)

print(f"Assigned {count} locations to Kochi Office.")
