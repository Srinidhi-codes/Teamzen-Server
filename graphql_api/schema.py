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

@strawberry.type
class Query(UserQuery, AttendanceQuery, LeaveQuery, OrganizationQuery, NotificationQuery, DashboardQuery):
    """
    Root Query:
    - me
    - myAttendance
    - attendanceByUser
    """
    pass


@strawberry.type
class Mutation(UserMutation, AttendanceMutation, LeaveMutation, OrganizationMutation, NotificationMutation):
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
