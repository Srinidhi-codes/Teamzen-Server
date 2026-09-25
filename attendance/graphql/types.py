from typing import Optional, List
import strawberry
import strawberry.django
from strawberry import auto

from attendance.models import AttendanceRecord, AttendanceCorrection, AttendanceHeartbeat
from users.graphql.types import UserType
from organizations.graphql.types import OfficeLocationType

@strawberry.django.type(AttendanceHeartbeat)
class AttendanceHeartbeatType:
    id: strawberry.ID
    timestamp: auto
    latitude: auto
    longitude: auto
    distance_meters: auto
    is_within_geofence: auto
    accuracy_meters: auto
    is_mocked: auto
    battery_level: auto

@strawberry.django.type(AttendanceRecord)
class AttendanceRecordType:
    id: strawberry.ID
    attendance_date: auto
    login_time: auto
    logout_time: auto
    actual_login_time: auto
    actual_logout_time: auto

    login_latitude: auto
    login_longitude: auto
    logout_latitude: auto
    logout_longitude: auto
    login_distance: auto
    logout_distance: auto

    is_within_geofence: auto
    face_verified: auto
    face_match_score: auto
    status: auto
    worked_hours: auto
    effective_worked_hours: auto
    total_heartbeats: auto
    valid_heartbeats: auto
    out_of_fence_heartbeats: auto
    roaming_anomaly_detected: auto
    roaming_notes: auto
    remarks: auto
    is_verified: auto

    user: UserType
    office_location: OfficeLocationType

    created_at: auto
    updated_at: auto

    @strawberry.field
    def heartbeats(self) -> List[AttendanceHeartbeatType]:
        return list(self.heartbeats.all().order_by("timestamp"))

    @strawberry.field
    def check_in_selfie_url(self) -> Optional[str]:
        if self.check_in_selfie:
            return self.check_in_selfie.url
        return None

    @strawberry.field
    def check_out_selfie_url(self) -> Optional[str]:
        if self.check_out_selfie:
            return self.check_out_selfie.url
        return None

    @strawberry.field
    def correction_reason(self) -> Optional[str]:
        correction = (
            self.attendancecorrection_set.order_by("-created_at").first()
        )
        return correction.reason if correction else None

    @strawberry.field
    def correction_status(self) -> Optional[str]:
        correction = (
            self.attendancecorrection_set.order_by("-created_at").first()
        )
        return correction.status if correction else None

    @strawberry.field
    def correction_id(self) -> Optional[strawberry.ID]:
        correction = (
            self.attendancecorrection_set.order_by("-created_at").first()
        )
        return correction.id if correction else None

    @strawberry.field
    def approval_comment(self) -> Optional[str]:
        correction = (
            self.attendancecorrection_set.order_by("-created_at").first()
        )
        return correction.approval_comments if correction else None

@strawberry.django.type(AttendanceCorrection)
class AttendanceCorrectionType:
    id: strawberry.ID
    attendance_record: AttendanceRecordType
    requested_by: UserType
    approved_by: Optional[UserType]

    corrected_login_time: auto
    corrected_logout_time: auto
    reason: auto
    status: str
    approval_comments: auto

    created_at: auto

