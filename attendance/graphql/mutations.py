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
    face_verified: Optional[bool] = None
    face_match_score: Optional[float] = None
    face_descriptor: Optional[list[float]] = None
    selfie_base64: Optional[str] = None
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    challenge_token: Optional[str] = None

@strawberry.input
class CheckOutInput:
    latitude: float
    longitude: float
    logout_time: time
    face_verified: Optional[bool] = None
    face_match_score: Optional[float] = None
    face_descriptor: Optional[list[float]] = None
    selfie_base64: Optional[str] = None
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    challenge_token: Optional[str] = None
 
@strawberry.input
class AttendanceCorrectionInput:
    attendance_record_id: strawberry.ID
    corrected_login_time: time
    corrected_logout_time: time
    reason: str
    category: Optional[str] = "FORGOT_TO_PUNCH"
    supporting_evidence_base64: Optional[str] = None

@strawberry.input
class ApproveAttendanceCorrectionInput:
    correction_id: strawberry.ID
    status: str
    approval_comments: Optional[str] = None

@strawberry.input
class ApproveOffHoursAttendanceInput:
    record_id: strawberry.ID
    status: str
    approval_remarks: Optional[str] = None

@strawberry.type
class ApproveOffHoursAttendancePayload:
    success: bool
    record: Optional[AttendanceRecordType] = None
    message: str = ""


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
            raise GraphQLError("Unauthenticated")

        attendance, _ = check_in_user(
            user=user,
            office_id=input.office_location_id,
            latitude=input.latitude,
            longitude=input.longitude,
            time=input.login_time,
            face_verified=input.face_verified,
            face_match_score=input.face_match_score,
            face_descriptor=input.face_descriptor,
            selfie_base64=input.selfie_base64,
            device_id=input.device_id,
            device_name=input.device_name,
            challenge_token=input.challenge_token,
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
            raise GraphQLError("Unauthenticated")

        attendance, _ = check_out_user(
            user=user,
            latitude=input.latitude,
            longitude=input.longitude,
            time=input.logout_time,
            face_verified=input.face_verified,
            face_match_score=input.face_match_score,
            face_descriptor=input.face_descriptor,
            selfie_base64=input.selfie_base64,
            device_id=input.device_id,
            device_name=input.device_name,
            challenge_token=input.challenge_token,
        )

        return attendance

        
    @strawberry.mutation
    def request_attendance_correction(
        self,
        info,
        input: AttendanceCorrectionInput,
    ) -> AttendanceCorrectionType:

        user = info.context.request.user
        if not user.is_authenticated:
            raise GraphQLError("Unauthenticated")

        from attendance.services import request_regularization_for_user
        import base64
        import uuid
        from django.core.files.base import ContentFile

        supporting_evidence_file = None
        if input.supporting_evidence_base64:
            try:
                raw_b64 = input.supporting_evidence_base64
                if ";base64," in raw_b64:
                    format_part, raw_b64 = raw_b64.split(";base64,", 1)
                    ext = "pdf" if "pdf" in format_part else ("png" if "png" in format_part else "jpg")
                else:
                    ext = "jpg"
                decoded_data = base64.b64decode(raw_b64)
                file_name = f"evidence_{user.id}_{uuid.uuid4().hex[:8]}.{ext}"
                supporting_evidence_file = ContentFile(decoded_data, name=file_name)
            except Exception:
                pass

        correction = request_regularization_for_user(
            user=user,
            attendance_record_id=input.attendance_record_id,
            corrected_login_time=input.corrected_login_time,
            corrected_logout_time=input.corrected_logout_time,
            reason=input.reason,
            category=input.category or "FORGOT_TO_PUNCH",
            supporting_evidence=supporting_evidence_file,
        )

        return correction

    @strawberry.mutation
    def approve_or_reject_attendance_correction(
        self,
        info,
        input: ApproveAttendanceCorrectionInput,
    ) -> bool:
        approver = info.context.request.user

        if not approver or getattr(approver, "is_anonymous", True):
            raise GraphQLError("Authentication required")

        from attendance.services import process_regularization_approval_decision
        process_regularization_approval_decision(
            correction_id=input.correction_id,
            action=input.status,
            approver=approver,
            comments=input.approval_comments or "",
        )

        return True


    @strawberry.mutation
    def cancel_attendance_correction(self, info, correctionId: strawberry.ID) -> AttendanceCorrectionType:
        correction = AttendanceCorrection.objects.get(id=correctionId)

        correction.cancel()
        correction.save()

        return correction

    @strawberry.mutation
    def approve_or_reject_off_hours_attendance(
        self, info, input: ApproveOffHoursAttendanceInput
    ) -> ApproveOffHoursAttendancePayload:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "hr", "manager", "superadmin"]:
            raise GraphQLError("You do not have permission to approve attendance.")

        from attendance.services import approve_or_reject_attendance_record
        record = approve_or_reject_attendance_record(
            record_id=int(input.record_id),
            action=input.status,
            manager_user=user,
            remarks=input.approval_remarks or ""
        )

        return ApproveOffHoursAttendancePayload(
            success=True,
            record=record,
            message=f"Attendance record has been successfully {input.status}."
        )
