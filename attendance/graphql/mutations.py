import strawberry
from datetime import date, time
from typing import Optional

from attendance.graphql.types import (
    AttendanceRecordType,
    AttendanceCorrectionType
)
from attendance.models import AttendanceRecord, AttendanceCorrection
from attendance.services import check_in_user, check_out_user
from django.db import transaction
from graphql import GraphQLError

@strawberry.input
class CheckInInput:
    office_location_id: strawberry.ID
    latitude: float
    longitude: float
    login_time: time

@strawberry.input
class CheckOutInput:
    latitude: float
    longitude: float
    logout_time: time
 
@strawberry.input
class AttendanceCorrectionInput:
    attendance_record_id: strawberry.ID
    corrected_login_time: time
    corrected_logout_time: time
    reason: str


@strawberry.type
class AttendanceMutation:

    @strawberry.mutation
    def check_in(
        self,
        info,
        input: CheckInInput,
    ) -> AttendanceRecordType:

        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Not authenticated")

        attendance, _ = check_in_user(
            user=user,
            office_id=input.office_location_id,
            latitude=input.latitude,
            longitude=input.longitude,
            time=input.login_time,
        )

        return attendance

    @strawberry.mutation
    def check_out(
        self,
        info,
        input: CheckOutInput,
    ) -> AttendanceRecordType:

        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Not authenticated")

        attendance, _ = check_out_user(
            user=user,
            latitude=input.latitude,
            longitude=input.longitude,
            time=input.logout_time,
        )

        return attendance

        
    @strawberry.mutation
    def request_attendance_correction(
        self,
        info,
        input: AttendanceCorrectionInput,
    ) -> AttendanceCorrectionType:

        user = info.context.request.user

        record = AttendanceRecord.objects.get(id=input.attendance_record_id)

        return AttendanceCorrection.objects.create(
            attendance_record=record,
            requested_by=user,
            corrected_login_time=input.corrected_login_time or record.login_time,
            corrected_logout_time=input.corrected_logout_time or record.logout_time,
            reason=input.reason,
        )

        
    @strawberry.mutation
    def approve_attendance_correction(
        self,
        info,
        correction_id: strawberry.ID,
        status: str,
        approval_comments: Optional[str] = None,
    ) -> bool:
        approver = info.context.request.user

        # 🔐 Auth check
        # if not approver or getattr(approver, "is_anonymous", True):
        #     raise GraphQLError("Authentication required")

        # # 🔐 Role check
        # if approver.role not in ["admin", "hr", "manager"]:
        #     raise GraphQLError("Not authorized")

        # 🔎 Fetch correction
        try:
            correction = AttendanceCorrection.objects.select_related(
                "attendance_record"
            ).get(id=correction_id)
        except AttendanceCorrection.DoesNotExist:
            raise GraphQLError("Attendance correction not found")

        # 🛑 Prevent double approval/rejection
        if correction.status != "pending":
            raise GraphQLError("This correction has already been processed")

        # ✅ Apply decision
        if status == "approved":
            correction.approve(approver, approval_comments)

        elif status == "rejected":
            correction.reject(approver, approval_comments)

        else:
            raise GraphQLError("Invalid status. Use 'approved' or 'rejected'.")

        return True


    @strawberry.mutation
    def cancel_attendance_correction(self, info, correctionId: strawberry.ID) -> AttendanceCorrectionType:
        correction = AttendanceCorrection.objects.get(id=correctionId)

        correction.status = "cancelled"
        correction.save(update_fields=["status"])

        return correction
