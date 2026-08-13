from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

import strawberry


@strawberry.type
class OffboardingPayload:
    success: bool = False
    error: Optional[str] = None
    invite_token: Optional[str] = None
    invite_url: Optional[str] = None
    offboarding_id: Optional[strawberry.ID] = None


@strawberry.type
class OffboardingTaskDefinitionType:
    id: strawberry.ID
    title: str
    description: str
    assignee_role: str
    phase: str
    due_offset_days: int
    requires_document_category: str
    is_required: bool
    sort_order: int


@strawberry.type
class OffboardingTemplateType:
    id: strawberry.ID
    name: str
    description: str
    organization_id: strawberry.ID
    is_default: bool
    it_contact_id: Optional[strawberry.ID]
    task_definitions: List[OffboardingTaskDefinitionType]


@strawberry.type
class OffboardingTaskInstanceType:
    id: strawberry.ID
    title: str
    description: str
    assignee_role: str
    phase: str
    status: str
    due_at: Optional[date]
    is_required: bool
    requires_document_category: str
    sort_order: int
    notes: str
    assignee_id: Optional[strawberry.ID]
    assignee_name: Optional[str]
    completed_at: Optional[datetime]


@strawberry.type
class FnfSettlementType:
    id: strawberry.ID
    status: str
    pro_rata_salary: float
    leave_encashment: float
    bonus_gratuity: float
    other_additions: float
    recoveries: float
    other_deductions: float
    net_payable: float
    notes: str
    statement_pdf_url: str
    snapshot_json: Optional[str]
    computed_at: Optional[datetime]
    approved_at: Optional[datetime]
    acknowledged_at: Optional[datetime]
    paid_at: Optional[datetime]


@strawberry.type
class ExitLetterType:
    id: strawberry.ID
    letter_type: str
    subject: str
    body_html: str
    pdf_url: str
    status: str
    issued_at: Optional[datetime]
    download_url: Optional[str]


@strawberry.type
class EmployeeOffboardingType:
    id: strawberry.ID
    status: str
    reason: str
    progress_pct: int
    exit_date: Optional[date]
    last_working_day: Optional[date]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    notes: str
    organization_id: strawberry.ID
    user_id: strawberry.ID
    user_email: str
    user_name: str
    template_id: Optional[strawberry.ID]
    template_name: Optional[str]
    tasks: List[OffboardingTaskInstanceType]
    settlement: Optional[FnfSettlementType]
    letters: List[ExitLetterType]


@strawberry.type
class ExitSessionType:
    offboarding: EmployeeOffboardingType
    invite_valid: bool


@strawberry.type
class OffboardingOverviewType:
    total: int
    initiated: int
    in_progress: int
    settlement_pending: int
    letters_pending: int
    completed: int
    cancelled: int
