from accounts.models import AppPermission, Role

def seed_feeds_permissions():
    perms_to_create = [
        ('feeds:admin', 'Can manage all feeds and delete any posts/comments'),
        ('feeds:post', 'Can create new posts on feeds'),
    ]

    for name, desc in perms_to_create:
        p, created = AppPermission.objects.get_or_create(name=name, defaults={'description': desc})
        if created:
            print(f"Created permission: {name}")
        else:
            print(f"Permission already exists: {name}")
            
    # Assign feeds:admin to Management and SuperAdmin
    roles_for_admin = ["Management", "SuperAdmin", "Admin"]
    for role_name in roles_for_admin:
        try:
            role = Role.objects.get(name__icontains=role_name)
            p = AppPermission.objects.get(name='feeds:admin')
            p_post = AppPermission.objects.get(name='feeds:post')
            
            if not role.permissions.filter(id=p.id).exists():
                role.permissions.add(p)
                print(f"Added feeds:admin to role: {role.name}")
            if not role.permissions.filter(id=p_post.id).exists():
                role.permissions.add(p_post)
                print(f"Added feeds:post to role: {role.name}")
                
        except Role.DoesNotExist:
            pass
        except Exception as e:
            print(f"Error updating role {role_name}: {e}")

seed_feeds_permissions()
