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
    if distance > office.geo_radius_meters:
        attendance.is_within_geofence = False

    login_time = normalize_time(time)
    attendance.login_time = login_time
    attendance.login_latitude = latitude
    attendance.login_longitude = longitude
    attendance.is_within_geofence = True
    attendance.login_distance = distance
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
    attendance.logout_latitude = latitude
    attendance.logout_longitude = longitude
    attendance.logout_distance = distance
    if attendance.login_time:
        login_dt = datetime.combine(date.today(), attendance.login_time)
        logout_dt = datetime.combine(date.today(), logout_time)

        attendance.worked_hours = round(
            (logout_dt - login_dt).total_seconds() / 3600,
            2
        )

    if attendance.logout_time < office.logout_time and attendance.status == "late_login":
        attendance.status = "absent"
    elif attendance.logout_time < office.logout_time:
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
