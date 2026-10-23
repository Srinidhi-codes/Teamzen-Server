from math import radians, sin, cos, sqrt, atan2
from datetime import date, datetime, timedelta, time as time_type
import base64
import re
import uuid
from django.core.files.base import ContentFile
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from django.core import signing
from graphql import GraphQLError

from attendance.models import (
    AttendanceRecord,
    AttendanceHeartbeat,
    AttendanceCorrection,
    UserDeviceBinding,
)
from attendance.face_constants import (
    FACE_DESCRIPTOR_DIM,
    FACE_DISTANCE_THRESHOLD,
    FACE_MATCH_THRESHOLD,
)
from organizations.models import OfficeLocation
from organizations.workweek import is_org_weekend
from leaves.models import CompanyHoliday
from payroll.models import PayrollRun


def save_selfie_base64_to_field(image_field, base64_str: str | None, filename: str):
    if not base64_str or not isinstance(base64_str, str) or len(base64_str) < 50:
        return
    match = re.match(r"^data:image/(png|jpeg|jpg|webp);base64,(.+)$", base64_str, re.I | re.S)
    if match:
        ext = "jpg" if match.group(1).lower() in ("jpeg", "jpg") else match.group(1).lower()
        b64_data = match.group(2)
    else:
        ext = "jpg"
        b64_data = base64_str
    try:
        img_bytes = base64.b64decode(b64_data)
        image_field.save(f"{filename}.{ext}", ContentFile(img_bytes), save=False)
    except Exception:
        pass


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


from django.core.cache import cache

def generate_face_challenge_token(user_id: int | str) -> str:
    """
    Issues a short-lived (180s) cryptographically signed challenge token with a unique nonce
    to bind the verification attempt to the authenticated user and prevent replay attacks.
    """
    signer = signing.TimestampSigner(salt="face_punch_challenge")
    payload = {
        "user_id": str(user_id),
        "nonce": uuid.uuid4().hex,
        "ts": timezone.now().timestamp(),
    }
    return signer.sign_object(payload)


def validate_face_challenge_token(user, challenge_token: str | None) -> None:
    """
    Validates a short-lived cryptographically signed challenge token to prevent replay attacks.
    """
    if not challenge_token or not isinstance(challenge_token, str):
        return
    signer = signing.TimestampSigner(salt="face_punch_challenge")
    try:
        data = signer.unsign_object(challenge_token, max_age=180)
        token_user_id = str(data.get("user_id"))
        if token_user_id != str(user.id):
            raise GraphQLError("Challenge token does not match authenticated user.")
        
        # Anti-replay: Ensure nonce cannot be reused
        nonce = data.get("nonce")
        if nonce:
            cache_key = f"face_challenge_used:{nonce}"
            if cache.get(cache_key):
                raise GraphQLError("Face challenge token has already been consumed (anti-replay). Please capture again.")
            cache.set(cache_key, 1, timeout=300)
    except signing.SignatureExpired:
        raise GraphQLError("Face verification session expired. Please retry.")
    except GraphQLError:
        raise
    except Exception:
        raise GraphQLError("Invalid face verification challenge token.")


def assert_device_binding_allowed(user, device_id: str | None, device_name: str | None = None):
    """
    Validates that attendance is punched exclusively from a registered personal device.
    Blocks coworker/buddy logins from foreign devices when device_binding_enforced is True.
    """
    org = getattr(user, "organization", None)
    if not org or not getattr(org, "device_binding_enforced", False):
        return

    if not device_id or not str(device_id).strip():
        raise GraphQLError(
            "Device identification required by company policy. Punch from an authorized registered device."
        )

    device_id = str(device_id).strip()

    # Query active bindings for user
    existing_bindings = UserDeviceBinding.objects.filter(user=user, is_active=True)
    if not existing_bindings.exists():
        # First-time device enrollment for employee
        UserDeviceBinding.objects.create(
            user=user,
            device_id=device_id,
            device_name=device_name or "Primary Device",
            is_trusted=True,
            is_active=True,
        )
        return

    matching = existing_bindings.filter(device_id=device_id, is_trusted=True).first()
    if not matching:
        raise GraphQLError(
            "Unregistered device detected. You can only punch attendance from your registered personal device. "
            "If you recently changed your phone or computer, contact HR to authorize a device replacement."
        )
    matching.save(update_fields=["last_seen_at"])


