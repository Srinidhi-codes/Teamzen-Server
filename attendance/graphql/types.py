from typing import Optional
import strawberry
import strawberry.django
from strawberry import auto

from attendance.models import AttendanceRecord, AttendanceCorrection
from users.graphql.types import UserType
from organizations.graphql.types import OfficeLocationType

@strawberry.django.type(AttendanceRecord)
class AttendanceRecordType:
    id: strawberry.ID
    attendance_date: auto
    login_time: auto
    logout_time: auto

    login_latitude: auto
    login_longitude: auto
    logout_latitude: auto
    logout_longitude: auto
    login_distance: auto
    logout_distance: auto

    is_within_geofence: auto
    status: auto
    worked_hours: auto
    remarks: auto
    is_verified: auto

    user: UserType
    office_location: OfficeLocationType

    created_at: auto
    updated_at: auto

@strawberry.django.type(AttendanceCorrection)
class AttendanceCorrectionType:
    id: strawberry.ID
    attendance_record: AttendanceRecordType
    requested_by: UserType
    approved_by: Optional[UserType]

    corrected_login_time: auto
    corrected_logout_time: auto
    reason: auto
    status: auto
    approval_comments: auto

    created_at: auto


# @strawberry.django.type(AttendanceRecord)
# class AttendanceRecordType:
#     id: strawberry.ID
#     attendance_date: auto
#     login_time: auto
#     logout_time: auto
#     status: auto
#     worked_hours: auto
#     is_within_geofence: auto
#     remarks: auto


# @strawberry.django.type(AttendanceCorrection)
# class AttendanceCorrectionType:
#     id: strawberry.ID
#     reason: auto
#     status: auto
#     corrected_login_time: auto
#     corrected_logout_time: auto
#     created_at: auto
