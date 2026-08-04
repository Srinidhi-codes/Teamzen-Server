"""Offer letter PDF generation with company branding and optional CTC annexure."""

from __future__ import annotations

import logging
import os
import re
import tempfile
import urllib.request
from html import unescape
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)

# Helvetica core fonts are latin-1 only — map common Unicode punctuation.
_PDF_CHAR_MAP = str.maketrans(
    {
        "\u2014": "-",  # em dash
        "\u2013": "-",  # en dash
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "-",
        "\u00a0": " ",
        "\u2026": "...",
        "\u20b9": "Rs.",  # Indian rupee
        "\u20ac": "EUR",
        "\u00a3": "GBP",
    }
)


def _pdf_safe(text: str | None) -> str:
    """Normalize text so FPDF Helvetica can encode it."""
    if not text:
        return ""
    s = str(text).translate(_PDF_CHAR_MAP)
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"</(div|li|h[1-6])>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "• ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return _pdf_safe(unescape(text).strip())


def _download_image_to_temp(url: str, suffix: str = ".png") -> str | None:
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.close()
        urllib.request.urlretrieve(url, tmp.name)
        return tmp.name
    except Exception:
        return None


def _resolve_logo_path(organization) -> tuple[str | None, bool]:
    if not organization or not getattr(organization, "logo", None):
        return None, False
    logo = organization.logo
    try:
        path = logo.path
        if path and os.path.isfile(path):
            return path, False
    except Exception:
        pass
    try:
        url = logo.url
        if not url:
            return None, False
        if url.startswith("/"):
            from django.conf import settings

            candidate = os.path.join(settings.MEDIA_ROOT, logo.name)
            if os.path.isfile(candidate):
                return candidate, False
            return None, False
        suffix = os.path.splitext(logo.name or "logo.png")[1] or ".png"
        path = _download_image_to_temp(url, suffix=suffix)
        return path, bool(path)
    except Exception:
        return None, False


def _fmt_money(amount) -> str:
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return "-"
    return f"INR {val:,.2f}"


def _org_detail_lines(org) -> list[str]:
    if not org:
        return []
    lines = [org.name]
    if org.headquarters_address:
        lines.append(str(org.headquarters_address).strip())
    bits = []
    if org.gst_number:
        bits.append(f"GST: {org.gst_number}")
    if org.pan_number:
        bits.append(f"PAN: {org.pan_number}")
    if org.registration_number:
        bits.append(f"Reg: {org.registration_number}")
    if bits:
        lines.append(" · ".join(bits))
    return lines


def build_default_ctc_components(annual_ctc: float) -> list[dict[str, Any]]:
    """Simple Indian-style monthly split when HR only provides annual CTC."""
    monthly = float(annual_ctc) / 12.0
    basic = round(monthly * 0.40, 2)
    hra = round(monthly * 0.20, 2)
    special = round(monthly - basic - hra, 2)
    return [
        {"name": "Basic", "amount": basic, "frequency": "monthly"},
        {"name": "HRA", "amount": hra, "frequency": "monthly"},
        {"name": "Special Allowance", "amount": special, "frequency": "monthly"},
    ]


