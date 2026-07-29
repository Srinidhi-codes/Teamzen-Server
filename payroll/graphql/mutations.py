import strawberry
from typing import Optional, List
from strawberry.types import Info
from decimal import Decimal
from datetime import date
from .types import (
    EmployeeSalaryStructureType,
    EmployeeComponentOverrideType,
    PayrollRunType,
    SalaryComponentType,
    SalaryStructureType,
    PayrollAdjustmentType,
    SalaryAdvanceType,
    PayrollSettingsType,
)
from ..models import (
    EmployeeComponentOverride,
    SalaryComponent,
    SalaryStructure,
    SalaryStructureComponent,
    EmployeeSalaryStructure,
    PayrollRun,
    PayrollAdjustment,
    SalaryAdvance,
    Payslip,
)
from ..services import PayrollService
from .auth import require_payroll_admin, require_org


def _get_run_for_user(user, payroll_run_id):
    qs = PayrollRun.objects.filter(id=payroll_run_id)
    if user.role == "superadmin" and not user.organization_id:
        return qs.get()
    return qs.get(organization=user.organization)


@strawberry.input
class SalaryComponentInput:
    name: str
    code: str
    component_type: str
    is_taxable: bool = True
    is_statutory: bool = False
    description: str = ""


@strawberry.input
class ComponentOverrideInput:
    component_id: strawberry.ID
    is_excluded: bool = False
    override_value: Optional[Decimal] = None


@strawberry.input
class SalaryStructureComponentInput:
    component_id: strawberry.ID
    calculation_type: str
    value: Decimal
    base_component_id: Optional[strawberry.ID] = None


