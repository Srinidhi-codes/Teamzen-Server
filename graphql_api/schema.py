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

@strawberry.type
class Query(UserQuery, AttendanceQuery, LeaveQuery, OrganizationQuery, NotificationQuery, DashboardQuery, PayrollQuery):
    """
    Root Query:
    - me
    - myAttendance
    - attendanceByUser
    """




@strawberry.type
class Mutation(UserMutation, AttendanceMutation, LeaveMutation, OrganizationMutation, NotificationMutation, PayrollMutation, AuthMutation):
    """
    Root Mutation:
    - login (REST preferred)
    - checkIn
    - checkOut
    - requestAttendanceCorrection
    """
    pass


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation
)
 
