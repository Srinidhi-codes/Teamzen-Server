from math import radians, sin, cos, sqrt, atan2
from datetime import date, datetime, time as time_type
from django.shortcuts import get_object_or_404
from graphql import GraphQLError

from attendance.models import AttendanceRecord
from attendance.face_constants import FACE_MATCH_THRESHOLD
from organizations.models import OfficeLocation


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = radians(float(lat1))
    phi2 = radians(float(lat2))
    delta_phi = radians(float(lat2) - float(lat1))
    delta_lambda = radians(float(lon2) - float(lon1))

    a = sin(delta_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def org_requires_face(user) -> bool:
    org = getattr(user, "organization", None)
    return bool(org and getattr(org, "face_attendance_enabled", False))


def assert_face_attendance_allowed(user, *, face_verified: bool | None, face_match_score: float | None):
    """Raise when org requires face punch and client did not satisfy enrollment/match."""
    if not org_requires_face(user):
        return

    if not user.face_enrolled_at or not user.face_descriptor:
        raise GraphQLError(
            "Face enrollment required. Enroll your face in Attendance or Profile before punching."
        )

    if not face_verified:
        raise GraphQLError("Face verification failed. Please try again with a clear selfie.")

    score = float(face_match_score) if face_match_score is not None else 0.0
    if score < FACE_MATCH_THRESHOLD:
        raise GraphQLError(
            f"Face match score too low ({score:.2f}). Required ≥ {FACE_MATCH_THRESHOLD:.2f}."
        )


def check_in_user(
    user,
    office_id,
    latitude,
    longitude,
    time,
    *,
    face_verified: bool | None = None,
    face_match_score: float | None = None,
):
    office = get_object_or_404(OfficeLocation, id=office_id)

    if office.latitude is None or office.longitude is None:
        raise GraphQLError("Office location has no coordinates configured.")

    distance = calculate_distance(
        latitude, longitude, office.latitude, office.longitude
    )
    is_within = distance <= office.geo_radius_meters
    face_mode = org_requires_face(user)

    if face_mode:
        assert_face_attendance_allowed(
            user, face_verified=face_verified, face_match_score=face_match_score
        )

    attendance, _ = AttendanceRecord.objects.get_or_create(
        user=user,
        attendance_date=date.today(),
        defaults={"office_location": office},
    )
    # Keep office in sync if record already existed without office change
    if attendance.office_location_id != office.id:
        attendance.office_location = office

    attendance.login_time = normalize_time(time)
    attendance.actual_login_time = attendance.login_time
    attendance.login_latitude = latitude
    attendance.login_longitude = longitude
    attendance.login_distance = int(distance)
    attendance.is_within_geofence = is_within
    if face_mode:
        attendance.face_verified = True
        attendance.face_match_score = float(face_match_score) if face_match_score is not None else None
    attendance.save()

    return attendance, distance


def check_out_user(
    user,
    latitude,
    longitude,
    time,
    *,
    face_verified: bool | None = None,
    face_match_score: float | None = None,
):
    attendance = get_object_or_404(
        AttendanceRecord,
        user=user,
        attendance_date=date.today(),
    )

    office = attendance.office_location
    if not office or office.latitude is None or office.longitude is None:
        raise GraphQLError("Office location has no coordinates configured.")

    distance = calculate_distance(
        latitude, longitude, office.latitude, office.longitude
    )
    face_mode = org_requires_face(user)

    if face_mode:
        assert_face_attendance_allowed(
            user, face_verified=face_verified, face_match_score=face_match_score
        )

    logout_time = normalize_time(time)
    attendance.logout_time = logout_time
    attendance.actual_logout_time = logout_time
    attendance.logout_latitude = latitude
    attendance.logout_longitude = longitude
    attendance.logout_distance = int(distance)

    # Maintain geofence integrity: if either check-in or check-out is outside, flag is False
    if distance > office.geo_radius_meters:
        attendance.is_within_geofence = False

    if face_mode:
        attendance.face_verified = True
        attendance.face_match_score = float(face_match_score) if face_match_score is not None else None

    attendance.save()
    return attendance, distance


def normalize_time(value):
    if isinstance(value, time_type):
        return value.replace(microsecond=0)
    if isinstance(value, str):
        return datetime.strptime(value, "%H:%M:%S").time()
    raise ValueError("Invalid time format")
