import strawberry
from typing import List, Optional
from decimal import Decimal
from strawberry.types import Info
from .types import (
    SalaryComponentType,
    SalaryStructureType,
    PayrollRunType,
    PayslipType,
    PayrollAdjustmentType,
    SalaryAdvanceType,
    PayrollSettingsType,
    AdvanceRecoveryPreviewType,
    PayrollSetupChecklistType,
)
from ..models import (
    SalaryComponent,
    SalaryStructure,
    PayrollRun,
    Payslip,
    PayrollAdjustment,
    SalaryAdvance,
    EmployeeSalaryStructure,
)
from ..services import PayrollService


@strawberry.type
class PayrollQuery:
    @strawberry.field
    def payroll_run(self, info: Info, id: strawberry.ID) -> Optional[PayrollRunType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        try:
            pk = int(str(id))
        except (ValueError, TypeError):
            pk = id
        return PayrollRun.objects.filter(id=pk, organization=user.organization).first()

    @strawberry.field
    def payroll_runs(self, info: Info) -> List[PayrollRunType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        return PayrollRun.objects.filter(organization=user.organization).order_by(
            "-year", "-month"
        )

    @strawberry.field
    def salary_components(self, info: Info) -> List[SalaryComponentType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        return SalaryComponent.objects.filter(organization=user.organization)

    @strawberry.field
    def salary_structures(self, info: Info) -> List[SalaryStructureType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        return SalaryStructure.objects.filter(organization=user.organization)

    @strawberry.field
    def my_payslips(self, info: Info) -> List[PayslipType]:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Unauthorized")
        return Payslip.objects.filter(
            user=user, status__in=["published", "paid"]
        ).order_by("-payroll_run__year", "-payroll_run__month")

    @strawberry.field
    def employee_payslips(self, info: Info, user_id: strawberry.ID) -> List[PayslipType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in [
            "admin",
            "hr",
            "superadmin",
            "manager",
        ]:
            raise Exception("Unauthorized")
        return Payslip.objects.filter(
            user_id=user_id, payroll_run__organization=user.organization
        ).order_by("-payroll_run__year", "-payroll_run__month")

    @strawberry.field
    def salary_advances(
        self, info: Info, status: Optional[str] = None
    ) -> List[SalaryAdvanceType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        qs = SalaryAdvance.objects.filter(
            organization=user.organization
        ).select_related("user")
        if status:
            qs = qs.filter(status=status)
        return qs.order_by("-granted_on", "-id")

    @strawberry.field
    def payroll_adjustments(
        self, info: Info, month: int, year: int
    ) -> List[PayrollAdjustmentType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        return PayrollAdjustment.objects.filter(
            organization=user.organization, month=month, year=year
        ).select_related("user")

    @strawberry.field
    def payroll_settings(self, info: Info) -> PayrollSettingsType:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        org = user.organization
        if not org:
            raise Exception("No organization")
        return PayrollSettingsType(
            plan=org.plan,
            payroll_cycle_day=org.payroll_cycle_day,
            payroll_auto_enabled=org.payroll_auto_enabled,
            can_enable_payroll_auto=org.plan in ("pro", "elite"),
        )

    @strawberry.field
    def payroll_setup_checklist(self, info: Info) -> PayrollSetupChecklistType:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        org = user.organization
        components = SalaryComponent.objects.filter(organization=org).count()
        structures = SalaryStructure.objects.filter(organization=org).count()
        assigned = (
            EmployeeSalaryStructure.objects.filter(
                user__organization=org, is_active=True
            )
            .values("user_id")
            .distinct()
            .count()
        )
        advances = SalaryAdvance.objects.filter(
            organization=org, status="active"
        ).count()
        return PayrollSetupChecklistType(
            components=components,
            structures=structures,
            employees_with_ctc=assigned,
            active_advances=advances,
            ready=components > 0 and structures > 0 and assigned > 0,
        )

    @strawberry.field
    def advance_recovery_preview(
        self, info: Info
    ) -> List[AdvanceRecoveryPreviewType]:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ["admin", "superadmin"]:
            raise Exception("Unauthorized")
        rows = PayrollService.preview_advance_recoveries(user.organization)
        return [
            AdvanceRecoveryPreviewType(
                advance_id=r["advance_id"],
                user_id=r["user_id"],
                user_name=r["user_name"],
                deduct=r["deduct"],
                remaining_after=r["remaining_after"],
            )
            for r in rows
        ]