def resolve_ctc_snapshot(
    onboarding,
    *,
    include_ctc_annexure: bool = False,
    annual_ctc=None,
    ctc_components: list[dict] | None = None,
) -> dict | None:
    if not include_ctc_annexure:
        return None

    from decimal import Decimal

    from payroll.models import EmployeeSalaryStructure

    components: list[dict[str, Any]] = []
    annual = None

    if annual_ctc is not None and str(annual_ctc) != "":
        annual = float(Decimal(str(annual_ctc)))

    if ctc_components:
        for row in ctc_components:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            try:
                amount = float(Decimal(str(row.get("amount") or 0)))
            except Exception:
                amount = 0.0
            components.append(
                {
                    "name": name,
                    "amount": amount,
                    "frequency": (row.get("frequency") or "monthly").lower(),
                }
            )

    if annual is None or not components:
        structure = (
            EmployeeSalaryStructure.objects.filter(
                user=onboarding.user, is_active=True
            )
            .select_related("salary_structure")
            .prefetch_related("salary_structure__components__component")
            .order_by("-effective_from")
            .first()
        )
        if structure:
            if annual is None:
                annual = float(structure.annual_ctc)
            if not components and structure.salary_structure_id:
                monthly = Decimal(structure.annual_ctc) / Decimal(12)
                for sc in structure.salary_structure.components.all():
                    if sc.calculation_type == "percentage":
                        amount = float(
                            (monthly * Decimal(sc.value) / Decimal(100)).quantize(
                                Decimal("0.01")
                            )
                        )
                    else:
                        amount = float(Decimal(sc.value).quantize(Decimal("0.01")))
                    components.append(
                        {
                            "name": sc.component.name,
                            "amount": amount,
                            "frequency": "monthly",
                        }
                    )

    if annual is None:
        return None

    if not components:
        components = build_default_ctc_components(annual)

    return {
        "annual_ctc": annual,
        "monthly_ctc": round(annual / 12.0, 2),
        "components": components,
        "currency": "INR",
        "note": (
            "This annexure forms part of the offer. Statutory deductions "
            "(PF, ESI, tax) apply as per law and company policy."
        ),
    }


