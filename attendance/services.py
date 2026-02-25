from math import radians, sin, cos, sqrt, atan2
from datetime import date, datetime
from django.utils import timezone
from django.shortcuts import get_object_or_404

from attendance.models import AttendanceRecord
from organizations.models import OfficeLocation
from datetime import datetime, time as time_type


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = radians(float(lat1))
    phi2 = radians(float(lat2))
    delta_phi = radians(float(lat2) - float(lat1))
    delta_lambda = radians(float(lon2) - float(lon1))

    a = sin(delta_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def check_in_user(user, office_id, latitude, longitude, time):
    office = get_object_or_404(OfficeLocation, id=office_id)

    distance = calculate_distance(
        latitude, longitude, office.latitude, office.longitude
    )

    attendance, _ = AttendanceRecord.objects.get_or_create(
        user=user,
        attendance_date=date.today(),
        office_location=office,
    )
    is_within = distance <= office.geo_radius_meters
    
    attendance.login_time = normalize_time(time)
    attendance.actual_login_time = attendance.login_time
    attendance.login_latitude = latitude
    attendance.login_longitude = longitude
    attendance.login_distance = distance
    attendance.is_within_geofence = is_within
    if attendance.login_time > office.login_time:
        attendance.status = "late_login"
    else:
        attendance.status = "present"
    attendance.save()

    return attendance, distance


def check_out_user(user, latitude, longitude, time):
    attendance = get_object_or_404(
        AttendanceRecord,
        user=user,
        attendance_date=date.today()
    )

    office = attendance.office_location
    distance = calculate_distance(
        latitude, longitude, office.latitude, office.longitude
    )

    logout_time = normalize_time(time)
    attendance.logout_time = logout_time
    attendance.actual_logout_time = logout_time
    attendance.logout_latitude = latitude
    attendance.logout_longitude = longitude
    attendance.logout_distance = distance
    
    # Maintain geofence integrity: if either check-in or check-out is outside, flag is False
    if distance > office.geo_radius_meters:
        attendance.is_within_geofence = False
    
    if attendance.login_time:
        login_dt = datetime.combine(attendance.attendance_date, attendance.login_time)
        logout_dt = datetime.combine(attendance.attendance_date, logout_time)
        
        # Handle cross-day logout if it ever happens (Logout < Login on same date)
        if logout_dt < login_dt:
            # Assume it's the next day
            from datetime import timedelta
            logout_dt += timedelta(days=1)

        duration = (logout_dt - login_dt).total_seconds() / 3600
        attendance.worked_hours = round(duration, 2)

        # Robust Status Logic
        if duration < 1.0: # Less than 1 hour is effectively absent
            attendance.status = "absent"
        elif duration < 4.5: # 1 to 4.5 hours is a half day
            attendance.status = "half_day"
        else:
            # Check for shift violations
            is_late = attendance.login_time > office.login_time
            is_early = logout_time < office.logout_time
            
            if is_late and is_early:
                attendance.status = "half_day" # Both violations = Half Day
            elif is_late:
                attendance.status = "late_login"
            elif is_early:
                attendance.status = "early_logout"
            else:
                attendance.status = "present"
    
    attendance.save()
    return attendance, distance


def normalize_time(value):
    if isinstance(value, time_type):
        return value.replace(microsecond=0)
    if isinstance(value, str):
        return datetime.strptime(value, "%H:%M:%S").time()
    raise ValueError("Invalid time format")