@strawberry.type
class PayrollMutation:
    @strawberry.mutation
    def create_salary_component(
        self, info: Info, data: SalaryComponentInput
    ) -> SalaryComponentType:
        user = info.context.request.user
        require_payroll_admin(user)
        return SalaryComponent.objects.create(
            organization=require_org(user), **data.__dict__
        )

    @strawberry.mutation
    def create_salary_structure(
        self,
        info: Info,
        name: str,
        description: str,
        components: List[SalaryStructureComponentInput],
    ) -> SalaryStructureType:
        user = info.context.request.user
        require_payroll_admin(user)
        structure = SalaryStructure.objects.create(
            organization=require_org(user), name=name, description=description
        )
        for comp_data in components:
            SalaryStructureComponent.objects.create(
                salary_structure=structure,
                component_id=comp_data.component_id,
                calculation_type=comp_data.calculation_type,
                value=comp_data.value,
                base_component_id=comp_data.base_component_id,
            )
        return structure

    @strawberry.mutation
    def update_salary_structure(
        self,
        info: Info,
        structure_id: strawberry.ID,
        name: str,
        description: str,
        components: List[SalaryStructureComponentInput],
    ) -> SalaryStructureType:
        user = info.context.request.user
        require_payroll_admin(user)
        structure = SalaryStructure.objects.get(id=structure_id)
        if user.role != "superadmin" or user.organization_id:
            if structure.organization_id != require_org(user).id:
                raise Exception("Unauthorized")
        structure.name = name
        structure.description = description
        structure.save(update_fields=["name", "description"])
        structure.components.all().delete()
        for comp_data in components:
            SalaryStructureComponent.objects.create(
                salary_structure=structure,
                component_id=comp_data.component_id,
                calculation_type=comp_data.calculation_type,
                value=comp_data.value,
                base_component_id=comp_data.base_component_id,
            )
        return structure

    @strawberry.mutation
    def delete_salary_structure(
        self,
        info: Info,
        structure_id: strawberry.ID,
    ) -> bool:
        user = info.context.request.user
        require_payroll_admin(user)
        structure = SalaryStructure.objects.get(id=structure_id)
        if user.role != "superadmin" or user.organization_id:
            if structure.organization_id != require_org(user).id:
                raise Exception("Unauthorized")
        if EmployeeSalaryStructure.objects.filter(salary_structure=structure, is_active=True).exists():
            raise Exception("Cannot delete: this structure is assigned to active employees. Reassign them first.")
        structure.delete()
        return True

    @strawberry.mutation
    def assign_salary_to_employee(
        self,
        info: Info,
        user_id: strawberry.ID,
        structure_id: strawberry.ID,
        annual_ctc: Decimal,
        effective_from: str,
    ) -> EmployeeSalaryStructureType:
        user = info.context.request.user
        require_payroll_admin(user)
        try:
            effective_from_date = date.fromisoformat(effective_from)
        except ValueError:
            raise Exception("Invalid effective_from date. Use YYYY-MM-DD.")
        EmployeeSalaryStructure.objects.filter(
            user_id=user_id, is_active=True
        ).update(is_active=False)
        salary = EmployeeSalaryStructure.objects.create(
            user_id=user_id,
            salary_structure_id=structure_id,
            annual_ctc=annual_ctc,
            effective_from=effective_from_date,
            is_active=True,
        )
        return salary

    @strawberry.mutation
    def create_payroll_run(self, info: Info, month: int, year: int) -> PayrollRunType:
        """Create a draft monthly run without calculating payslips."""
        user = info.context.request.user
        require_payroll_admin(user)
        org = require_org(user)
        existing = PayrollRun.objects.filter(
            organization=org, month=month, year=year
        ).first()
        if existing and existing.status not in ("draft", "failed"):
            raise Exception(
                f"Payroll for {month}/{year} already exists with status {existing.status}."
            )
        return PayrollService.create_draft_run(
            org, month, year, processed_by=user
        )

    @strawberry.mutation
    def process_payroll_run(
        self, info: Info, payroll_run_id: strawberry.ID
    ) -> PayrollRunType:
        """Calculate / recalculate payslips for a draft or completed (unlocked) run."""
        user = info.context.request.user
        require_payroll_admin(user)
        run = _get_run_for_user(user, payroll_run_id)
        if PayrollService.run_has_locked_payslips(run):
            raise Exception(
                "Cannot recalculate: one or more payslips are already published or paid."
            )
        service = PayrollService()
        try:
            success = service.process_payroll(run.id)
        except Exception as e:
            raise Exception(str(e))
        if not success:
            raise Exception("Payroll processing failed")
        run.refresh_from_db()
        return run

    @strawberry.mutation
    def initiate_payroll_run(self, info: Info, month: int, year: int) -> PayrollRunType:
        """Backward-compatible: create draft (if needed) then process immediately."""
        user = info.context.request.user
        require_payroll_admin(user)
        run = PayrollService.create_draft_run(
            require_org(user), month, year, processed_by=user
        )
        if PayrollService.run_has_locked_payslips(run):
            raise Exception(
                "Cannot recalculate: one or more payslips are already published or paid."
            )
        service = PayrollService()
        try:
            success = service.process_payroll(run.id)
        except Exception as e:
            raise Exception(str(e))
        if not success:
            raise Exception("Payroll processing failed")
        run.refresh_from_db()
        return run

    @strawberry.mutation
    def publish_payslips(self, info: Info, payroll_run_id: strawberry.ID) -> bool:
        user = info.context.request.user
        require_payroll_admin(user)
        run = _get_run_for_user(user, payroll_run_id)
        if run.status != "completed":
            raise Exception("Process payroll before publishing payslips.")
        payslips = Payslip.objects.filter(payroll_run=run)
        if not payslips.exists():
            raise Exception("No payslips to publish. Process the run first.")
        for payslip in payslips:
            # Always regenerate so structure/adjustments/LOP changes are reflected
            PayrollService.generate_payslip_pdf(payslip)
        payslips.update(status="published")
        return True

    @strawberry.mutation
    def execute_payroll_payout(self, info: Info, payroll_run_id: strawberry.ID) -> int:
        user = info.context.request.user
        require_payroll_admin(user)
        run = _get_run_for_user(user, payroll_run_id)
        published = Payslip.objects.filter(
            payroll_run=run, status="published"
        ).count()
        if published == 0:
            raise Exception(
                "No published payslips to pay. Publish payslips before payout."
            )
        return PayrollService.process_payouts(payroll_run_id)

    @strawberry.mutation
    def delete_payroll_run(self, info: Info, payroll_run_id: strawberry.ID) -> bool:
        user = info.context.request.user
        require_payroll_admin(user)
        payroll_run = _get_run_for_user(user, payroll_run_id)
        if Payslip.objects.filter(
            payroll_run=payroll_run, status__in=["published", "paid"]
        ).exists():
            raise Exception(
                "Cannot delete a payroll run with published or paid payslips."
            )
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
        adjustment_type: str,
    ) -> PayrollAdjustmentType:
        user = info.context.request.user
        require_payroll_admin(user)
        return PayrollAdjustment.objects.create(
            organization=require_org(user),
            user_id=user_id,
            month=month,
            year=year,
            amount=amount,
            reason=reason,
            adjustment_type=adjustment_type,
        )

    @strawberry.mutation
    def create_salary_advance(
        self,
        info: Info,
        user_id: strawberry.ID,
        amount: Decimal,
        installments: int,
        reason: str = "",
        granted_on: Optional[str] = None,
    ) -> SalaryAdvanceType:
        user = info.context.request.user
        require_payroll_admin(user)
        if amount <= 0:
            raise Exception("Advance amount must be positive")
        installments = max(1, int(installments))
        installment_amount = (Decimal(amount) / Decimal(installments)).quantize(
            Decimal("0.01")
        )
        granted = date.fromisoformat(granted_on) if granted_on else date.today()
        return SalaryAdvance.objects.create(
            organization=require_org(user),
            user_id=user_id,
            amount=amount,
            reason=reason or "Salary advance",
            granted_on=granted,
            installments_total=installments,
            installment_amount=installment_amount,
            remaining_balance=amount,
            recovered_so_far=Decimal("0.00"),
            status="active",
        )

    @strawberry.mutation
    def cancel_salary_advance(
        self, info: Info, advance_id: strawberry.ID
    ) -> SalaryAdvanceType:
        user = info.context.request.user
        require_payroll_admin(user)
        qs = SalaryAdvance.objects.filter(id=advance_id)
        if user.role != "superadmin" or user.organization_id:
            qs = qs.filter(organization=require_org(user))
        adv = qs.get()
        if adv.status != "active":
            raise Exception(f"Advance is already {adv.status}")
        adv.status = "cancelled"
        adv.save(update_fields=["status", "updated_at"])
        return adv

    @strawberry.mutation
    def update_payroll_settings(
        self,
        info: Info,
        payroll_cycle_day: int,
        payroll_auto_enabled: bool,
    ) -> PayrollSettingsType:
        user = info.context.request.user
        require_payroll_admin(user)
        org = require_org(user)
        day = max(1, min(28, int(payroll_cycle_day)))
        auto = bool(payroll_auto_enabled)
        if auto and org.plan not in ("pro", "elite"):
            raise Exception(
                "Automated payroll requires Pro or Elite plan. Upgrade to enable."
            )
        org.payroll_cycle_day = day
        org.payroll_auto_enabled = auto
        org.save(update_fields=["payroll_cycle_day", "payroll_auto_enabled", "updated_at"])
        return PayrollSettingsType(
            plan=org.plan,
            payroll_cycle_day=org.payroll_cycle_day,
            payroll_auto_enabled=org.payroll_auto_enabled,
            can_enable_payroll_auto=org.plan in ("pro", "elite"),
        )

    @strawberry.mutation
    def save_employee_component_overrides(
        self,
        info: Info,
        employee_salary_id: strawberry.ID,
        overrides: List[ComponentOverrideInput],
    ) -> List[EmployeeComponentOverrideType]:
        user = info.context.request.user
        require_payroll_admin(user, allow_hr=True)
        qs = EmployeeSalaryStructure.objects.filter(id=employee_salary_id)
        if user.role != "superadmin" or user.organization_id:
            qs = qs.filter(user__organization=require_org(user))
        emp_salary = qs.get()
        # Clear existing overrides and recreate
        emp_salary.component_overrides.all().delete()
        created = []
        for ovr in overrides:
            obj = EmployeeComponentOverride.objects.create(
                employee_salary=emp_salary,
                component_id=ovr.component_id,
                is_excluded=ovr.is_excluded,
                override_value=ovr.override_value,
            )
            created.append(obj)
        return created
