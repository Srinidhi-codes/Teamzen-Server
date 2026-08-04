from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

import strawberry


@strawberry.type
class OnboardingPayload:
    success: bool = False
    error: Optional[str] = None
    invite_token: Optional[str] = None
    invite_url: Optional[str] = None


@strawberry.type
class OnboardingTaskDefinitionType:
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
class OnboardingTemplateType:
    id: strawberry.ID
    name: str
    description: str
    organization_id: strawberry.ID
    department_id: Optional[strawberry.ID]
    designation_id: Optional[strawberry.ID]
    employment_type: str
    is_default: bool
    it_contact_id: Optional[strawberry.ID]
    task_definitions: List[OnboardingTaskDefinitionType]


@strawberry.type
class OnboardingTaskInstanceType:
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
    completed_by_id: Optional[strawberry.ID]


@strawberry.type
class EmployeeDocumentType:
    id: strawberry.ID
    category: str
    title: str
    file_name: str
    file_url: Optional[str]
    verification_status: str
    rejection_reason: str
    expiry_date: Optional[date]
    ai_suggested_category: str
    ai_confidence: Optional[float]
    created_at: datetime
    verified_at: Optional[datetime]


@strawberry.type
class OfferLetterType:
    id: strawberry.ID
    subject: str
    body_html: str
    pdf_url: str
    status: str
    accepted_name: str
    accepted_at: Optional[datetime]


@strawberry.type
class LetterTemplateType:
    id: strawberry.ID
    name: str
    letter_type: str
    subject: str
    body_html: str
    is_default: bool
    organization_id: strawberry.ID


@strawberry.type
class EmployeeOnboardingType:
    id: strawberry.ID
    status: str
    progress_pct: int
    join_date: Optional[date]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    activated_at: Optional[datetime]
    notes: str
    organization_id: strawberry.ID
    user_id: strawberry.ID
    user_email: str
    user_name: str
    department_name: Optional[str]
    designation_name: Optional[str]
    template_id: Optional[strawberry.ID]
    template_name: Optional[str]
    tasks: List[OnboardingTaskInstanceType]
    documents: List[EmployeeDocumentType]
    offer_letter: Optional[OfferLetterType]


@strawberry.type
class OnboardingOverviewType:
    total: int
    invited: int
    preboarding: int
    in_progress: int
    completed: int
    cancelled: int
    pending_verifications: int
    overdue_tasks: int


@strawberry.input
class StartPreboardingInput:
    email: str
    first_name: str
    last_name: str
    password: str
    organization_id: Optional[strawberry.ID] = None
    department_id: Optional[strawberry.ID] = None
    designation_id: Optional[strawberry.ID] = None
    office_location_id: Optional[strawberry.ID] = None
    manager_id: Optional[strawberry.ID] = None
    employment_type: str = "full_time"
    date_of_joining: Optional[date] = None
    phone_number: Optional[str] = None
    template_id: Optional[strawberry.ID] = None
    letter_template_id: Optional[strawberry.ID] = None
    generate_offer: bool = True
    send_invite: bool = True


@strawberry.input
class TaskDefinitionInput:
    title: str
    description: str = ""
    assignee_role: str = "hire"
    phase: str = "preboarding"
    due_offset_days: int = 0
    requires_document_category: str = ""
    is_required: bool = True
    sort_order: int = 0


@strawberry.input
class CreateOnboardingTemplateInput:
    name: str
    description: str = ""
    organization_id: Optional[strawberry.ID] = None
    department_id: Optional[strawberry.ID] = None
    designation_id: Optional[strawberry.ID] = None
    employment_type: str = ""
    is_default: bool = False
    it_contact_id: Optional[strawberry.ID] = None
    tasks: Optional[List[TaskDefinitionInput]] = None


@strawberry.input
class UpdateOnboardingTemplateInput:
    id: strawberry.ID
    name: Optional[str] = None
    description: Optional[str] = None
    department_id: Optional[strawberry.ID] = None
    designation_id: Optional[strawberry.ID] = None
    employment_type: Optional[str] = None
    is_default: Optional[bool] = None
    it_contact_id: Optional[strawberry.ID] = None


@strawberry.input
class UpsertTaskDefinitionInput:
    template_id: strawberry.ID
    id: Optional[strawberry.ID] = None
    title: str
    description: str = ""
    assignee_role: str = "hire"
    phase: str = "preboarding"
    due_offset_days: int = 0
    requires_document_category: str = ""
    is_required: bool = True
    sort_order: int = 0


@strawberry.input
class LetterTemplateInput:
    name: str
    letter_type: str = "offer"
    subject: str = ""
    body_html: str
    is_default: bool = False
    organization_id: Optional[strawberry.ID] = None


@strawberry.input
class UpdateLetterTemplateInput:
    id: strawberry.ID
    name: Optional[str] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    is_default: Optional[bool] = None


@strawberry.input
class UpdatePreboardingProfileInput:
    invite_token: str
    phone_number: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc_code: Optional[str] = None
    pan_number: Optional[str] = None
    aadhar_number: Optional[str] = None
    uan_number: Optional[str] = None


@strawberry.input
class AcceptOfferInput:
    invite_token: Optional[str] = None
    onboarding_id: Optional[strawberry.ID] = None
    accepted_name: str


@strawberry.input
class SuggestOnboardingTasksInput:
    prompt: str
    organization_id: Optional[strawberry.ID] = None
    employment_type: str = ""
    department: str = ""
    apply_to_template_id: Optional[strawberry.ID] = None


@strawberry.type
class SuggestedOnboardingTaskType:
    title: str
    description: str
    assignee_role: str
    phase: str
    due_offset_days: int
    requires_document_category: str
    is_required: bool
    sort_order: int


@strawberry.type
class SuggestOnboardingTasksPayload:
    success: bool = False
    error: Optional[str] = None
    tasks: List[SuggestedOnboardingTaskType] = strawberry.field(default_factory=list)
    applied_count: int = 0


@strawberry.input
class PolishOfferLetterInput:
    body_html: str
    organization_id: Optional[strawberry.ID] = None
    tone: str = "professional"
    letter_template_id: Optional[strawberry.ID] = None
    save: bool = False


@strawberry.type
class PolishOfferLetterPayload:
    success: bool = False
    error: Optional[str] = None
    body_html: str = ""
