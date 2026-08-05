import strawberry
from typing import Optional, List
from strawberry.types import Info
from strawberry.scalars import JSON
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
    DataImportJobType,
    PayslipTemplateType,
    FounderPayrollSetupType,
    PayrollSetupChecklistType,
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
    DataImportJob,
    PayslipTemplate,
)
from ..services import PayrollService
from .auth import require_payroll_admin, require_org, scoped_qs


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

    @strawberry.mutation
    def update_import_mapping(
        self,
        info: Info,
        job_id: strawberry.ID,
        column_mapping: JSON,
        use_ai: bool = False,
    ) -> DataImportJobType:
        from ..import_services import (
            TARGET_KEYS,
            ai_refine_column_mapping,
            heuristic_column_mapping,
        )

        user = info.context.request.user
        require_payroll_admin(user, allow_hr=True)
        job = scoped_qs(DataImportJob.objects.filter(id=job_id), user).first()
        if not job:
            raise Exception("Import job not found")

        mapping = dict(column_mapping or {})
        cleaned = {}
        used = set()
        for h in job.headers or []:
            t = str(mapping.get(h, "") or "").strip()
            if t not in TARGET_KEYS:
                t = ""
            if t and t in used:
                t = ""
            if t:
                used.add(t)
            cleaned[h] = t

        confidence = {h: (0.9 if cleaned.get(h) else 0.0) for h in (job.headers or [])}

        if use_ai:
            cleaned, confidence = ai_refine_column_mapping(
                job.organization_id,
                job.headers or [],
                job.sample_rows or [],
                current_mapping=cleaned,
            )
        elif not any(cleaned.values()):
            cleaned, confidence = heuristic_column_mapping(job.headers or [])

        job.column_mapping = cleaned
        job.mapping_confidence = confidence
        job.status = "mapped"
        job.save(
            update_fields=[
                "column_mapping",
                "mapping_confidence",
                "status",
                "updated_at",
            ]
        )
        return DataImportJobType.from_model(job)

    @strawberry.mutation
    def preview_data_import(
        self, info: Info, job_id: strawberry.ID
    ) -> DataImportJobType:
        from ..import_services import build_preview

        user = info.context.request.user
        require_payroll_admin(user, allow_hr=True)
        job = scoped_qs(DataImportJob.objects.filter(id=job_id), user).first()
        if not job:
            raise Exception("Import job not found")
        if not job.column_mapping or "email" not in (job.column_mapping or {}).values():
            raise Exception("Map an email column before previewing.")

        preview = build_preview(
            job.organization, job.all_rows or [], job.column_mapping or {}
        )
        job.preview_result = preview
        job.status = "previewed"
        job.save(update_fields=["preview_result", "status", "updated_at"])
        return DataImportJobType.from_model(job)

    @strawberry.mutation
    def commit_data_import(
        self,
        info: Info,
        job_id: strawberry.ID,
        update_existing: bool = True,
        assign_ctc: bool = True,
        send_welcome: bool = False,
    ) -> DataImportJobType:
        from ..import_services import commit_import

        user = info.context.request.user
        require_payroll_admin(user, allow_hr=True)
        job = scoped_qs(DataImportJob.objects.filter(id=job_id), user).first()
        if not job:
            raise Exception("Import job not found")
        if job.status == "committed":
            raise Exception("This import was already committed.")
        if not job.column_mapping or "email" not in (job.column_mapping or {}).values():
            raise Exception("Map an email column before committing.")

        try:
            result = commit_import(
                job.organization,
                job.all_rows or [],
                job.column_mapping or {},
                update_existing=update_existing,
                assign_ctc=assign_ctc,
                send_welcome=send_welcome,
                actor=user,
            )
            job.commit_result = result
            job.status = "committed"
            job.error_message = ""
            job.save(
                update_fields=[
                    "commit_result",
                    "status",
                    "error_message",
                    "updated_at",
                ]
            )
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.save(update_fields=["status", "error_message", "updated_at"])
            raise
        return DataImportJobType.from_model(job)

    @strawberry.mutation
    def set_default_payslip_template(
        self,
        info: Info,
        template_id: strawberry.ID,
        organization_id: Optional[strawberry.ID] = None,
    ) -> PayslipTemplateType:
        from ..template_services import set_org_default_template

        user = info.context.request.user
        require_payroll_admin(user, allow_hr=True)
        org = require_org(user, organization_id)
        tpl = PayslipTemplate.objects.filter(id=template_id).first()
        if not tpl:
            raise Exception("Template not found")
        if tpl.organization_id and tpl.organization_id != org.id:
            raise Exception("Unauthorized")
        result = set_org_default_template(org, tpl)
        return PayslipTemplateType.from_model(result)

    @strawberry.mutation
    def update_payslip_template(
        self,
        info: Info,
        template_id: strawberry.ID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        layout_key: Optional[str] = None,
        theme: Optional[JSON] = None,
        is_active: Optional[bool] = None,
    ) -> PayslipTemplateType:
        user = info.context.request.user
        require_payroll_admin(user, allow_hr=True)
        tpl = PayslipTemplate.objects.filter(id=template_id).first()
        if not tpl:
            raise Exception("Template not found")
        if tpl.organization_id is None:
            raise Exception("System gallery templates cannot be edited. Set as default to clone.")
        if user.role != "superadmin" or user.organization_id:
            if tpl.organization_id != require_org(user).id:
                raise Exception("Unauthorized")
        if name is not None:
            tpl.name = name.strip()[:120]
        if description is not None:
            tpl.description = description
        if layout_key is not None:
            if layout_key not in (
                "classic",
                "modern",
                "compact",
                "minimal",
                "uploaded",
                "networth",
            ):
                raise Exception("Invalid layout_key")
            tpl.layout_key = layout_key
        if theme is not None:
            tpl.theme = dict(theme)
        if is_active is not None:
            tpl.is_active = is_active
        tpl.save()
        return PayslipTemplateType.from_model(tpl)

    @strawberry.mutation
    def create_payslip_template(
        self,
        info: Info,
        name: str,
        layout_key: str = "classic",
        description: str = "",
        theme: Optional[JSON] = None,
        organization_id: Optional[strawberry.ID] = None,
        set_as_default: bool = False,
    ) -> PayslipTemplateType:
        from ..template_services import DEFAULT_THEME, set_org_default_template

        user = info.context.request.user
        require_payroll_admin(user, allow_hr=True)
        org = require_org(user, organization_id)
        if layout_key not in (
            "classic",
            "modern",
            "compact",
            "minimal",
            "uploaded",
            "networth",
        ):
            raise Exception("Invalid layout_key")
        tpl = PayslipTemplate.objects.create(
            organization=org,
            name=name.strip()[:120],
            description=description or "",
            layout_key=layout_key,
            theme=dict(theme or DEFAULT_THEME),
            source="custom",
            is_default=False,
            is_active=True,
            created_by=user,
        )
        if set_as_default:
            tpl = set_org_default_template(org, tpl)
        return PayslipTemplateType.from_model(tpl)

    @strawberry.mutation
    def delete_payslip_template(
        self,
        info: Info,
        template_id: strawberry.ID,
    ) -> bool:
        """Delete an org-owned payslip template. System gallery templates cannot be deleted."""
        user = info.context.request.user
        require_payroll_admin(user, allow_hr=True)
        tpl = PayslipTemplate.objects.filter(id=template_id).first()
        if not tpl:
            raise Exception("Template not found")
        if tpl.organization_id is None:
            raise Exception("System gallery templates cannot be deleted.")
        org = require_org(user)
        if user.role != "superadmin" or user.organization_id:
            if tpl.organization_id != org.id:
                raise Exception("Unauthorized")
        elif user.role == "superadmin" and not user.organization_id:
            # Superadmin without org may delete any org template
            pass
        was_default = tpl.is_default
        org_id = tpl.organization_id
        tpl.delete()
        # If default was removed, leave org without default (falls back to system classic)
        if was_default and org_id:
            pass
        return True

    @strawberry.mutation
    def ensure_founder_payroll_setup(
        self,
        info: Info,
        organization_id: Optional[strawberry.ID] = None,
    ) -> FounderPayrollSetupType:
        """Ensure default salary structure exists; return Founder checklist + structure id."""
        user = info.context.request.user
        require_payroll_admin(user)
        org = require_org(user, organization_id)
        from payroll.setup_services import (
            ensure_default_salary_structure,
            build_payroll_setup_checklist,
        )

        structure = ensure_default_salary_structure(org)
        data = build_payroll_setup_checklist(org)
        return FounderPayrollSetupType(
            checklist=PayrollSetupChecklistType(**data),
            default_structure_id=strawberry.ID(str(structure.id)),
            default_structure_name=structure.name or "Standard CTC",
        )
