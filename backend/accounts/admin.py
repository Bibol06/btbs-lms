
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('LMS', {'fields': ('role', 'admin_scope')}),
    )

    list_display = (
        'username',
        'email',
        'role',
        'admin_scope',
        'is_staff',
    )
