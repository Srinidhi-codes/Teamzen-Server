import strawberry

from users.graphql.queries import UserQuery
from attendance.graphql.queries import AttendanceQuery
from attendance.graphql.mutations import AttendanceMutation
from users.graphql.mutations import UserMutation


@strawberry.type
class Query(UserQuery, AttendanceQuery):
    """
    Root Query:
    - me
    - myAttendance
    - attendanceByUser
    """
    pass


@strawberry.type
class Mutation(UserMutation, AttendanceMutation):
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
