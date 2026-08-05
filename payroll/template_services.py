"""Payslip template gallery: system presets, org defaults, clone-from-upload."""

from __future__ import annotations

import io
import json
import logging
import re
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
        "name": "Classic India",
        "slug": "classic-india",
        "description": "Standard Indian payslip with net-pay hero and two-column employee grid.",
        "layout_key": "classic",
        "theme": {
            **DEFAULT_THEME,
            "accent": "#0f766e",
            "hero_bg": "#f8fafc",
        },
    },
    {
        "name": "Modern Teal",
        "slug": "modern-teal",
        "description": "Bold net-pay band with teal accents — great for product startups.",
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
        "name": "Compact Register",
        "slug": "compact-register",
        "description": "Tighter spacing for denser salary breakups — good for finance-heavy teams.",
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
        "name": "Minimal Clean",
        "slug": "minimal-clean",
        "description": "Quiet layout without a large net-pay hero — closer to traditional slips.",
        "layout_key": "minimal",
        "theme": {
            **DEFAULT_THEME,
            "accent": "#334155",
            "hero_bg": "#ffffff",
            "show_net_hero": False,
            "table_header_bg": "#334155",
        },
    },
    {
        "name": "Networth Grid",
        "slug": "networth-grid",
        "description": "Clean branded grid with side color bar, Full/Actual earnings, amount in words.",
        "layout_key": "networth",
        "theme": {
            **DEFAULT_THEME,
            "renderer": "networth_replica",
            "primary": "#141414",
            "accent": "#800020",
            "show_net_hero": False,
        },
    },
]


def ensure_system_templates() -> int:
    """Idempotently seed gallery templates (organization=null). Returns created count."""
    from payroll.models import PayslipTemplate

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
        elif obj.source != "system":
            # Keep slug reserved for system
            pass
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
    """
    Demo PDF for a template.
    Uploaded / Networth-replica templates → clean drawn layout (never patch PDF).
    Gallery layouts → Teamzen theme render.
    """
    from payroll.services import PayrollService

    mock = build_demo_payslip_mock(organization)
    # Uploaded payslips use the clean Networth-style replica (no redact patching)
    if _template_uses_uploaded_pdf(template) or (template and template.layout_key == "networth"):
        from payroll.networth_layout import render_networth_style_payslip

        return render_networth_style_payslip(mock)

    return PayrollService.generate_payslip_pdf(
        mock, template_override=template, persist=False
    )


def _template_uses_uploaded_pdf(template) -> bool:
    if not template:
        return False
    if getattr(template, "layout_key", None) in ("uploaded", "networth"):
        return True
    if getattr(template, "source", None) == "cloned" and getattr(template, "source_file", None):
        return True
    theme = getattr(template, "theme", None) or {}
    return bool(theme.get("use_source_pdf") or theme.get("renderer") == "networth_replica")


def read_template_source_bytes(template) -> bytes | None:
    """Read the stored source PDF bytes from storage."""
    if not template or not template.source_file:
        return None
    try:
        template.source_file.open("rb")
        try:
            return template.source_file.read()
        finally:
            template.source_file.close()
    except Exception:
        logger.exception("Could not read template source_file id=%s", getattr(template, "id", None))
        return None


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


def set_org_default_template(organization, template) -> None:
    from payroll.models import PayslipTemplate

    PayslipTemplate.objects.filter(
        organization=organization, is_default=True
    ).update(is_default=False)
    if template.organization_id is None:
        # Clone system template into org as default so theme can be customized later
        clone = PayslipTemplate.objects.create(
            organization=organization,
            name=template.name,
            slug=f"{template.slug}-org" if template.slug else "",
            description=template.description,
            layout_key=template.layout_key,
            theme=dict(template.theme or DEFAULT_THEME),
            source="custom",
            is_default=True,
            is_active=True,
        )
        return clone
    template.is_default = True
    template.is_active = True
    template.save(update_fields=["is_default", "is_active", "updated_at"])
    return template


def extract_text_from_pdf(file_bytes: bytes, max_chars: int = 8000) -> str:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        return ""
    reader = PdfReader(io.BytesIO(file_bytes))
    parts: list[str] = []
    for page in reader.pages[:4]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n".join(parts).strip()
    return text[:max_chars]


def clone_template_from_upload(
    organization,
    *,
    file_bytes: bytes,
    file_name: str,
    name: str = "",
    created_by=None,
):
    """
    Store uploaded payslip PDF as reference and create a clean Networth-style
    replica template. Generation always redraws from scratch (no PDF patching).
    """
    from django.core.files.base import ContentFile
    from payroll.models import PayslipTemplate

    ensure_system_templates()
    lower = (file_name or "").lower()
    if not lower.endswith(".pdf"):
        raise ValueError("Please upload a PDF payslip to use as a template.")

    base = (name or "").strip()
    if not base:
        base = (file_name or "Uploaded payslip").rsplit(".", 1)[0]
    tpl_name = base[:120] or "Uploaded payslip"

    field_map: dict = {}
    try:
        from payroll.pdf_fill import build_payslip_field_map

        field_map = build_payslip_field_map(file_bytes)
    except Exception:
        logger.exception("Could not analyze uploaded payslip structure")
        field_map = {}

    notes = (
        "Clean replica of your uploaded payslip design (Networth-style grid). "
        "Payroll redraws the layout from scratch — no overlapping/patched text."
    )

    tpl = PayslipTemplate(
        organization=organization,
        name=tpl_name,
        slug="",
        description="Pixel-clean replica of uploaded payslip",
        layout_key="networth",
        theme={
            **DEFAULT_THEME,
            "use_source_pdf": True,
            "renderer": "networth_replica",
            "fill_in_place": False,
            "field_map": field_map,
            "primary": "#141414",
            "accent": "#800020",
        },
        source="cloned",
        preview_notes=notes[:4000],
        is_default=False,
        is_active=True,
        created_by=created_by,
    )
    tpl.source_file.save(
        file_name or "payslip.pdf",
        ContentFile(file_bytes),
        save=False,
    )
    tpl.save()
    return tpl


def _extract_json_object(text: str) -> dict:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}
