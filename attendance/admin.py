from django.contrib import admin
from .models import AttendanceRecord, AttendanceCorrection, AttendanceHeartbeat

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = (
        'user', 
        'attendance_date', 
        'status', 
        'login_time', 
        'logout_time',
        'is_within_geofence',
        'worked_hours',
        'effective_worked_hours',
        'valid_heartbeats',
        'total_heartbeats',
        'roaming_anomaly_detected',
    )
    list_filter = ('status', 'roaming_anomaly_detected', 'attendance_date', 'office_location', 'is_within_geofence')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'remarks', 'roaming_notes')
    ordering = ('-attendance_date',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AttendanceHeartbeat)
class AttendanceHeartbeatAdmin(admin.ModelAdmin):
    list_display = (
        'attendance_record',
        'timestamp',
        'is_within_geofence',
        'distance_meters',
        'accuracy_meters',
        'is_mocked',
        'battery_level',
    )
    list_filter = ('is_within_geofence', 'is_mocked', 'timestamp')
    search_fields = ('attendance_record__user__email', 'attendance_record__user__first_name')
    ordering = ('-timestamp',)
    readonly_fields = ('timestamp',)

@admin.register(AttendanceCorrection)
class AttendanceCorrectionAdmin(admin.ModelAdmin):
    list_display = (
        'attendance_record', 
        'requested_by', 
        '_status', 
        'corrected_login_time', 
        'corrected_logout_time',
        'created_at'
    )
    list_filter = ('_status', 'created_at')
    search_fields = (
        'requested_by__email', 
        'requested_by__first_name', 
        'requested_by__last_name', 
        'reason'
    )
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)
