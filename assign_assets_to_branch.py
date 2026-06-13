import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lpcrm.settings')
django.setup()

from hr.models import Asset, Branch

def assign_assets_to_branch():
    print("Starting Asset -> Branch assignment...")
    
    # Get Kochi Office
    try:
        kochi_branch = Branch.objects.get(name='Kochi Office', company='LP')
        print(f"Found branch: {kochi_branch.name} (ID: {kochi_branch.id})")
    except Branch.DoesNotExist:
        print("Kochi Office branch does not exist. Aborting.")
        return

    # Find assets NOT in Mobile or SIM category
    assets_to_update = Asset.objects.exclude(category__name__in=['Mobiles', 'Mobile', 'SIM', 'Sim'])
    count = assets_to_update.count()
    
    print(f"Found {count} assets to assign to Kochi Office.")
    
    # Update branch
    assets_to_update.update(branch=kochi_branch)
    
    print("Update complete.")

if __name__ == '__main__':
    assign_assets_to_branch()
