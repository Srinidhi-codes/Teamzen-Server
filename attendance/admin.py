from django.contrib import admin
from .models import AttendanceRecord, AttendanceCorrection

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = (
        'user', 
        'attendance_date', 
        'status', 
        'login_time', 
        'logout_time',
        'is_within_geofence',
        'worked_hours'
    )
    list_filter = ('status', 'attendance_date', 'office_location', 'is_within_geofence')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'remarks')
    ordering = ('-attendance_date',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(AttendanceCorrection)
class AttendanceCorrectionAdmin(admin.ModelAdmin):
    list_display = (
        'attendance_record', 
        'requested_by', 
        'status', 
        'corrected_login_time', 
        'corrected_logout_time',
        'created_at'
    )
    list_filter = ('status', 'created_at')
    search_fields = (
        'requested_by__email', 
        'requested_by__first_name', 
        'requested_by__last_name', 
        'reason'
    )
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)
