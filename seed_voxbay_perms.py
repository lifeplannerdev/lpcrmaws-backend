from accounts.models import AppPermission, Role, User

def seed_permissions():
    perms_to_create = [
        ('voxbay:read_own', 'Can read own Voxbay calls'),
        ('voxbay:read_all', 'Can read all Voxbay calls'),
        ('voxbay:admin', 'Can manage unique missed Voxbay calls'),
    ]

    for name, desc in perms_to_create:
        p, created = AppPermission.objects.get_or_create(name=name, defaults={'description': desc})
        if created:
            print(f"Created permission: {name}")
        else:
            print(f"Permission already exists: {name}")

    # Now assign voxbay:read_own to Admissions Manager role
    try:
        role = Role.objects.get(name__icontains="Admissions Manager")
        p = AppPermission.objects.get(name='voxbay:read_own')
        if not role.permissions.filter(id=p.id).exists():
            role.permissions.add(p)
            print(f"Added voxbay:read_own to role: {role.name}")
        else:
            print(f"Role '{role.name}' already has voxbay:read_own")
        
        # Also assign it to the user directly if they have a permissions JSON field or extra_permissions
        tony = User.objects.filter(username="Tony_AM").first()
        if tony:
            if tony.db_roles.filter(id=role.id).exists():
                print(f"Tony is already in role {role.name}")
            else:
                tony.db_roles.add(role)
                print(f"Added Tony to role {role.name}")
    except Role.DoesNotExist:
        print("Role 'Admissions Manager' not found.")
    except Exception as e:
        print(f"Error updating role: {e}")

seed_permissions()
