import strawberry
from users.graphql.queries import UserQuery
from attendance.graphql.queries import AttendanceQuery
from attendance.graphql.mutations import AttendanceMutation
from users.graphql.mutations import UserMutation
from leaves.graphql.queries import LeaveQuery
from leaves.graphql.mutations import LeaveMutation
from organizations.graphql.queries import OrganizationQuery
from organizations.graphql.mutations import OrganizationMutation
from notifications.graphql.queries import NotificationQuery
from notifications.graphql.mutations import NotificationMutation
from graphql_api.dashboard_queries import DashboardQuery
from payroll.graphql.queries import PayrollQuery
from payroll.graphql.mutations import PayrollMutation
from graphql_api.auth import Mutation as AuthMutation
from reports.graphql.queries import ReportsQuery
from performance.graphql.queries import PerformanceQuery
from performance.graphql.mutations import PerformanceMutation

@strawberry.type
class Query(UserQuery, AttendanceQuery, LeaveQuery, OrganizationQuery, NotificationQuery, DashboardQuery, PayrollQuery, ReportsQuery, PerformanceQuery):
    """
    Root Query:
    - me
    - myAttendance
    - attendanceByUser
    - reports + performance analytics
    """




@strawberry.type
class Mutation(UserMutation, AttendanceMutation, LeaveMutation, OrganizationMutation, NotificationMutation, PayrollMutation, AuthMutation, PerformanceMutation):
    """
    Root Mutation:
    - login (REST preferred)
    - checkIn
    - checkOut
    - requestAttendanceCorrection
    - performance cycles / goals / reviews
    """
    pass


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation
)
 
