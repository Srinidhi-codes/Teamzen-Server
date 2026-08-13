"""
Form 16 Part B helpers.

Layout reference: repo root MSXPS6972G_PARTB_2026-27.pdf (flat TRACES-style Part B).
We redraw with fpdf2 — that PDF is not AcroForm-fillable.
"""
from __future__ import annotations

import io
import re
from datetime import date
from decimal import Decimal
from typing import Any

from django.utils import timezone

PAN_IN_FILENAME_RE = re.compile(r"([A-Z]{5}[0-9]{4}[A-Z])", re.IGNORECASE)


def parse_financial_year(fy: str) -> tuple[date, date, str, str]:
    """
    '2025-26' -> (2025-04-01, 2026-03-31, AY '2026-27', FY label '2025-26').
    """
    raw = (fy or "").strip().replace("/", "-")
    m = re.match(r"^(\d{4})\s*-\s*(\d{2}|\d{4})$", raw)
    if not m:
        today = timezone.localdate()
        start_year = today.year if today.month >= 4 else today.year - 1
    else:
        start_year = int(m.group(1))
        end_part = m.group(2)
        if len(end_part) == 4:
            end_year = int(end_part)
        else:
            end_year = start_year + 1
        if end_year != start_year + 1:
            end_year = start_year + 1

    fy_start = date(start_year, 4, 1)
    fy_end = date(start_year + 1, 3, 31)
    ay = f"{start_year + 1}-{str(start_year + 2)[-2:]}"
    fy_label = f"{start_year}-{str(start_year + 1)[-2:]}"
    return fy_start, fy_end, ay, fy_label