def assert_face_attendance_allowed(
    user,
    *,
    face_descriptor: list[float] | None = None,
    face_verified: bool | None = None,
    face_match_score: float | None = None,
    challenge_token: str | None = None,
) -> float:
    """
    Validate face punch. Returns server-computed similarity in [0, 1].
    Always recomputes Euclidean distance vs enrolled template(s) — client flags alone are not enough.
    Supports single template as well as alternative appearances (e.g. with/without glasses).
    """
    if not org_requires_face(user):
        return 0.0

    if challenge_token:
        validate_face_challenge_token(user, challenge_token)

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


def evaluate_shift_and_calendar_window(attendance: AttendanceRecord, office: OfficeLocation, user, checkin_time: time_type):
    """
    Evaluates whether check-in is during a weekend/company holiday or outside the allowed shift window.
    Standard window: 1 hr before office.login_time to 2 hrs before office.logout_time.
    Tags attendance with is_weekend_work / is_off_hours and approval_status='pending' if outside window.
    """
    today = attendance.attendance_date or date.today()
    org = getattr(user, "organization", None)

    is_weekend = False
    is_holiday = False
    if org:
        is_weekend = is_org_weekend(today, org)
        is_holiday = CompanyHoliday.objects.filter(organization=org, holiday_date=today).exists()

    if is_weekend or is_holiday:
        attendance.is_weekend_work = True
        attendance.approval_status = "pending"
        attendance.approval_remarks = "Holiday check-in (pending approval)" if is_holiday else "Weekend check-in (pending approval)"
        return

    # Evaluate shift window (only if office has login & logout times)
    if office and office.login_time and office.logout_time and checkin_time:
        checkin_min = checkin_time.hour * 60 + checkin_time.minute
        shift_start_min = office.login_time.hour * 60 + office.login_time.minute
        shift_end_min = office.logout_time.hour * 60 + office.logout_time.minute

        # Earliest = 1 hour before shift start, Latest = 2 hours before shift end
        earliest_min = max(0, shift_start_min - 60)
        latest_min = max(0, shift_end_min - 120)

        # Off-hours check (e.g. midnight, early morning < earliest_min, or after latest_min)
        if checkin_min < earliest_min or checkin_min > latest_min:
            attendance.is_off_hours = True
            attendance.approval_status = "pending"
            earliest_t = time_type(earliest_min // 60, earliest_min % 60)
            latest_t = time_type(latest_min // 60, latest_min % 60)
            attendance.approval_remarks = (
                f"Off-hours check-in at {checkin_time.strftime('%I:%M %p')} "
                f"(Allowed window: {earliest_t.strftime('%I:%M %p')} - {latest_t.strftime('%I:%M %p')})"
            )
            return

    # Normal shift on regular working day
    if attendance.approval_status not in ["approved", "rejected"]:
        attendance.is_weekend_work = False
        attendance.is_off_hours = False
        attendance.approval_status = "auto_approved"


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
    selfie_base64: str | None = None,
    device_id: str | None = None,
    device_name: str | None = None,
    challenge_token: str | None = None,
):
    # Enforce device registration check
    assert_device_binding_allowed(user, device_id, device_name)

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
            challenge_token=challenge_token,
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

    if selfie_base64:
        save_selfie_base64_to_field(
            attendance.check_in_selfie,
            selfie_base64,
            f"selfie_{attendance.id}_check_in",
        )

    # Evaluate shift window & weekend/holiday constraints
    evaluate_shift_and_calendar_window(attendance, office, user, attendance.login_time)
    attendance.save()

    # Automatically record initial check-in breadcrumb / heartbeat
    AttendanceHeartbeat.objects.create(
        attendance_record=attendance,
        latitude=latitude,
        longitude=longitude,
        distance_meters=int(distance),
        is_within_geofence=is_within,
    )
    all_hb = list(attendance.heartbeats.all().order_by("timestamp"))
    total_count = len(all_hb)
    valid_count = sum(1 for hb in all_hb if hb.is_within_geofence)
    out_of_fence_count = total_count - valid_count

    attendance.total_heartbeats = total_count
    attendance.valid_heartbeats = valid_count
    attendance.out_of_fence_heartbeats = out_of_fence_count
    if not is_within:
        attendance.roaming_anomaly_detected = True
        attendance.roaming_notes = (
            f"Checked in {int(distance)}m outside office geofence ({round(distance / 1000, 2)}km away)"
        )
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
    selfie_base64: str | None = None,
    device_id: str | None = None,
    device_name: str | None = None,
    challenge_token: str | None = None,
):
    # Enforce device registration check
    assert_device_binding_allowed(user, device_id, device_name)

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
    is_out_within = distance <= office.geo_radius_meters
    face_mode = org_requires_face(user)
    server_face_score = None

    if face_mode:
        server_face_score = assert_face_attendance_allowed(
            user,
            face_descriptor=face_descriptor,
            face_verified=face_verified,
            face_match_score=face_match_score,
            challenge_token=challenge_token,
        )

    logout_time = normalize_time(time)
    attendance.logout_time = logout_time
    attendance.actual_logout_time = logout_time
    attendance.logout_latitude = latitude
    attendance.logout_longitude = longitude
    attendance.logout_distance = int(distance)

    if not is_out_within:
        attendance.is_within_geofence = False

    if face_mode:
        attendance.face_verified = True
        attendance.face_match_score = server_face_score

    if selfie_base64:
        save_selfie_base64_to_field(
            attendance.check_out_selfie,
            selfie_base64,
            f"selfie_{attendance.id}_check_out",
        )

    attendance.save()

    # Automatically record check-out breadcrumb / heartbeat
    AttendanceHeartbeat.objects.create(
        attendance_record=attendance,
        latitude=latitude,
        longitude=longitude,
        distance_meters=int(distance),
        is_within_geofence=is_out_within,
    )
    all_hb = list(attendance.heartbeats.all().order_by("timestamp"))
    total_count = len(all_hb)
    valid_count = sum(1 for hb in all_hb if hb.is_within_geofence)
    out_of_fence_count = total_count - valid_count

    attendance.total_heartbeats = total_count
    attendance.valid_heartbeats = valid_count
    attendance.out_of_fence_heartbeats = out_of_fence_count
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


