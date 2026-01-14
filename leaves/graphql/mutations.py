import strawberry
from datetime import date, time
from typing import Optional

from leaves.models import LeaveType, LeaveBalance, LeaveRequest, CompanyHoliday
from leaves.graphql.types import LeaveTypeType, LeaveBalanceType, LeaveRequestType, CompanyHolidayType

@strawberry.type
class LeaveMutation:
    @strawberry.mutation
    def create_leave_type(
        self,
        info,
        name: str,
        organization_id: Optional[strawberry.ID] = None,
    ) -> LeaveTypeType:
        leave_type = LeaveType.objects.create(name=name, organization_id=organization_id)
        return LeaveTypeType.from_django_object(leave_type)
