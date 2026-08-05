"""Shared payroll setup helpers for import and Founder mode."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from django.contrib.auth import get_user_model

from payroll.models import (
    SalaryComponent,
    SalaryStructure,
    SalaryStructureComponent,
    EmployeeSalaryStructure,
    SalaryAdvance,
)

User = get_user_model()


def ensure_default_salary_structure(organization):
    """
    Return an active salary structure for the org.
    Creates Basic (40%) + HRA (20%) of CTC if none exists.
    """
    structure = (
        SalaryStructure.objects.filter(organization=organization, is_active=True)
        .order_by("id")
        .first()
    )
    if structure:
        return structure

    basic, _ = SalaryComponent.objects.get_or_create(
        organization=organization,
        code="BASIC",
        defaults={
            "name": "Basic",
            "component_type": "earning",
            "is_taxable": True,
            "is_statutory": False,
            "description": "Auto-created for Founder payroll setup",
        },
    )
    hra, _ = SalaryComponent.objects.get_or_create(
        organization=organization,
        code="HRA",
        defaults={
            "name": "HRA",
            "component_type": "earning",
            "is_taxable": True,
            "is_statutory": False,
            "description": "Auto-created for Founder payroll setup",
        },
    )
    structure = SalaryStructure.objects.create(
        organization=organization,
        name="Standard CTC",
        description="Auto-created for Founder payroll mode",
        is_active=True,
    )
    SalaryStructureComponent.objects.create(
        salary_structure=structure,
        component=basic,
        calculation_type="percentage",
        value=Decimal("40"),
        base_component=None,
    )
    SalaryStructureComponent.objects.create(
        salary_structure=structure,
        component=hra,
        calculation_type="percentage",
        value=Decimal("20"),
        base_component=None,
    )
    return structure


def build_payroll_setup_checklist(organization) -> dict:
    """Counts used by payrollSetupChecklist and Founder mode."""
    components = SalaryComponent.objects.filter(organization=organization).count()
    structures = SalaryStructure.objects.filter(organization=organization).count()
    assigned_ids = set(
        EmployeeSalaryStructure.objects.filter(
            user__organization=organization, is_active=True
        )
        .values_list("user_id", flat=True)
        .distinct()
    )
    assigned = len(assigned_ids)
    advances = SalaryAdvance.objects.filter(
        organization=organization, status="active"
    ).count()

    active_qs = User.objects.filter(
        organization=organization,
        is_active=True,
        role__in=["employee", "manager"],
    )
    active_employees = active_qs.count()
    employees_missing_ctc = active_qs.exclude(id__in=assigned_ids).count()
    employees_missing_bank = active_qs.filter(
        Q(bank_account_number__isnull=True)
        | Q(bank_account_number="")
        | Q(bank_ifsc_code__isnull=True)
        | Q(bank_ifsc_code="")
    ).count()

    return {
        "components": components,
        "structures": structures,
        "employees_with_ctc": assigned,
        "active_advances": advances,
        "ready": components > 0 and structures > 0 and assigned > 0,
        "active_employees": active_employees,
        "employees_missing_ctc": employees_missing_ctc,
        "employees_missing_bank": employees_missing_bank,
    }
