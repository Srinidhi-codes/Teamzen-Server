from rest_framework import serializers
from attendance.models import AttendanceRecord, AttendanceCorrection

class AttendanceRecordSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta: 
        model = AttendanceRecord
        fields = [
            'id', 'user', 'user_name', 'attendance_date', 'login_time',
            'logout_time', 'is_within_geofence', 'status', 'worked_hours', 'remarks'
        ]
        read_only_fields = ['id', 'is_within_geofence', 'worked_hours']

class AttendanceCorrectionSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(source='requested_by.get_full_name', read_only=True)

    class Meta:
        model = AttendanceCorrection
        fields = [
            'id', 'attendance_record', 'corrected_login_time',
            'corrected_logout_time', 'reason', 'status', 'requested_by_name'
        ]
        read_only_fields = ['id', 'status']