import strawberry
from typing import Optional, List
from strawberry.types import Info
from decimal import Decimal
from datetime import date
from .types import (
    PayrollRunType,
    SalaryComponentType,
    SalaryStructureType,
    PayrollAdjustmentType,
    SalaryAdvanceType,
    PayrollSettingsType,
)
from ..models import (
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
    def create_salary_component(
        self, info: Info, data: SalaryComponentInput
    ) -> SalaryComponentType:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        return SalaryComponent.objects.create(
            organization=user.organization, **data.__dict__
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
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        structure = SalaryStructure.objects.create(
            organization=user.organization, name=name, description=description
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
    def assign_salary_to_employee(
        self,
        info: Info,
        user_id: strawberry.ID,
        structure_id: strawberry.ID,
        annual_ctc: Decimal,
        effective_from: str,
    ) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        EmployeeSalaryStructure.objects.filter(
            user_id=user_id, is_active=True
        ).update(is_active=False)
        EmployeeSalaryStructure.objects.create(
            user_id=user_id,
            salary_structure_id=structure_id,
            annual_ctc=annual_ctc,
            effective_from=effective_from,
            is_active=True,
        )
        return True

    @strawberry.mutation
    def create_payroll_run(self, info: Info, month: int, year: int) -> PayrollRunType:
        """Create a draft monthly run without calculating payslips."""
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        existing = PayrollRun.objects.filter(
            organization=user.organization, month=month, year=year
        ).first()
        if existing and existing.status not in ("draft", "failed"):
            raise Exception(
                f"Payroll for {month}/{year} already exists with status {existing.status}."
            )
        return PayrollService.create_draft_run(
            user.organization, month, year, processed_by=user
        )

    @strawberry.mutation
    def process_payroll_run(
        self, info: Info, payroll_run_id: strawberry.ID
    ) -> PayrollRunType:
        """Calculate / recalculate payslips for a draft or completed (unlocked) run."""
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        run = PayrollRun.objects.get(
            id=payroll_run_id, organization=user.organization
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
    def initiate_payroll_run(self, info: Info, month: int, year: int) -> PayrollRunType:
        """Backward-compatible: create draft (if needed) then process immediately."""
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        run = PayrollService.create_draft_run(
            user.organization, month, year, processed_by=user
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
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        run = PayrollRun.objects.get(
            id=payroll_run_id, organization=user.organization
        )
        if run.status != "completed":
            raise Exception("Process payroll before publishing payslips.")
        payslips = Payslip.objects.filter(payroll_run=run)
        if not payslips.exists():
            raise Exception("No payslips to publish. Process the run first.")
        for payslip in payslips:
            if not payslip.payslip_pdf:
                PayrollService.generate_payslip_pdf(payslip)
        payslips.update(status="published")
        return True

    @strawberry.mutation
    def execute_payroll_payout(self, info: Info, payroll_run_id: strawberry.ID) -> int:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        run = PayrollRun.objects.get(
            id=payroll_run_id, organization=user.organization
        )
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
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        payroll_run = PayrollRun.objects.get(
            id=payroll_run_id, organization=user.organization
        )
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
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        return PayrollAdjustment.objects.create(
            organization=user.organization,
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
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        if amount <= 0:
            raise Exception("Advance amount must be positive")
        installments = max(1, int(installments))
        installment_amount = (Decimal(amount) / Decimal(installments)).quantize(
            Decimal("0.01")
        )
        granted = date.fromisoformat(granted_on) if granted_on else date.today()
        return SalaryAdvance.objects.create(
            organization=user.organization,
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
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        adv = SalaryAdvance.objects.get(
            id=advance_id, organization=user.organization
        )
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
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        org = user.organization
        if not org:
            raise Exception("No organization")
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