def extract_pan_from_filename(name: str) -> str | None:
    stem = (name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    m = PAN_IN_FILENAME_RE.search(stem.upper())
    return m.group(1).upper() if m else None


def _money(n: Decimal | float | int | None) -> Decimal:
    if n is None:
        return Decimal("0.00")
    return Decimal(str(n)).quantize(Decimal("0.01"))


def build_form16_summary(
    user,
    *,
    financial_year: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Aggregate payslips for FY and map to Part B-ish lines.
    Overrides may include: section_80c, hra_exempt, other_exempt_10, tds_total, std_deduction.
    """
    from payroll.models import Payslip, PayslipComponent

    fy_start, fy_end, assessment_year, fy_label = parse_financial_year(financial_year)
    overrides = overrides or {}

    # Payslips whose payroll month falls in FY (Apr start_year .. Mar start_year+1)
    slips = (
        Payslip.objects.filter(
            user=user,
            status__in=["published", "paid", "draft"],
        )
        .select_related("payroll_run")
        .prefetch_related("components")
    )
    matched = []
    for s in slips:
        run = s.payroll_run
        if not run:
            continue
        # Month/year of payroll
        y, m = run.year, run.month
        if (y == fy_start.year and m >= 4) or (y == fy_end.year and m <= 3):
            matched.append(s)

    gross = sum((_money(s.gross_earnings) for s in matched), Decimal("0.00"))
    hra_paid = Decimal("0.00")
    basic_paid = Decimal("0.00")
    tds = Decimal("0.00")
    for s in matched:
        for c in s.components.all():
            code = (c.component_code or "").upper()
            name = (c.component_name or "").upper()
            amt = _money(c.amount)
            if code in ("HRA",) or "HRA" in name or "HOUSE RENT" in name:
                if (c.component_type or "").lower().startswith("earn"):
                    hra_paid += amt
            if code in ("BASIC", "BASIC_SALARY") or name.startswith("BASIC"):
                if (c.component_type or "").lower().startswith("earn"):
                    basic_paid += amt
            if code in ("TDS", "IT", "INCOME_TAX") or "TDS" in name or "INCOME TAX" in name:
                if (c.component_type or "").lower().startswith("deduct"):
                    tds += amt

    section_80c = _money(overrides.get("section_80c", 0))
    hra_exempt = _money(overrides.get("hra_exempt", 0))
    other_exempt = _money(overrides.get("other_exempt_10", 0))
    if "tds_total" in overrides:
        tds = _money(overrides["tds_total"])
    std_deduction = _money(overrides.get("std_deduction", 75000))

    total_exempt_10 = hra_exempt + other_exempt
    salary_from_employer = max(gross - total_exempt_10, Decimal("0.00"))
    income_salaries = max(salary_from_employer - std_deduction, Decimal("0.00"))
    chapter_via = section_80c  # simplified
    total_taxable = max(income_salaries - chapter_via, Decimal("0.00"))

    # Rough new-regime style rebate placeholder (not a tax engine)
    rebate_87a = Decimal("0.00")
    if total_taxable <= Decimal("700000"):
        # Cap illustrative rebate
        rebate_87a = min(Decimal("25000"), total_taxable * Decimal("0.05"))

    tax_on_total = max(total_taxable * Decimal("0.05") - rebate_87a, Decimal("0.00"))
    if "tax_on_total" in overrides:
        tax_on_total = _money(overrides["tax_on_total"])

    org = user.organization
    emp_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email
    emp_addr = (getattr(user, "residential_address", None) or "").strip()
    if not emp_addr and user.office_location_id:
        emp_addr = (user.office_location.address or "")[:500]

    period_from = fy_start
    if (
        user.date_of_joining
        and fy_start <= user.date_of_joining <= fy_end
    ):
        period_from = user.date_of_joining
    period_to = fy_end
    if (
        user.date_of_exit
        and fy_start <= user.date_of_exit <= fy_end
    ):
        period_to = user.date_of_exit

    # Short TRACES-like certificate id (7 chars)
    import hashlib

    cert_seed = f"{user.id}-{fy_label}-{(user.pan_number or '').upper()}"
    certificate_no = (
        overrides.get("certificate_no")
        or hashlib.sha1(cert_seed.encode()).hexdigest()[:7].upper()
    )

    signatory_name = (overrides.get("signatory_name") or "").strip()
    signatory_father = (overrides.get("signatory_father") or "").strip()
    signatory_designation = (overrides.get("signatory_designation") or "").strip()
    place = (overrides.get("place") or "").strip()
    if org and not place:
        # First line / city from HQ address
        place = (org.headquarters_address or "").split("\n")[0].strip()[:80]
    if org and not signatory_name:
        # Prefer an org admin/hr as default signatory
        from django.contrib.auth import get_user_model

        User = get_user_model()
        admin = (
            User.objects.filter(organization=org, role__in=["admin", "hr", "superadmin"])
            .order_by("id")
            .first()
        )
        if admin:
            signatory_name = (
                f"{admin.first_name or ''} {admin.last_name or ''}".strip() or admin.email
            )
            if not signatory_designation:
                signatory_designation = (
                    getattr(getattr(admin, "designation", None), "name", None)
                    or admin.role
                    or "Authorised Signatory"
                ).upper()

    return {
        "financial_year": fy_label,
        "assessment_year": assessment_year,
        "employer_name": org.name if org else "",
        "employer_address": (org.headquarters_address if org else "") or "",
        "employer_phone": (overrides.get("employer_phone") or "").strip(),
        "employer_email": (overrides.get("employer_email") or "").strip(),
        "employer_pan": (org.pan_number if org else "") or "",
        "employer_tan": (getattr(org, "tan_number", None) or "") if org else "",
        "cit_tds_office": (getattr(org, "cit_tds_office", None) or "") if org else "",
        "employee_name": emp_name.upper(),
        "employee_address": emp_addr,
        "employee_pan": (user.pan_number or "").upper(),
        "employee_id": user.employee_id or str(user.id),
        "period_from": period_from.strftime("%d-%b-%Y"),
        "period_to": period_to.strftime("%d-%b-%Y"),
        "gross_salary": float(gross),
        "basic_paid": float(basic_paid),
        "hra_paid": float(hra_paid),
        "hra_exempt": float(hra_exempt),
        "other_exempt_10": float(other_exempt),
        "total_exempt_10": float(total_exempt_10),
        "salary_from_employer": float(salary_from_employer),
        "std_deduction": float(std_deduction),
        "income_salaries": float(income_salaries),
        "section_80c": float(section_80c),
        "chapter_via_total": float(chapter_via),
        "total_taxable": float(total_taxable),
        "rebate_87a": float(rebate_87a),
        "tax_on_total": float(tax_on_total),
        "tds_total": float(tds),
        "payslip_count": len(matched),
        "certificate_no": certificate_no,
        "generated_on": timezone.localdate().strftime("%d-%b-%Y"),
        "opting_out_115bac": (overrides.get("opting_out_115bac") or "No").strip() or "No",
        "signatory_name": signatory_name,
        "signatory_father": signatory_father,
        "signatory_designation": signatory_designation or "AUTHORISED SIGNATORY",
        "place": place,
    }


def _fmt(n: float | Decimal) -> str:
    return f"{float(n):,.2f}"


def _pdf_safe(text: str) -> str:
    if not text:
        return ""
    return (
        str(text)
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("·", "-")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def render_form16_part_b_pdf(summary: dict[str, Any]) -> bytes:
    """
    Render Form 16 Part B using the exact TRACES sample background/structure
    (MSXPS6972G_PARTB_2026-27.pdf → blank template + coordinate fill).
    """
    from documents.form16_pdf import render_form16_part_b_from_template

    return render_form16_part_b_from_template(summary)
