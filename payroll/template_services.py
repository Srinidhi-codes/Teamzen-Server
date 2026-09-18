"""Standard payslip template gallery and organization defaults."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_THEME: dict[str, Any] = {
    "primary": "#212529",
    "muted": "#6c757d",
    "accent": "#0d6efd",
    "hero_bg": "#f8f9fa",
    "earning_bg": "#f0fdf4",
    "deduction_bg": "#fef2f2",
    "show_logo": True,
    "show_net_hero": True,
    "show_teamzen_mark": True,
    "table_header_bg": "#212529",
    "table_header_fg": "#ffffff",
}


SYSTEM_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "Statutory India",
        "slug": "classic-india",
        "description": "Conventional Indian payroll format with employee details, earnings, deductions, net pay, and amount in words.",
        "layout_key": "classic",
        "theme": {
            **DEFAULT_THEME,
            "accent": "#0f766e",
            "hero_bg": "#f8fafc",
        },
    },
    {
        "name": "Modern Professional",
        "slug": "modern-teal",
        "description": "Branded contemporary format with a prominent net-pay summary and clear payroll sections.",
        "layout_key": "modern",
        "theme": {
            **DEFAULT_THEME,
            "primary": "#0f172a",
            "accent": "#0d9488",
            "hero_bg": "#ccfbf1",
            "earning_bg": "#ecfdf5",
            "deduction_bg": "#fff1f2",
            "table_header_bg": "#0f766e",
        },
    },
    {
        "name": "Finance Register",
        "slug": "compact-register",
        "description": "Dense payroll-ledger format for detailed earnings and deduction breakups.",
        "layout_key": "compact",
        "theme": {
            **DEFAULT_THEME,
            "accent": "#1e40af",
            "hero_bg": "#eff6ff",
            "show_net_hero": True,
            "table_header_bg": "#1e3a8a",
        },
    },
    {
        "name": "Formal Minimal",
        "slug": "minimal-clean",
        "description": "Formal monochrome format suited to established companies and printable records.",
        "layout_key": "minimal",
        "theme": {
            **DEFAULT_THEME,
            "accent": "#334155",
            "hero_bg": "#ffffff",
            "show_net_hero": False,
            "table_header_bg": "#334155",
        },
    },
]


def ensure_system_templates() -> int:
    """Idempotently seed gallery templates (organization=null). Returns created count."""
    from payroll.models import PayslipTemplate

    # Retire the old upload-replica preset and any uploaded structure copies.
    PayslipTemplate.objects.filter(
        organization=None, slug="networth-grid"
    ).delete()
    PayslipTemplate.objects.filter(source="cloned").delete()

    created = 0
    for spec in SYSTEM_TEMPLATES:
        obj, was_created = PayslipTemplate.objects.get_or_create(
            organization=None,
            slug=spec["slug"],
            defaults={
                "name": spec["name"],
                "description": spec["description"],
                "layout_key": spec["layout_key"],
                "theme": spec["theme"],
                "source": "system",
                "is_default": spec["slug"] == "classic-india",
                "is_active": True,
            },
        )
        if was_created:
            created += 1
        else:
            changed = False
            for field in ("name", "description", "layout_key"):
                if getattr(obj, field) != spec[field]:
                    setattr(obj, field, spec[field])
                    changed = True
            if obj.theme != spec["theme"]:
                obj.theme = spec["theme"]
                changed = True
            if changed:
                obj.save(update_fields=["name", "description", "layout_key", "theme", "updated_at"])
    return created


def resolve_template_for_org(organization):
    """Active default for org, else system classic."""
    from payroll.models import PayslipTemplate

    ensure_system_templates()
    if organization is not None:
        org_default = (
            PayslipTemplate.objects.filter(
                organization=organization, is_default=True, is_active=True
            )
            .order_by("-updated_at")
            .first()
        )
        if org_default:
            return org_default
    return (
        PayslipTemplate.objects.filter(
            organization=None, slug="classic-india", is_active=True
        ).first()
        or PayslipTemplate.objects.filter(organization=None, is_active=True).first()
    )


def theme_for_payslip(payslip, template_override=None) -> tuple[str, dict]:
    """Return (layout_key, theme) for PDF generation."""
    if template_override is not None:
        theme = {**DEFAULT_THEME, **(template_override.theme or {})}
        return template_override.layout_key or "classic", theme

    org = payslip.payroll_run.organization
    tpl = resolve_template_for_org(org)
    if not tpl:
        return "classic", dict(DEFAULT_THEME)
    theme = {**DEFAULT_THEME, **(tpl.theme or {})}
    return tpl.layout_key or "classic", theme


def build_demo_payslip_mock(organization):
    """In-memory sample payslip for template demo PDF (not saved to DB)."""
    from types import SimpleNamespace
    from decimal import Decimal
    from datetime import date

    user = SimpleNamespace(
        id=0,
        first_name="Aanya",
        last_name="Sharma",
        email="aanya.demo@example.com",
        employee_id="EMP-DEMO",
        pan_number="ABCDE1234F",
        bank_account_number="50100234567890",
        bank_ifsc_code="HDFC0001234",
        date_of_birth=date(1994, 5, 12),
        date_of_joining=date(2022, 4, 1),
    )
    components = [
        SimpleNamespace(
            component_name="Basic",
            component_code="BASIC",
            component_type="earning",
            amount=Decimal("34000"),
        ),
        SimpleNamespace(
            component_name="House Rent Allowance",
            component_code="HRA",
            component_type="earning",
            amount=Decimal("13600"),
        ),
        SimpleNamespace(
            component_name="Special Allowance",
            component_code="SPECIAL",
            component_type="earning",
            amount=Decimal("37400"),
        ),
        SimpleNamespace(
            component_name="Professional Tax",
            component_code="PT",
            component_type="deduction",
            amount=Decimal("200"),
        ),
        SimpleNamespace(
            component_name="Provident Fund",
            component_code="PF",
            component_type="deduction",
            amount=Decimal("4080"),
        ),
        SimpleNamespace(
            component_name="Income Tax",
            component_code="TDS",
            component_type="deduction",
            amount=Decimal("8270"),
        ),
    ]

    class _CompManager:
        def filter(self, **kwargs):
            ctype = kwargs.get("component_type")
            if ctype:
                return [c for c in components if c.component_type == ctype]
            return list(components)

    return SimpleNamespace(
        id=0,
        user=user,
        designation="Software Engineer",
        department="Engineering",
        worked_days=Decimal("22.0"),
        lop_days=Decimal("0.0"),
        gross_earnings=Decimal("85000"),
        total_deductions=Decimal("12550"),
        net_pay=Decimal("72450"),
        components=_CompManager(),
        payroll_run=SimpleNamespace(
            organization=organization,
            month=3,
            year=2026,
        ),
    )


def generate_demo_pdf_bytes(organization, template) -> bytes:
    """Generate a demo PDF from one of the standard gallery templates."""
    from payroll.services import PayrollService

    mock = build_demo_payslip_mock(organization)
    return PayrollService.generate_payslip_pdf(
        mock, template_override=template, persist=False
    )


def render_pdf_first_page_to_png(file_bytes: bytes, zoom: float = 2.0) -> bytes | None:
    """Rasterize page 1 of a PDF to PNG bytes (requires pymupdf)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("pymupdf not installed; cannot rasterize uploaded payslip")
        return None
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        if doc.page_count < 1:
            doc.close()
            return None
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        png = pix.tobytes("png")
        doc.close()
        return png
    except Exception:
        logger.exception("Failed to rasterize PDF page")
        return None


