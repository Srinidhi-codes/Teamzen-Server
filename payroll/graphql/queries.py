import strawberry
from typing import List, Optional
from strawberry.types import Info
from .types import (
    SalaryComponentType, SalaryStructureType, EmployeeSalaryStructureType,
    PayrollRunType, PayslipType
)
from ..models import (
    SalaryComponent, SalaryStructure, EmployeeSalaryStructure,
    PayrollRun, Payslip
)

@strawberry.type
class PayrollQuery:
    @strawberry.field
    def payroll_run(self, info: Info, id: strawberry.ID) -> Optional[PayrollRunType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
        
        try:
            # Try numeric first, then fallback to string
            pk = int(str(id))
        except (ValueError, TypeError):
            pk = id

        return PayrollRun.objects.filter(id=pk, organization=user.organization).first()

    @strawberry.field
    def payroll_runs(self, info: Info) -> List[PayrollRunType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
        return PayrollRun.objects.filter(organization=user.organization).order_by('-year', '-month')

    @strawberry.field
    def salary_components(self, info: Info) -> List[SalaryComponentType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
        return SalaryComponent.objects.filter(organization=user.organization)

    @strawberry.field
    def salary_structures(self, info: Info) -> List[SalaryStructureType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
        return SalaryStructure.objects.filter(organization=user.organization)

    @strawberry.field
    def my_payslips(self, info: Info) -> List[PayslipType]:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Unauthorized")
        return Payslip.objects.filter(user=user, status__in=['published', 'paid']).order_by('-payroll_run__year', '-payroll_run__month')

    @strawberry.field
    def employee_payslips(self, info: Info, user_id: strawberry.ID) -> List[PayslipType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'hr', 'superadmin', 'manager']:
            raise Exception("Unauthorized")
        
        return Payslip.objects.filter(user_id=user_id, payroll_run__organization=user.organization).order_by('-payroll_run__year', '-payroll_run__month')
