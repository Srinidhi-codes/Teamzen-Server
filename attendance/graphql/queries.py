import strawberry
from typing import List, Optional
from datetime import date, time
from django.db.models import Q
from attendance.models import AttendanceRecord, AttendanceCorrection
from attendance.graphql.types import AttendanceRecordType, AttendanceCorrectionType
from users.models import CustomUser
from users.graphql.types import UserType

# =====================================================
# INPUT TYPES
# =====================================================

@strawberry.input
class AttendanceInput:
    start_date: Optional[date]
    end_date: Optional[date]

@strawberry.input
class AttendanceCorrectionSortInput:
    field: str = "created_at"
    direction: str = "desc"

@strawberry.input
class AttendanceCorrectionFilterInput:
    search: Optional[str] = None
    status: Optional[str] = None

# =====================================================
# RESPONSE TYPES
# =====================================================

@strawberry.type
class PaginatedAttendanceCorrectionResponse:
    results: List[AttendanceCorrectionType]
    total: int
    page: int
    page_size: int


@strawberry.type
class TeamAttendanceTodayItem:
    user: UserType
    status: str  # present | absent | leave
    login_time: Optional[time] = None
    logout_time: Optional[time] = None
    record_status: Optional[str] = None


PRESENT_STATUSES = {"present", "late_login", "early_logout", "half_day"}

# =====================================================
# QUERIES
# =====================================================

@strawberry.type
class AttendanceQuery:
    # -------------------------
    # MY ATTENDANCE
    # ------------------------
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
        if not user.is_authenticated:
            return []

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

    # -------------------------
    # ATTENDANCE BY USER
    # -------------------------
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
        if not requester.is_authenticated:
            raise Exception("Not authorized")

        if requester.role == "superadmin":
            return AttendanceRecord.objects.filter(user_id=user_id)

        if requester.role not in ["hr", "admin", "manager"]:
            raise Exception("Not authorized")

        try:
            target_user = CustomUser.objects.get(pk=user_id)
            if target_user.organization_id != requester.organization_id:
                raise Exception("Not authorized to view users from other organizations")
        except CustomUser.DoesNotExist:
             return []

        return AttendanceRecord.objects.filter(user_id=user_id)

    # -------------------------
    # TEAM ATTENDANCE TODAY
    # -------------------------
    @strawberry.field
    def team_attendance_today(self, info) -> List[TeamAttendanceTodayItem]:
        """
        Present / absent / leave for the viewer's reporting circle today.
        Circle = self + manager + peers + direct reports.
        """
        user = info.context.request.user
        if not user.is_authenticated:
            return []

        today = date.today()

        member_ids = {user.pk}
        if user.manager_id:
            member_ids.add(user.manager_id)

        if user.manager_id:
            for peer_id in CustomUser.objects.filter(manager_id=user.manager_id).exclude(pk=user.pk).values_list("pk", flat=True):
                member_ids.add(peer_id)

        for sub_id in user.subordinates.filter(is_active=True).values_list("pk", flat=True):
            member_ids.add(sub_id)

        members = (
            CustomUser.objects.filter(pk__in=member_ids, is_active=True)
            .select_related("designation", "department", "organization")
            .order_by("first_name", "last_name")
        )

        records = {
            r.user_id: r
            for r in AttendanceRecord.objects.filter(
                user_id__in=member_ids,
                attendance_date=today,
            )
        }

        on_leave_ids: set = set()
        try:
            from leaves.models import LeaveRequest
            on_leave_ids = set(
                LeaveRequest.objects.filter(
                    user_id__in=member_ids,
                    _status="approved",
                    from_date__lte=today,
                    to_date__gte=today,
                ).values_list("user_id", flat=True)
            )
        except Exception:
            on_leave_ids = set()

        results: List[TeamAttendanceTodayItem] = []
        for member in members:
            record = records.get(member.pk)
            if member.pk in on_leave_ids or (record and record.status == "leave"):
                status = "leave"
            elif record and (record.login_time or record.status in PRESENT_STATUSES):
                status = "present"
            else:
                status = "absent"

            results.append(
                TeamAttendanceTodayItem(
                    user=member,
                    status=status,
                    login_time=record.login_time if record else None,
                    logout_time=record.logout_time if record else None,
                    record_status=record.status if record else None,
                )
            )

        order = {"present": 0, "leave": 1, "absent": 2}
        results.sort(key=lambda item: (order.get(item.status, 9), item.user.first_name or ""))
        return results

    # -------------------------
    # ATTENDANCE CORRECTIONS
    # -------------------------
    @strawberry.field
    def attendance_corrections(
        self,
        info,
        page: int = 1,
        page_size: int = 10,
        filters: Optional[AttendanceCorrectionFilterInput] = None,
        sort: Optional[AttendanceCorrectionSortInput] = None,
        input: Optional[AttendanceInput] = None
    ) -> PaginatedAttendanceCorrectionResponse:
        
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Not authorized")

        qs = AttendanceCorrection.objects.select_related(
            "attendance_record",
            "requested_by",
            "approved_by",
        )

        if user.role == "superadmin":
            pass
        elif user.role == "employee":
            qs = qs.filter(requested_by=user)
        elif user.role in ["admin", "hr"]:
            qs = qs.filter(requested_by__organization_id=user.organization_id)
        elif user.role == "manager":
            qs = qs.filter(
                Q(requested_by=user) | Q(requested_by__manager=user),
                requested_by__organization_id=user.organization_id
            )
        else:
            raise Exception("Not authorized")

        if filters:
            if filters.status:
                qs = qs.filter(_status=filters.status)

        if input:
            if input.start_date and input.end_date:
                qs = qs.filter(
                    attendance_record__attendance_date__range=(input.start_date, input.end_date)
                )
            elif input.start_date:
                 qs = qs.filter(attendance_record__attendance_date__gte=input.start_date)
            elif input.end_date:
                 qs = qs.filter(attendance_record__attendance_date__lte=input.end_date)

        if filters:
             if filters.search:
                 search = filters.search.strip()
                 qs = qs.filter(
                     Q(requested_by__first_name__icontains=search) |
                     Q(requested_by__last_name__icontains=search) |
                     Q(requested_by__email__icontains=search) |
                     Q(approved_by__first_name__icontains=search) |
                     Q(approved_by__last_name__icontains=search) |
                     Q(approved_by__email__icontains=search) |
                     Q(attendance_record__attendance_date__icontains=search)
                 )

        from graphql_utils.pagination import get_paginated_results
        
        paginated = get_paginated_results(qs, page, page_size, sort)

        return PaginatedAttendanceCorrectionResponse(**paginated)
