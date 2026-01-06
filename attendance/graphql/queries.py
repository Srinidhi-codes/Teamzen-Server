import strawberry
from typing import List, Optional
from datetime import date
from attendance.models import AttendanceRecord, AttendanceCorrection
from attendance.graphql.types import AttendanceRecordType, AttendanceCorrectionType

@strawberry.input
class AttendanceInput:
    start_date: Optional[date]
    end_date: Optional[date]

@strawberry.type
class AttendanceQuery:

    @strawberry.field
    def my_attendance(
        self,
        info,
        input: Optional[AttendanceInput] = None,
    ) -> List[AttendanceRecordType]:
        """
        Logged-in user's attendance
        """
        user = info.context.request.user

        qs = AttendanceRecord.objects.filter(user=user)

        if not input:
            return qs.filter(attendance_date=date.today())

        if input.start_date and input.end_date:
            qs = qs.filter(
                attendance_date__gte=input.start_date,
                attendance_date__lte=input.end_date,
            )
        elif input.start_date:
            qs = qs.filter(attendance_date__gte=input.start_date)
        elif input.end_date:
            qs = qs.filter(attendance_date__lte=input.end_date)
        else:
            qs = qs.filter(attendance_date=date.today())

        return qs


    @strawberry.field
    def attendance_by_user(
        self,
        info,
        user_id: strawberry.ID,
    ) -> List[AttendanceRecordType]:
        """
        HR / Manager view
        """
        requester = info.context.request.user

        if requester.role not in ["hr", "admin", "manager"]:
            raise Exception("Not authorized")

        return AttendanceRecord.objects.filter(user_id=user_id)

    @strawberry.field
    def attendance_corrections(
        self,
        info,
        status: Optional[str] = None
    ) -> List[AttendanceCorrectionType]:

        user = info.context.request.user

        qs = AttendanceCorrection.objects.all()

        if user.role == "employee":
            qs = qs.filter(requested_by=user)

        if status:
            qs = qs.filter(status=status)

        return qs
