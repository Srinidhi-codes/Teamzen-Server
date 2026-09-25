from math import radians, sin, cos, sqrt, atan2
from datetime import date, datetime, time as time_type
from django.shortcuts import get_object_or_404
from graphql import GraphQLError

from attendance.models import AttendanceRecord, AttendanceHeartbeat
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
    if not org or not getattr(org, "face_attendance_enabled", False):
        return False
    from organizations.plan_entitlements import org_has_feature

    return org_has_feature(org, "face_attendance")


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


def _get_enrolled_templates(raw) -> list[list[float]]:
    """Extract list of 128-d descriptor vectors. Supports single vector or multi-appearance list."""
    if not raw:
        return []
    if isinstance(raw, list) and len(raw) > 0 and isinstance(raw[0], list):
        templates = []
        for item in raw:
            vec = _as_float_list(item)
            if len(vec) == FACE_DESCRIPTOR_DIM:
                templates.append(vec)
        return templates
    vec = _as_float_list(raw)
    if len(vec) == FACE_DESCRIPTOR_DIM:
        return [vec]
    return []


def assert_face_attendance_allowed(
    user,
    *,
    face_descriptor: list[float] | None = None,
    face_verified: bool | None = None,
    face_match_score: float | None = None,
) -> float:
    """
    Validate face punch. Returns server-computed similarity in [0, 1].
    Always recomputes Euclidean distance vs enrolled template(s) — client flags alone are not enough.
    Supports single template as well as alternative appearances (e.g. with/without glasses).
    """
    if not org_requires_face(user):
        return 0.0

    templates = _get_enrolled_templates(user.face_descriptor)
    if not user.face_enrolled_at or not templates:
        raise GraphQLError(
            "Face enrollment required. Enroll your face in Attendance before punching."
        )

    live = _as_float_list(face_descriptor)
    if len(live) != FACE_DESCRIPTOR_DIM:
        raise GraphQLError(
            "Face verification data missing or invalid. Update the app and retry with camera."
        )

    # Find closest match among enrolled appearances (e.g., with vs without specs)
    best_distance = min(euclidean_distance(t, live) for t in templates)
    if best_distance > FACE_DISTANCE_THRESHOLD:
        raise GraphQLError(
            f"Face did not match (distance {best_distance:.2f}; need ≤ {FACE_DISTANCE_THRESHOLD:.2f}). "
            "Use the enrolled person's face and try again."
        )

    if face_verified is False:
        raise GraphQLError("Face verification failed. Please try again with a clear selfie.")

    # Mathematical cosine similarity for L2-normalized unit vectors: 1 - (d^2)/2
    similarity = max(0.0, min(1.0, 1.0 - (best_distance ** 2) / 2.0))
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
        defaults={
            "office_location": office,
            "total_heartbeats": 0,
            "valid_heartbeats": 0,
            "out_of_fence_heartbeats": 0,
        },
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


def record_attendance_heartbeat(
    user,
    latitude,
    longitude,
    *,
    accuracy_meters: float | None = None,
    is_mocked: bool = False,
    battery_level: float | None = None,
):
    """
    Record periodic background geolocation heartbeat for today's active shift.
    Validates against office geofence and updates attendance metrics & anomaly alerts.
    """
    today = date.today()
    try:
        attendance = AttendanceRecord.objects.get(user=user, attendance_date=today)
    except AttendanceRecord.DoesNotExist:
        return {
            "status": "no_record",
            "message": "No attendance record found for today. Please clock in first.",
            "should_stop": True,
        }

    if not attendance.login_time:
        return {
            "status": "not_clocked_in",
            "message": "User has not clocked in yet today.",
            "should_stop": True,
        }

    if attendance.logout_time:
        return {
            "status": "shift_ended",
            "message": "User has already clocked out for the day.",
            "should_stop": True,
        }

    office = attendance.office_location
    if not office or office.latitude is None or office.longitude is None:
        raise GraphQLError("Office location has no coordinates configured.")

    distance = calculate_distance(
        latitude, longitude, office.latitude, office.longitude
    )
    dist_int = int(distance)
    is_within = (dist_int <= office.geo_radius_meters) and not is_mocked

    heartbeat = AttendanceHeartbeat.objects.create(
        attendance_record=attendance,
        latitude=latitude,
        longitude=longitude,
        distance_meters=dist_int,
        is_within_geofence=is_within,
        accuracy_meters=accuracy_meters,
        is_mocked=is_mocked,
        battery_level=battery_level,
    )

    # Update summary aggregates on attendance record
    all_hb = list(attendance.heartbeats.all().order_by("timestamp"))
    total_count = len(all_hb)
    valid_count = sum(1 for hb in all_hb if hb.is_within_geofence)
    out_of_fence_count = total_count - valid_count

    attendance.total_heartbeats = total_count
    attendance.valid_heartbeats = valid_count
    attendance.out_of_fence_heartbeats = out_of_fence_count

    # Check for roaming anomalies (e.g. 2 consecutive out-of-fence pings or mock GPS)
    consecutive_out = 0
    max_consecutive_out = 0
    for hb in all_hb:
        if not hb.is_within_geofence:
            consecutive_out += 1
            if consecutive_out > max_consecutive_out:
                max_consecutive_out = consecutive_out
        else:
            consecutive_out = 0

    if is_mocked:
        attendance.roaming_anomaly_detected = True
        attendance.roaming_notes = "Mock GPS / location spoofing provider detected"
    elif max_consecutive_out >= 2:
        attendance.roaming_anomaly_detected = True
        attendance.roaming_notes = f"Extended absence detected: {out_of_fence_count} out-of-fence pings"

    attendance.save()

    return {
        "status": "success",
        "heartbeat_id": heartbeat.id,
        "is_within_geofence": is_within,
        "distance_meters": dist_int,
        "should_stop": False,
        "roaming_flag": attendance.roaming_anomaly_detected,
    }
