from django.contrib import admin
from .models import CustomUser

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'email', 'first_name', 'last_name',
        'role', 'department', 'is_active'
    )
    list_filter = ('role', 'is_active', 'department')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('-created_at',)