def hex_to_rgb(hex_color: str, fallback=(33, 37, 41)) -> tuple[int, int, int]:
    s = (hex_color or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return fallback
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return fallback


def set_org_default_template(organization, template):
    from payroll.models import PayslipTemplate

    PayslipTemplate.objects.filter(
        organization=organization, is_default=True
    ).update(is_default=False)
    if template.organization_id is None:
        # Keep one organization-owned default per standard gallery design.
        clone, _ = PayslipTemplate.objects.update_or_create(
            organization=organization,
            slug=f"{template.slug}-org" if template.slug else "",
            defaults={
                "name": template.name,
                "description": template.description,
                "layout_key": template.layout_key,
                "theme": dict(template.theme or DEFAULT_THEME),
                "source": "custom",
                "is_default": True,
                "is_active": True,
            },
        )
        return clone
    template.is_default = True
    template.is_active = True
    template.save(update_fields=["is_default", "is_active", "updated_at"])
    return template


__all__ = [
    "DEFAULT_THEME",
    "SYSTEM_TEMPLATES",
    "build_demo_payslip_mock",
    "ensure_system_templates",
    "generate_demo_pdf_bytes",
    "hex_to_rgb",
    "render_pdf_first_page_to_png",
    "resolve_template_for_org",
    "set_org_default_template",
    "theme_for_payslip",
]  # explicit public API