def approve_or_reject_attendance_record(
    record_id: int,
    action: str,  # "approved" | "rejected"
    manager_user,
    remarks: str = ""
) -> AttendanceRecord:
    record = get_object_or_404(AttendanceRecord, id=record_id)
    if action not in ["approved", "rejected"]:
        raise GraphQLError("Action must be either 'approved' or 'rejected'.")

    record.approval_status = action
    record.approved_by = manager_user
    if remarks:
        record.approval_remarks = remarks

    # Recalculate status and save (if rejected, recalculate_status sets status='absent')
    record.save()
    return record


# =============================================================================
# ENTERPRISE ATTENDANCE REGULARIZATION POLICY ENGINE
# =============================================================================

def count_business_days(start_date: date, end_date: date, weekend_days: list[int] | None = None) -> int:
    """Calculate working business days between two dates, excluding weekends."""
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    weekends = set(weekend_days if weekend_days is not None else [6])  # Sunday default
    cur = start_date + timedelta(days=1)
    b_days = 0
    while cur <= end_date:
        if cur.weekday() not in weekends:
            b_days += 1
        cur += timedelta(days=1)
    return b_days


def get_monthly_regularization_quota_summary(user, target_date: date | None = None) -> dict:
    """
    Returns the employee's monthly regularization allowance, used count, and remaining quota.
    """
    org = getattr(user, "organization", None)
    monthly_limit = getattr(org, "attendance_regularization_monthly_limit", 3) if org else 3
    deadline_days = getattr(org, "attendance_regularization_deadline_days", 3) if org else 3

    target = target_date or timezone.localdate()
    month_start = date(target.year, target.month, 1)
    next_month = date(
        target.year + (1 if target.month == 12 else 0),
        1 if target.month == 12 else target.month + 1,
        1,
    )

    used_count = AttendanceCorrection.objects.filter(
        requested_by=user,
        attendance_record__attendance_date__gte=month_start,
        attendance_record__attendance_date__lt=next_month,
        _status__in=["pending", "approved"],
    ).count()

    remaining = max(0, monthly_limit - used_count)
    return {
        "monthly_limit": monthly_limit,
        "used_count": used_count,
        "remaining_count": remaining,
        "deadline_days": deadline_days,
        "is_exhausted": remaining <= 0,
    }


