import strawberry
from typing import List, Optional
from datetime import date


@strawberry.input
class ReportFilterInput:
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    organization_id: Optional[strawberry.ID] = None
    department_id: Optional[strawberry.ID] = None
    office_location_id: Optional[strawberry.ID] = None


@strawberry.type
class ReportKpiType:
    label: str
    value: str
    hint: Optional[str] = None
    trend: Optional[str] = None  # up | down | flat


@strawberry.type
class ReportSeriesPointType:
    label: str
    value: float
    secondary: Optional[float] = None
    tertiary: Optional[float] = None


@strawberry.type
class ReportNamedValueType:
    name: str
    value: float
    color: Optional[str] = None


@strawberry.type
class WorkforceEmployeeRowType:
    id: strawberry.ID
    name: str
    email: str
    department: Optional[str]
    designation: Optional[str]
    employment_type: Optional[str]
    date_of_joining: Optional[str]
    date_of_exit: Optional[str]
    is_active: bool


@strawberry.type
class WorkforceReportType:
    kpis: List[ReportKpiType]
    headcount_series: List[ReportSeriesPointType]
    department_breakdown: List[ReportNamedValueType]
    employment_type_breakdown: List[ReportNamedValueType]
    employees: List[WorkforceEmployeeRowType]
    hires: int
    exits: int
    turnover_rate: float
    active_count: int
    inactive_count: int


@strawberry.type
class AttendanceEmployeeRowType:
    id: strawberry.ID
    name: str
    email: str
    department: Optional[str]
    present_days: int
    late_days: int
    absent_days: int
    leave_days: int
    half_days: int
    attendance_rate: float


@strawberry.type
class AttendanceReportType:
    kpis: List[ReportKpiType]
    daily_series: List[ReportSeriesPointType]
    status_breakdown: List[ReportNamedValueType]
    office_breakdown: List[ReportNamedValueType]
    employees: List[AttendanceEmployeeRowType]


@strawberry.type
class LeaveRequestRowType:
    id: strawberry.ID
    employee: str
    leave_type: str
    from_date: str
    to_date: str
    duration_days: float
    status: str
    department: Optional[str]


@strawberry.type
class LeaveReportType:
    kpis: List[ReportKpiType]
    type_breakdown: List[ReportNamedValueType]
    monthly_flux: List[ReportSeriesPointType]
    utilization: List[ReportNamedValueType]
    requests: List[LeaveRequestRowType]
    upcoming: List[LeaveRequestRowType]


@strawberry.type
class PayrollRunRowType:
    id: strawberry.ID
    month: int
    year: int
    status: str
    total_gross: float
    total_deduction: float
    total_net_pay: float
    label: str


@strawberry.type
class PayrollReportType:
    kpis: List[ReportKpiType]
    monthly_series: List[ReportSeriesPointType]
    department_cost: List[ReportNamedValueType]
    runs: List[PayrollRunRowType]
    advances_outstanding: float
    advances_count: int
