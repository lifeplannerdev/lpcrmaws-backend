from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from .models import User, MicroWork


class CustomUserAdmin(UserAdmin):
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {
            'fields': ('first_name', 'last_name', 'email', 'location', 'phone')
        }),
        ('Role info', {'fields': ('db_roles', 'company', 'team', 'salary')}),
        ('Permissions', {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions'
            )
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )


admin.site.register(User, CustomUserAdmin)
admin.site.register(MicroWork)
admin.site.unregister(Group)

admin.site.site_header = 'LP ADMINISTRATION'
admin.site.site_title = 'LP Admin Portal'
admin.site.index_title = 'Welcome to LP Administration'