def request_regularization_for_user(
    *,
    user,
    attendance_record_id: int | str,
    corrected_login_time: time_type | None = None,
    corrected_logout_time: time_type | None = None,
    reason: str,
    category: str = "FORGOT_TO_PUNCH",
    supporting_evidence = None,
) -> AttendanceCorrection:
    """
    Validates and submits an attendance regularization request governed by:
    - Tenant ownership & permission boundaries.
    - Payroll lock period prevention (frozen finalized payroll periods).
    - Hard submission SLA window (e.g. within 3 business days of incident).
    - Monthly quota cap with database concurrency locking (select_for_update).
    - Duplicate pending request check.
    - Shift-constrained time boundaries and overtime guardrails.
    - Automatic escalation to HR for 3rd/threshold requests.
    """
    record = get_object_or_404(
        AttendanceRecord.objects.select_related("user", "user__organization", "office_location"),
        id=attendance_record_id,
    )

    # 1. Identity & Tenant isolation check
    if record.user_id != user.id and user.role not in ["superadmin", "admin", "hr"]:
        raise GraphQLError("You can only request regularization for your own attendance records.")

    if user.organization_id and record.user.organization_id != user.organization_id and user.role != "superadmin":
        raise GraphQLError("Cross-tenant access forbidden.")

    # 2. Duplicate Pending Check
    if AttendanceCorrection.objects.filter(attendance_record=record, _status="pending").exists():
        raise GraphQLError("A pending regularization request already exists for this attendance date.")

    # 3. Payroll Lock Check: Prevent changes to finalized payroll periods
    is_payroll_locked = PayrollRun.objects.filter(
        organization=record.user.organization,
        month=record.attendance_date.month,
        year=record.attendance_date.year,
        status="completed",
    ).exists()
    if is_payroll_locked and user.role not in ["superadmin", "admin"]:
        raise GraphQLError(
            "Attendance for this period is locked because payroll has already been finalized. "
            "Adjustments require an authorized HR payroll exception."
        )

    org = record.user.organization
    deadline_days = getattr(org, "attendance_regularization_deadline_days", 3) or 3
    weekend_days = getattr(org, "weekend_days", [6])
    today = timezone.localdate()

    # 4. Time-Barring Submission Window Check
    elapsed_business_days = count_business_days(record.attendance_date, today, weekend_days)
    if elapsed_business_days > deadline_days and user.role not in ["superadmin", "admin", "hr"]:
        raise GraphQLError(
            f"Submission window expired. Regularization requests must be submitted within {deadline_days} "
            f"business days of the attendance discrepancy. Please contact HR for exception handling."
        )

    monthly_limit = getattr(org, "attendance_regularization_monthly_limit", 3) or 3
    escalation_limit = getattr(org, "attendance_regularization_escalation_limit", 3) or 3

    # 5. Concurrency-Safe Monthly Quota Check (Row locking with select_for_update)
    with transaction.atomic():
        month_start = date(record.attendance_date.year, record.attendance_date.month, 1)
        next_month = date(
            record.attendance_date.year + (1 if record.attendance_date.month == 12 else 0),
            1 if record.attendance_date.month == 12 else record.attendance_date.month + 1,
            1,
        )

        existing_month_count = (
            AttendanceCorrection.objects.select_for_update()
            .filter(
                requested_by=record.user,
                attendance_record__attendance_date__gte=month_start,
                attendance_record__attendance_date__lt=next_month,
                _status__in=["pending", "approved"],
            )
            .count()
        )

        if existing_month_count >= monthly_limit and user.role not in ["superadmin", "admin", "hr"]:
            raise GraphQLError(
                f"Monthly regularization quota ({monthly_limit} requests) exhausted for this month. "
                "Any further adjustments require direct HR authorization."
            )

        escalated_to_hr = False
        policy_notes = ""
        if existing_month_count + 1 >= escalation_limit:
            escalated_to_hr = True
            policy_notes = f"Request #{existing_month_count + 1} this month (Exceeds {escalation_limit - 1} manager threshold). Escalated to HR."

        shift_login = record.office_location.login_time if record.office_location else time_type(9, 0)
        shift_logout = record.office_location.logout_time if record.office_location else time_type(18, 0)

        # Guardrail against unauthorized overtime generation
        if corrected_logout_time and corrected_logout_time > shift_logout and category != "CLIENT_VISIT_ON_DUTY":
            policy_notes = (policy_notes + f" Requested logout {corrected_logout_time} extends beyond shift end {shift_logout}.").strip()

        correction = AttendanceCorrection.objects.create(
            attendance_record=record,
            requested_by=user,
            category=category or "FORGOT_TO_PUNCH",
            corrected_login_time=corrected_login_time or record.login_time,
            corrected_logout_time=corrected_logout_time or record.logout_time,
            original_login_time=record.actual_login_time or record.login_time,
            original_logout_time=record.actual_logout_time or record.logout_time,
            system_suggested_login_time=shift_login,
            system_suggested_logout_time=shift_logout,
            reason=reason.strip() if reason else "",
            supporting_evidence=supporting_evidence,
            escalated_to_hr=escalated_to_hr,
            policy_violation_notes=policy_notes,
        )

    # Notify Management
    try:
        from notifications.utils import notify_management
        msg = f"New attendance correction request ({category}) from {user.first_name} {user.last_name} for {record.attendance_date}."
        if escalated_to_hr:
            msg += " [ESCALATED TO HR]"
        notify_management(
            user=user,
            verb="requested",
            message=msg,
            target_type="Attendance Correction",
            target_id=str(correction.id),
        )
    except Exception:
        pass

    return correction


