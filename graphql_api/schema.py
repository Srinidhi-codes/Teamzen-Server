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
from feedback.graphql.queries import FeedbackQuery
from feedback.graphql.mutations import FeedbackMutation
from onboarding.graphql.queries import OnboardingQuery
from onboarding.graphql.mutations import OnboardingMutation
from documents.graphql.queries import DocumentsQuery
from documents.graphql.mutations import DocumentsMutation
from offboarding.graphql.queries import OffboardingQuery
from offboarding.graphql.mutations import OffboardingMutation
from ai_engine.graphql_queries import AiQuery

@strawberry.type
class Query(
    UserQuery,
    AttendanceQuery,
    LeaveQuery,
    OrganizationQuery,
    NotificationQuery,
    DashboardQuery,
    PayrollQuery,
    ReportsQuery,
    PerformanceQuery,
    FeedbackQuery,
    OnboardingQuery,
    DocumentsQuery,
    OffboardingQuery,
    AiQuery,
):
    """Root Query including onboarding, documents, offboarding and AI helpers."""


@strawberry.type
class Mutation(
    UserMutation,
    AttendanceMutation,
    LeaveMutation,
    OrganizationMutation,
    NotificationMutation,
    PayrollMutation,
    AuthMutation,
    PerformanceMutation,
    FeedbackMutation,
    OnboardingMutation,
    DocumentsMutation,
    OffboardingMutation,
):
    """Root Mutation including onboarding, documents and offboarding."""
    pass


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation
)
