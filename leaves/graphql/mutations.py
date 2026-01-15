import strawberry
from datetime import date, time
from typing import Optional

from leaves.models import LeaveType, LeaveBalance, LeaveRequest, CompanyHoliday
from leaves.graphql.types import LeaveTypeType, LeaveBalanceType, LeaveRequestType, CompanyHolidayType
from leaves.services import (
    validate_balance,
    get_or_create_balance,
    reserve_balance,
    consume_balance,
    release_balance,
)

@strawberry.input
class LeaveRequestInput:
    leave_type_id: strawberry.ID
    from_date: date
    to_date: date
    reason: str

@strawberry.input
class LeaveRequestApprovalInput:
    request_id: strawberry.ID
    status: str
    comments: str

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

    @strawberry.mutation
    def create_leave_request(
        self,
        info,
        input: LeaveRequestInput,
    ) -> LeaveRequestType:
        user = info.context.request.user
        duration = (input.to_date - input.from_date).days + 1
        leave_type = LeaveType.objects.get(id=input.leave_type_id)

        balance = get_or_create_balance(user, leave_type)
        validate_balance(balance, duration)
        reserve_balance(balance, duration)

        leave_request = LeaveRequest.objects.create(
            user=user,
            leave_type=leave_type,
            from_date=input.from_date,
            to_date=input.to_date,
            duration_days=duration,
            reason=input.reason,
            status='pending'
        )

        return leave_request
    
    @strawberry.mutation
    def leave_request_process(self, info, input: LeaveRequestApprovalInput) -> LeaveRequestType:
        # hr_user = info.context.request.user or 1
        req = LeaveRequest.objects.get(id=input.request_id)

        if input.status == 'approved':
            balance = get_or_create_balance(req.user, req.leave_type)
            consume_balance(balance, req.duration_days)
            req.status = 'approved'
            # req.approved_by = 1
            req.approval_comments = input.comments
            req.save(update_fields=['status','approved_by','approval_comments'])

        elif input.status == 'rejected':
            balance = get_or_create_balance(req.user, req.leave_type)
            release_balance(balance, req.duration_days)
            req.status = 'rejected'
            req.approval_comments = input.comments
            req.save(update_fields=['status','approval_comments'])

        return req


    @strawberry.mutation
    def cancel_leave_request(self, info, requestId: strawberry.ID) -> LeaveRequestType:
        req = LeaveRequest.objects.get(id=requestId)

        balance = get_or_create_balance(req.user, req.leave_type)
        release_balance(balance, req.duration_days)

        req.status = 'cancelled'
        req.save(update_fields=['status'])

        return req
    