def process_regularization_approval_decision(
    *,
    correction_id: int | str,
    action: str,  # "approved" | "rejected"
    approver,
    comments: str = "",
) -> AttendanceCorrection:
    """
    Processes manager/HR approval or rejection with strict enterprise safeguards:
    - Rejects self-approval attempts.
    - Enforces tenant isolation.
    - Enforces HR role requirement for quota-escalated requests.
    - Requires mandatory rejection reasons.
    - Preserves historical punch records and updates effective status atomically.
    """
    if action not in ["approved", "rejected"]:
        raise GraphQLError("Action must be 'approved' or 'rejected'.")

    correction = get_object_or_404(
        AttendanceCorrection.objects.select_related("attendance_record", "requested_by"),
        id=correction_id,
    )

    if correction.status != "pending":
        raise GraphQLError("This regularization request has already been processed.")

    # 1. Prevent self-approval
    if correction.requested_by_id == approver.id and approver.role != "superadmin":
        raise GraphQLError("Self-approval is strictly prohibited. Regularization must be reviewed by a manager or HR.")

    # 2. Tenant isolation check
    if (
        approver.organization_id
        and correction.requested_by.organization_id != approver.organization_id
        and approver.role != "superadmin"
    ):
        raise GraphQLError("Cross-tenant decision forbidden.")

    # 3. Escalated to HR permission check
    if correction.escalated_to_hr and approver.role not in ["superadmin", "admin", "hr"]:
        raise GraphQLError("This correction has been escalated due to monthly quota threshold and requires HR approval.")

    # 4. Mandatory rejection reason check
    if action == "rejected" and not (comments and comments.strip()):
        raise GraphQLError("A rejection reason/comment is required when rejecting a regularization request.")

    with transaction.atomic():
        if action == "approved":
            correction.approve(approver, comments.strip())
        else:
            correction.reject(approver, comments.strip())
        correction.save()

    # 5. Notify employee
    try:
        from notifications.utils import notify_user
        verb = "approved" if action == "approved" else "rejected"
        msg = f"Your attendance correction for {correction.attendance_record.attendance_date} has been {verb.upper()}."
        if comments:
            msg += f" Reason: {comments}"
        notify_user(
            recipient_id=correction.requested_by.id,
            verb=verb,
            message=msg,
            actor_id=approver.id,
            target_type="Attendance Correction",
            target_id=str(correction.id),
            level="personal",
        )
    except Exception:
        pass

    return correction
