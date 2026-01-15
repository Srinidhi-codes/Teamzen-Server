from django.contrib import admin
from .models import LeaveType

@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization')
    list_filter = ('organization',)
    search_fields = ('name','organization',)
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at')