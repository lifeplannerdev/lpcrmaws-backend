"""
Independent Seeding Script: Add 'admin:dashboard' Permission
File: lpcrmbackend-main/seed_admin_dashboard_permission.py

Convenience runner in backend root that delegates directly to scripts/add_admin_dashboard_perm.py.
Follows the project's root seed script convention (e.g. seed_fee_permissions.py, seed_mail_permissions.py).
"""
import os
import sys

# Ensure backend root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.add_admin_dashboard_perm import add_admin_dashboard_permission

if __name__ == '__main__':
    add_admin_dashboard_permission()