def render_offer_pdf_url(
    onboarding,
    subject: str,
    body_html: str,
    *,
    ctc_snapshot: dict | None = None,
) -> str:
    """
    Render a branded offer PDF (logo + company details + body + optional CTC
    annexure) and upload to Cloudinary. Returns secure URL or "".
    """
    from fpdf import FPDF
    import cloudinary.uploader

    user = onboarding.user
    org = onboarding.organization
    body_text = _strip_html(body_html)
    tmp_paths: list[str] = []

    try:
        logo_path, logo_is_temp = _resolve_logo_path(org)
        if logo_is_temp and logo_path:
            tmp_paths.append(logo_path)

        pdf = FPDF(unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.add_page()
        pdf.set_margins(18, 18, 18)

        # Header: logo + company block
        header_y = 14
        text_x = 18
        if logo_path:
            try:
                pdf.image(logo_path, x=18, y=header_y, h=16)
                text_x = 42
            except Exception:
                logger.exception("Failed to place org logo on offer PDF")

        pdf.set_xy(text_x, header_y)
        pdf.set_font("helvetica", "B", 14)
        pdf.set_text_color(15, 23, 42)
        for i, line in enumerate(_org_detail_lines(org) or ["Offer Letter"]):
            if i == 0:
                pdf.set_font("helvetica", "B", 14)
                pdf.set_text_color(15, 23, 42)
            else:
                pdf.set_font("helvetica", "", 9)
                pdf.set_text_color(71, 85, 105)
            pdf.set_x(text_x)
            pdf.multi_cell(0, 5, _pdf_safe(line)[:140])

        pdf.set_draw_color(16, 185, 129)
        pdf.set_line_width(0.6)
        pdf.line(18, 36, 192, 36)

        pdf.set_y(42)
        pdf.set_font("helvetica", "B", 13)
        pdf.set_text_color(15, 23, 42)
        pdf.multi_cell(0, 7, _pdf_safe(subject or "Offer of Employment")[:160])

        pdf.ln(2)
        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(100, 116, 139)
        candidate = f"{user.first_name} {user.last_name}".strip() or user.email
        meta = f"Candidate: {candidate}  |  {user.email}"
        if onboarding.join_date:
            meta += f"  |  Join: {onboarding.join_date.strftime('%d %b %Y')}"
        pdf.multi_cell(0, 5, _pdf_safe(meta))

        pdf.ln(6)
        pdf.set_font("helvetica", "", 11)
        pdf.set_text_color(30, 41, 59)
        for para in body_text.split("\n"):
            line = para.strip()
            if not line:
                pdf.ln(3)
                continue
            pdf.multi_cell(0, 6, _pdf_safe(line))
            pdf.ln(1)

        pdf.ln(10)
        pdf.set_font("helvetica", "I", 9)
        pdf.set_text_color(100, 116, 139)
        company = org.name if org else "Company"
        pdf.multi_cell(0, 5, _pdf_safe(f"For {company}  |  Authorized HR / People Team"))

        # CTC annexure
        if ctc_snapshot and ctc_snapshot.get("annual_ctc") is not None:
            pdf.add_page()
            pdf.set_font("helvetica", "B", 14)
            pdf.set_text_color(15, 23, 42)
            pdf.multi_cell(0, 8, _pdf_safe("Annexure A - Compensation (CTC)"))
            pdf.ln(2)
            pdf.set_draw_color(16, 185, 129)
            pdf.line(18, pdf.get_y(), 192, pdf.get_y())
            pdf.ln(6)

            pdf.set_font("helvetica", "", 11)
            pdf.set_text_color(30, 41, 59)
            pdf.multi_cell(
                0,
                6,
                _pdf_safe(f"Annual CTC: {_fmt_money(ctc_snapshot.get('annual_ctc'))}"),
            )
            pdf.multi_cell(
                0,
                6,
                _pdf_safe(f"Monthly CTC: {_fmt_money(ctc_snapshot.get('monthly_ctc'))}"),
            )
            pdf.ln(4)

            # Table header
            pdf.set_fill_color(236, 253, 245)
            pdf.set_font("helvetica", "B", 10)
            pdf.cell(90, 8, "Component", border=1, fill=True)
            pdf.cell(40, 8, "Frequency", border=1, fill=True, align="C")
            pdf.cell(44, 8, "Amount", border=1, fill=True, align="R")
            pdf.ln()

            pdf.set_font("helvetica", "", 10)
            for row in ctc_snapshot.get("components") or []:
                pdf.cell(90, 8, _pdf_safe(str(row.get("name", "")))[:42], border=1)
                pdf.cell(
                    40,
                    8,
                    _pdf_safe(str(row.get("frequency", "monthly")).title())[:16],
                    border=1,
                    align="C",
                )
                pdf.cell(
                    44,
                    8,
                    _pdf_safe(_fmt_money(row.get("amount"))),
                    border=1,
                    align="R",
                )
                pdf.ln()

            pdf.ln(6)
            pdf.set_font("helvetica", "I", 9)
            pdf.set_text_color(100, 116, 139)
            note = ctc_snapshot.get("note") or ""
            if note:
                pdf.multi_cell(0, 5, _pdf_safe(note))

        pdf.ln(8)
        pdf.set_font("helvetica", "I", 8)
        pdf.set_text_color(148, 163, 184)
        pdf.multi_cell(
            0,
            4,
            _pdf_safe(f"Generated for {user.email} | Teamzen Onboarding"),
        )

        buf = BytesIO(pdf.output())
        buf.seek(0)

        result = cloudinary.uploader.upload(
            buf,
            resource_type="raw",
            folder=f"employee_docs/{onboarding.organization_id}/{onboarding.user_id}/offers",
            public_id=f"offer_{onboarding.id}",
            overwrite=True,
            format="pdf",
        )
        return result.get("secure_url") or result.get("url") or ""
    finally:
        for path in tmp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass


def upload_offer_pdf_bytes(
    onboarding, file_bytes: bytes, *, filename: str = "offer.pdf", public_id: str | None = None
) -> str:
    """Upload an offer PDF to Cloudinary; return secure URL."""
    import cloudinary.uploader

    buf = BytesIO(file_bytes)
    buf.seek(0)
    result = cloudinary.uploader.upload(
        buf,
        resource_type="raw",
        folder=f"employee_docs/{onboarding.organization_id}/{onboarding.user_id}/offers",
        public_id=public_id or f"offer_{onboarding.id}",
        overwrite=True,
        format="pdf",
        filename_override=filename,
    )
    return result.get("secure_url") or result.get("url") or ""


def download_pdf_bytes(url: str) -> bytes | None:
    """Download offer PDF bytes for email attachment. Returns None on failure."""
    if not url:
        return None
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "TeamzenOfferMailer/1.0",
                "Accept": "application/pdf,application/octet-stream,*/*",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = resp.read()
        if not data:
            logger.warning("Empty response downloading offer PDF from %s", url)
            return None
        # Soft check — Cloudinary raw may not set content-type to pdf
        if len(data) < 20:
            logger.warning("Suspiciously small offer PDF (%s bytes) from %s", len(data), url)
            return None
        return data
    except Exception:
        logger.exception("Failed to download offer PDF from %s", url)
        return None
