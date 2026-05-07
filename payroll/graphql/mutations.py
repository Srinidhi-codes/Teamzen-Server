import strawberry
from typing import Optional, List
from strawberry.types import Info
from decimal import Decimal
from .types import PayrollRunType, SalaryComponentType, SalaryStructureType, PayrollAdjustmentType
from ..models import (
    SalaryComponent, SalaryStructure, SalaryStructureComponent, 
    EmployeeSalaryStructure, PayrollRun, PayrollAdjustment
)
from ..services import PayrollService

@strawberry.input
class SalaryComponentInput:
    name: str
    code: str
    component_type: str
    is_taxable: bool = True
    is_statutory: bool = False
    description: str = ""

@strawberry.input
class SalaryStructureComponentInput:
    component_id: strawberry.ID
    calculation_type: str
    value: Decimal
    base_component_id: Optional[strawberry.ID] = None

@strawberry.type
class PayrollMutation:
    @strawberry.mutation
    def create_salary_component(self, info: Info, data: SalaryComponentInput) -> SalaryComponentType:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
        
        comp = SalaryComponent.objects.create(
            organization=user.organization,
            **data.__dict__
        )
        return comp

    @strawberry.mutation
    def create_salary_structure(self, info: Info, name: str, description: str, components: List[SalaryStructureComponentInput]) -> SalaryStructureType:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
        
        structure = SalaryStructure.objects.create(
            organization=user.organization,
            name=name,
            description=description
        )
        
        for comp_data in components:
            SalaryStructureComponent.objects.create(
                salary_structure=structure,
                component_id=comp_data.component_id,
                calculation_type=comp_data.calculation_type,
                value=comp_data.value,
                base_component_id=comp_data.base_component_id
            )
            
        return structure

    @strawberry.mutation
    def assign_salary_to_employee(self, info: Info, user_id: strawberry.ID, structure_id: strawberry.ID, annual_ctc: Decimal, effective_from: str) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
        
        EmployeeSalaryStructure.objects.filter(user_id=user_id, is_active=True).update(is_active=False)
        
        EmployeeSalaryStructure.objects.create(
            user_id=user_id,
            salary_structure_id=structure_id,
            annual_ctc=annual_ctc,
            effective_from=effective_from,
            is_active=True
        )
        return True

    @strawberry.mutation
    def initiate_payroll_run(self, info: Info, month: int, year: int) -> PayrollRunType:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
        
        payroll_run, created = PayrollRun.objects.get_or_create(
            organization=user.organization,
            month=month,
            year=year,
            defaults={'processed_by': user}
        )
        
        if not created and payroll_run.status in ['published', 'paid']:
            raise Exception(f"Cannot recalculate payroll that has already been {payroll_run.status}")
            
        service = PayrollService()
        success = service.process_payroll(payroll_run.id)
        
        if not success:
            raise Exception("Payroll processing failed")
            
        return payroll_run

    @strawberry.mutation
    def publish_payslips(self, info: Info, payroll_run_id: strawberry.ID) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
            
        from ..models import Payslip
        from ..services import PayrollService
        
        payslips = Payslip.objects.filter(payroll_run_id=payroll_run_id)
        for payslip in payslips:
            if not payslip.payslip_pdf:
                PayrollService.generate_payslip_pdf(payslip)
                
        payslips.update(status='published')
        return True

    @strawberry.mutation
    def execute_payroll_payout(self, info: Info, payroll_run_id: strawberry.ID) -> int:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
            
        from ..services import PayrollService
        success_count = PayrollService.process_payouts(payroll_run_id)
        return success_count

    @strawberry.mutation
    def delete_payroll_run(self, info: Info, payroll_run_id: strawberry.ID) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
        
        payroll_run = PayrollRun.objects.get(id=payroll_run_id, organization=user.organization)
        
        # Check if any payslips are published or paid
        from ..models import Payslip
        if Payslip.objects.filter(payroll_run=payroll_run, status__in=['published', 'paid']).exists():
            raise Exception("Cannot delete a payroll run with published or paid payslips.")
            
        payroll_run.delete()
        return True

    @strawberry.mutation(name="createPayrollAdjustment")
    def create_payroll_adjustment(
        self, 
        info: Info, 
        user_id: strawberry.ID, 
        month: int, 
        year: int, 
        amount: Decimal, 
        reason: str, 
        adjustment_type: str
    ) -> PayrollAdjustmentType:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
            
        adjustment = PayrollAdjustment.objects.create(
            organization=user.organization,
            user_id=user_id,
            month=month,
            year=year,
            amount=amount,
            reason=reason,
            adjustment_type=adjustment_type
        )
        return adjustment
