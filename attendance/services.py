from math import radians, sin, cos, sqrt, atan2
from datetime import date, datetime, time as time_type
from django.shortcuts import get_object_or_404
from graphql import GraphQLError

from attendance.models import AttendanceRecord
from attendance.face_constants import (
    FACE_DESCRIPTOR_DIM,
    FACE_DISTANCE_THRESHOLD,
    FACE_MATCH_THRESHOLD,
)
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


def _as_float_list(raw) -> list[float]:
    if raw is None:
        return []
    try:
        return [float(x) for x in raw]
    except (TypeError, ValueError):
        return []


def euclidean_distance(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return float("inf")
    return sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def assert_face_attendance_allowed(
    user,
    *,
    face_descriptor: list[float] | None = None,
    face_verified: bool | None = None,
    face_match_score: float | None = None,
) -> float:
    """
    Validate face punch. Returns server-computed similarity in [0, 1].
    Always recomputes Euclidean distance vs enrolled descriptor — client flags alone are not enough.
    """
    if not org_requires_face(user):
        return 0.0

    enrolled = _as_float_list(user.face_descriptor)
    if not user.face_enrolled_at or not enrolled:
        raise GraphQLError(
            "Face enrollment required. Enroll your face in Attendance before punching."
        )

    if len(enrolled) != FACE_DESCRIPTOR_DIM:
        raise GraphQLError(
            "Your face enrollment is outdated. Please re-enroll your face, then try again."
        )

    live = _as_float_list(face_descriptor)
    if len(live) != FACE_DESCRIPTOR_DIM:
        raise GraphQLError(
            "Face verification data missing or invalid. Update the app and retry with camera."
        )

    distance = euclidean_distance(enrolled, live)
    if distance > FACE_DISTANCE_THRESHOLD:
        raise GraphQLError(
            f"Face did not match (distance {distance:.2f}; need ≤ {FACE_DISTANCE_THRESHOLD:.2f}). "
            "Use the enrolled person's face and try again."
        )

    if face_verified is False:
        raise GraphQLError("Face verification failed. Please try again with a clear selfie.")

    similarity = max(0.0, 1.0 - distance)
    if similarity < FACE_MATCH_THRESHOLD:
        raise GraphQLError(
            f"Face match score too low ({similarity:.2f}). Required ≥ {FACE_MATCH_THRESHOLD:.2f}."
        )

    _ = face_match_score  # client score is advisory only
    return similarity


def check_in_user(
    user,
    office_id,
    latitude,
    longitude,
    time,
    *,
    face_verified: bool | None = None,
    face_match_score: float | None = None,
    face_descriptor: list[float] | None = None,
):
    office = get_object_or_404(OfficeLocation, id=office_id)

    if office.latitude is None or office.longitude is None:
        raise GraphQLError("Office location has no coordinates configured.")

    distance = calculate_distance(
        latitude, longitude, office.latitude, office.longitude
    )
    is_within = distance <= office.geo_radius_meters
    face_mode = org_requires_face(user)
    server_face_score = None

    if face_mode:
        server_face_score = assert_face_attendance_allowed(
            user,
            face_descriptor=face_descriptor,
            face_verified=face_verified,
            face_match_score=face_match_score,
        )

    attendance, _ = AttendanceRecord.objects.get_or_create(
        user=user,
        attendance_date=date.today(),
        defaults={"office_location": office},
    )
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
        attendance.face_match_score = server_face_score
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
    face_descriptor: list[float] | None = None,
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
    server_face_score = None

    if face_mode:
        server_face_score = assert_face_attendance_allowed(
            user,
            face_descriptor=face_descriptor,
            face_verified=face_verified,
            face_match_score=face_match_score,
        )

    logout_time = normalize_time(time)
    attendance.logout_time = logout_time
    attendance.actual_logout_time = logout_time
    attendance.logout_latitude = latitude
    attendance.logout_longitude = longitude
    attendance.logout_distance = int(distance)

    if distance > office.geo_radius_meters:
        attendance.is_within_geofence = False

    if face_mode:
        attendance.face_verified = True
        attendance.face_match_score = server_face_score

    attendance.save()
    return attendance, distance


def normalize_time(value):
    if isinstance(value, time_type):
        return value.replace(microsecond=0)
    if isinstance(value, str):
        return datetime.strptime(value, "%H:%M:%S").time()
    raise ValueError("Invalid time format")
