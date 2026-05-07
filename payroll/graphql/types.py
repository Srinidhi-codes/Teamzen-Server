from typing import Optional, List
import strawberry
from strawberry import auto
import strawberry.django
from ..models import (
    SalaryComponent, SalaryStructure, SalaryStructureComponent, 
    EmployeeSalaryStructure, PayrollRun, Payslip, PayslipComponent,
    PayrollAdjustment
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

@strawberry.django.type(EmployeeSalaryStructure)
class EmployeeSalaryStructureType:
    id: strawberry.ID
    user: UserType
    salary_structure: SalaryStructureType
    annual_ctc: auto
    effective_from: auto
    is_active: auto

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
