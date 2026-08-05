from typing import Optional, List
from decimal import Decimal
import strawberry
from strawberry import auto
from strawberry.scalars import JSON
import strawberry.django
from ..models import (
    EmployeeComponentOverride,
    SalaryComponent,
    SalaryStructure,
    SalaryStructureComponent,
    EmployeeSalaryStructure,
    PayrollRun,
    Payslip,
    PayslipComponent,
    PayrollAdjustment,
    SalaryAdvance,
)
from organizations.graphql.types import OrganizationType
from users.graphql.types import UserType


@strawberry.django.type(PayrollAdjustment)
class PayrollAdjustmentType:
    id: strawberry.ID
    organization: OrganizationType
    user: UserType
    month: auto
    year: auto
    amount: auto
    reason: auto
    adjustment_type: auto
    is_processed: auto
    created_at: auto


@strawberry.django.type(SalaryAdvance)
class SalaryAdvanceType:
    id: strawberry.ID
    organization: OrganizationType
    user: UserType
    amount: auto
    reason: auto
    granted_on: auto
    installments_total: auto
    installment_amount: auto
    remaining_balance: auto
    recovered_so_far: auto
    status: auto
    created_at: auto


@strawberry.type
class AdvanceRecoveryPreviewType:
    advance_id: strawberry.ID
    user_id: strawberry.ID
    user_name: str
    deduct: Decimal
    remaining_after: Decimal


@strawberry.type
class PayrollSettingsType:
    plan: str
    payroll_cycle_day: int
    payroll_auto_enabled: bool
    can_enable_payroll_auto: bool


@strawberry.type
class PayrollSetupChecklistType:
    components: int
    structures: int
    employees_with_ctc: int
    active_advances: int
    ready: bool
    active_employees: int = 0
    employees_missing_ctc: int = 0
    employees_missing_bank: int = 0


@strawberry.type
class FounderPayrollSetupType:
    checklist: PayrollSetupChecklistType
    default_structure_id: Optional[strawberry.ID]
    default_structure_name: str


@strawberry.django.type(SalaryComponent)
class SalaryComponentType:
    id: strawberry.ID
    organization: OrganizationType
    name: auto
    code: auto
    component_type: auto
    is_taxable: auto
    is_statutory: auto
    description: auto


@strawberry.django.type(SalaryStructure)
class SalaryStructureType:
    id: strawberry.ID
    organization: OrganizationType
    name: auto
    description: auto
    is_active: auto

    @strawberry.field
    def components(self) -> List["SalaryStructureComponentType"]:
        return self.components.all()


@strawberry.django.type(SalaryStructureComponent)
class SalaryStructureComponentType:
    id: strawberry.ID
    salary_structure: SalaryStructureType
    component: SalaryComponentType
    calculation_type: auto
    value: auto
    base_component: Optional[SalaryComponentType]


@strawberry.django.type(EmployeeComponentOverride)
class EmployeeComponentOverrideType:
    id: strawberry.ID
    component: SalaryComponentType
    is_excluded: auto
    override_value: Optional[Decimal]


@strawberry.django.type(EmployeeSalaryStructure)
class EmployeeSalaryStructureType:
    id: strawberry.ID
    user: UserType
    salary_structure: SalaryStructureType
    annual_ctc: auto
    effective_from: auto
    is_active: auto

    @strawberry.field
    def component_overrides(self) -> List[EmployeeComponentOverrideType]:
        return self.component_overrides.select_related("component").all()


@strawberry.django.type(PayrollRun)
class PayrollRunType:
    id: strawberry.ID
    organization: OrganizationType
    month: auto
    year: auto
    status: auto
    total_gross: auto
    total_deduction: auto
    total_net_pay: auto
    processed_by: Optional[UserType]
    created_at: auto

    @strawberry.field
    def payslips(self) -> List["PayslipType"]:
        return self.payslips.all()

    @strawberry.field
    def has_locked_payslips(self) -> bool:
        return self.payslips.filter(status__in=["published", "paid"]).exists()

    @strawberry.field
    def published_count(self) -> int:
        return self.payslips.filter(status="published").count()

    @strawberry.field
    def paid_count(self) -> int:
        return self.payslips.filter(status="paid").count()

    @strawberry.field
    def draft_count(self) -> int:
        return self.payslips.filter(status="draft").count()


@strawberry.type
class PayslipPdfType:
    url: str
    name: str


@strawberry.django.type(Payslip)
class PayslipType:
    id: strawberry.ID
    payroll_run: PayrollRunType
    user: UserType
    designation: auto
    department: auto
    worked_days: auto
    lop_days: auto
    gross_earnings: auto
    total_deductions: auto
    net_pay: auto
    status: auto

    @strawberry.field
    def payslip_pdf(self) -> Optional[PayslipPdfType]:
        if not self.payslip_pdf:
            return None
        return PayslipPdfType(url=self.payslip_pdf.url, name=self.payslip_pdf.name)

    @strawberry.field
    def components(self) -> List["PayslipComponentType"]:
        return self.components.all()


@strawberry.django.type(PayslipComponent)
class PayslipComponentType:
    id: strawberry.ID
    payslip: PayslipType
    component_name: auto
    component_code: auto
    component_type: auto
    amount: auto


@strawberry.type
class ImportTargetFieldType:
    key: str
    label: str
    required: bool


@strawberry.type
class DataImportJobType:
    id: strawberry.ID
    status: str
    source_type: str
    file_name: str
    headers: List[str]
    sample_rows: JSON
    column_mapping: JSON
    mapping_confidence: JSON
    preview_result: JSON
    commit_result: JSON
    error_message: str
    row_count: int
    created_at: str

    @classmethod
    def from_model(cls, job) -> "DataImportJobType":
        return cls(
            id=strawberry.ID(str(job.id)),
            status=job.status,
            source_type=job.source_type,
            file_name=job.file_name or "",
            headers=job.headers or [],
            sample_rows=job.sample_rows or [],
            column_mapping=job.column_mapping or {},
            mapping_confidence=job.mapping_confidence or {},
            preview_result=job.preview_result or {},
            commit_result=job.commit_result or {},
            error_message=job.error_message or "",
            row_count=len(job.all_rows or []),
            created_at=job.created_at.isoformat() if job.created_at else "",
        )


@strawberry.type
class PayslipTemplateType:
    id: strawberry.ID
    name: str
    slug: str
    description: str
    layout_key: str
    theme: JSON
    source: str
    preview_notes: str
    is_default: bool
    is_active: bool
    is_system: bool
    organization_id: Optional[strawberry.ID]
    source_file_url: Optional[str] = None

    @classmethod
    def from_model(cls, tpl) -> "PayslipTemplateType":
        source_url = None
        try:
            if tpl.source_file:
                source_url = tpl.source_file.url
        except Exception:
            source_url = None
        return cls(
            id=strawberry.ID(str(tpl.id)),
            name=tpl.name,
            slug=tpl.slug or "",
            description=tpl.description or "",
            layout_key=tpl.layout_key,
            theme=tpl.theme or {},
            source=tpl.source,
            preview_notes=tpl.preview_notes or "",
            is_default=bool(tpl.is_default),
            is_active=bool(tpl.is_active),
            is_system=tpl.organization_id is None,
            organization_id=strawberry.ID(str(tpl.organization_id))
            if tpl.organization_id
            else None,
            source_file_url=source_url,
        )


@strawberry.type
class DataImportCommitResultType:
    created: int
    updated: int
    ctc_assigned: int
    failed_count: int
    failed: JSON
    preview_summary: JSON