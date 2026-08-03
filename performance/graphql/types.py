import strawberry
from typing import Optional, List
from datetime import date


@strawberry.type
class PerformanceCycleType:
    id: strawberry.ID
    name: str
    description: str
    start_date: date
    end_date: date
    status: str
    organization_id: strawberry.ID
    review_count: int = 0
    completed_reviews: int = 0
    goal_count: int = 0


@strawberry.type
class GoalType:
    id: strawberry.ID
    title: str
    description: str
    target: str
    progress: int
    status: str
    due_date: Optional[date]
    user_id: strawberry.ID
    user_name: str
    department: Optional[str]
    cycle_id: Optional[strawberry.ID]
    cycle_name: Optional[str]


@strawberry.type
class PerformanceReviewType:
    id: strawberry.ID
    cycle_id: strawberry.ID
    cycle_name: str
    employee_id: strawberry.ID
    employee_name: str
    reviewer_id: Optional[strawberry.ID]
    reviewer_name: Optional[str]
    self_score: Optional[float]
    manager_score: Optional[float]
    self_comments: str
    manager_comments: str
    status: str
    department: Optional[str]


@strawberry.type
class PerformanceOverviewType:
    active_cycles: int
    pending_reviews: int
    completed_reviews: int
    completion_rate: float
    goals_total: int
    goals_on_track: int
    goals_at_risk: int
    goals_completed: int
    rating_distribution: List["NamedCountType"]
    goal_by_department: List["NamedCountType"]


@strawberry.type
class NamedCountType:
    name: str
    value: float


@strawberry.input
class CycleInput:
    name: str
    description: Optional[str] = ""
    start_date: date
    end_date: date
    status: Optional[str] = "draft"
    organization_id: Optional[strawberry.ID] = None


@strawberry.input
class UpdateCycleInput:
    id: strawberry.ID
    name: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None


@strawberry.input
class GoalInput:
    title: str
    description: Optional[str] = ""
    target: Optional[str] = ""
    progress: Optional[int] = 0
    status: Optional[str] = "not_started"
    due_date: Optional[date] = None
    user_id: Optional[strawberry.ID] = None
    cycle_id: Optional[strawberry.ID] = None
    organization_id: Optional[strawberry.ID] = None


@strawberry.input
class UpdateGoalInput:
    id: strawberry.ID
    title: Optional[str] = None
    description: Optional[str] = None
    target: Optional[str] = None
    progress: Optional[int] = None
    status: Optional[str] = None
    due_date: Optional[date] = None


@strawberry.input
class ReviewInput:
    cycle_id: strawberry.ID
    employee_id: strawberry.ID
    reviewer_id: Optional[strawberry.ID] = None
    organization_id: Optional[strawberry.ID] = None


@strawberry.input
class UpdateReviewInput:
    id: strawberry.ID
    self_score: Optional[float] = None
    manager_score: Optional[float] = None
    self_comments: Optional[str] = None
    manager_comments: Optional[str] = None
    status: Optional[str] = None
    reviewer_id: Optional[strawberry.ID] = None
