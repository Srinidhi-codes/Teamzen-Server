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
    DataImportJobType,
    ImportTargetFieldType,
    PayslipTemplateType,
)
from .auth import require_payroll_admin, require_org, scoped_qs
from ..models import (
    SalaryComponent,
    SalaryStructure,
    PayrollRun,
    Payslip,
    PayrollAdjustment,
    SalaryAdvance,
    EmployeeSalaryStructure,
    DataImportJob,
    PayslipTemplate,
)
from ..services import PayrollService
from ..import_services import IMPORT_TARGET_FIELDS
from ..template_services import ensure_system_templates


@strawberry.type
class PayrollQuery:
    @strawberry.field
    def payroll_run(self, info: Info, id: strawberry.ID) -> Optional[PayrollRunType]:
        user = info.context.request.user
        require_payroll_admin(user)
        try:
            pk = int(str(id))
        except (ValueError, TypeError):
            pk = id
        return scoped_qs(PayrollRun.objects.filter(id=pk), user).first()

    @strawberry.field
    def payroll_runs(
        self,
        info: Info,
        organization_id: Optional[strawberry.ID] = None,
    ) -> List[PayrollRunType]:
        user = info.context.request.user
        require_payroll_admin(user)
        return scoped_qs(
            PayrollRun.objects.select_related("organization").all(),
            user,
            organization_id=organization_id,
        ).order_by("-year", "-month")

    @strawberry.field
    def salary_components(
        self,
        info: Info,
        organization_id: Optional[strawberry.ID] = None,
    ) -> List[SalaryComponentType]:
        user = info.context.request.user
        require_payroll_admin(user)
        return scoped_qs(
            SalaryComponent.objects.select_related("organization").all(),
            user,
            organization_id=organization_id,
        )

    @strawberry.field
    def salary_structures(
        self,
        info: Info,
        organization_id: Optional[strawberry.ID] = None,
    ) -> List[SalaryStructureType]:
        user = info.context.request.user
        require_payroll_admin(user)
        return scoped_qs(
            SalaryStructure.objects.select_related("organization").all(),
            user,
            organization_id=organization_id,
        )

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
        qs = Payslip.objects.filter(user_id=user_id)
        return scoped_qs(qs, user, field="payroll_run__organization").order_by(
            "-payroll_run__year", "-payroll_run__month"
        )

    @strawberry.field
    def salary_advances(
        self,
        info: Info,
        status: Optional[str] = None,
        organization_id: Optional[strawberry.ID] = None,
    ) -> List[SalaryAdvanceType]:
        user = info.context.request.user
        require_payroll_admin(user)
        qs = scoped_qs(
            SalaryAdvance.objects.all(),
            user,
            organization_id=organization_id,
        ).select_related("user", "organization")
        if status:
            qs = qs.filter(status=status)
        return qs.order_by("-granted_on", "-id")

    @strawberry.field
    def payroll_adjustments(
        self, info: Info, month: int, year: int
    ) -> List[PayrollAdjustmentType]:
        user = info.context.request.user
        require_payroll_admin(user)
        return (
            scoped_qs(PayrollAdjustment.objects.filter(month=month, year=year), user)
            .select_related("user")
        )

    @strawberry.field
    def payroll_settings(
        self,
        info: Info,
        organization_id: Optional[strawberry.ID] = None,
    ) -> PayrollSettingsType:
        user = info.context.request.user
        require_payroll_admin(user)
        org = require_org(user, organization_id)
        return PayrollSettingsType(
            plan=org.plan,
            payroll_cycle_day=org.payroll_cycle_day,
            payroll_auto_enabled=org.payroll_auto_enabled,
            can_enable_payroll_auto=org.plan in ("pro", "elite"),
        )

    @strawberry.field
    def payroll_setup_checklist(
        self,
        info: Info,
        organization_id: Optional[strawberry.ID] = None,
    ) -> PayrollSetupChecklistType:
        user = info.context.request.user
        require_payroll_admin(user)
        org = require_org(user, organization_id)
        from payroll.setup_services import build_payroll_setup_checklist

        data = build_payroll_setup_checklist(org)
        return PayrollSetupChecklistType(**data)

    @strawberry.field
    def advance_recovery_preview(
        self, info: Info
    ) -> List[AdvanceRecoveryPreviewType]:
        user = info.context.request.user
        require_payroll_admin(user)
        rows = PayrollService.preview_advance_recoveries(require_org(user))
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

    @strawberry.field
    def import_target_fields(self, info: Info) -> List[ImportTargetFieldType]:
        user = info.context.request.user
        require_payroll_admin(user, allow_hr=True)
        return [
            ImportTargetFieldType(
                key=f["key"],
                label=f["label"],
                required=f.get("required") == "true",
            )
            for f in IMPORT_TARGET_FIELDS
        ]

    @strawberry.field
    def data_import_job(
        self, info: Info, id: strawberry.ID
    ) -> Optional[DataImportJobType]:
        user = info.context.request.user
        require_payroll_admin(user, allow_hr=True)
        job = scoped_qs(DataImportJob.objects.filter(id=id), user).first()
        return DataImportJobType.from_model(job) if job else None

    @strawberry.field
    def data_import_jobs(
        self,
        info: Info,
        organization_id: Optional[strawberry.ID] = None,
    ) -> List[DataImportJobType]:
        user = info.context.request.user
        require_payroll_admin(user, allow_hr=True)
        qs = scoped_qs(
            DataImportJob.objects.all(),
            user,
            organization_id=organization_id,
        ).order_by("-created_at")[:20]
        return [DataImportJobType.from_model(j) for j in qs]

    @strawberry.field
    def payslip_templates(
        self,
        info: Info,
        organization_id: Optional[strawberry.ID] = None,
    ) -> List[PayslipTemplateType]:
        user = info.context.request.user
        require_payroll_admin(user, allow_hr=True)
        ensure_system_templates()
        org = require_org(user, organization_id)
        system = list(
            PayslipTemplate.objects.filter(organization=None, is_active=True)
        )
        org_tpls = list(
            PayslipTemplate.objects.filter(organization=org, is_active=True)
        )
        return [PayslipTemplateType.from_model(t) for t in system + org_tpls]
