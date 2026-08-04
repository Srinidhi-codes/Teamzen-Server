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
    """
    Indian-style annual CTC split (inspired by typical offer annexures).
    Amounts are annual figures so the PDF can show monthly = annual/12.
    """
    annual = float(annual_ctc)
    # Approximate split totaling ~100% of annual CTC
    weights = [
        ("Basic Salary", 0.35),
        ("House Rent Allowance (HRA)", 0.14),
        ("Leave Travel Allowance (LTA)", 0.03),
        ("Transport Allowance", 0.024),
        ("Medical Allowance", 0.025),
        ("Special Allowance", 0.301),
        ("Employee PF Contribution", 0.036),
        ("Employer PF Contribution", 0.036),
        ("Health Insurance", 0.008),
        ("Performance Variable Pay", 0.05),
    ]
    components: list[dict[str, Any]] = []
    allocated = 0.0
    for i, (name, w) in enumerate(weights):
        if i == len(weights) - 1:
            amount = round(annual - allocated, 2)
        else:
            amount = round(annual * w, 2)
            allocated += amount
        components.append(
            {
                "name": name,
                "amount": amount,
                "frequency": "annual",
                "monthly": round(amount / 12.0, 2),
            }
        )
    return components


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
            freq = (row.get("frequency") or "monthly").lower()
            if freq == "monthly":
                annual_amt = round(amount * 12.0, 2)
                monthly_amt = amount
            else:
                annual_amt = amount
                monthly_amt = round(amount / 12.0, 2)
            components.append(
                {
                    "name": name,
                    "amount": annual_amt,
                    "monthly": monthly_amt,
                    "frequency": "annual",
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
                            "amount": round(amount * 12.0, 2),
                            "monthly": amount,
                            "frequency": "annual",
                        }
                    )

    if annual is None:
        return None

    if not components:
        components = build_default_ctc_components(annual)

    # Ensure monthly field exists
    for row in components:
        if "monthly" not in row:
            freq = (row.get("frequency") or "monthly").lower()
            amt = float(row.get("amount") or 0)
            if freq == "monthly":
                row["monthly"] = amt
                row["amount"] = round(amt * 12.0, 2)
            else:
                row["monthly"] = round(amt / 12.0, 2)

    monthly_gross = round(
        sum(float(r.get("monthly") or 0) for r in components), 2
    )

    return {
        "annual_ctc": annual,
        "monthly_ctc": round(annual / 12.0, 2),
        "monthly_in_hand_approx": monthly_gross,
        "components": components,
        "currency": "INR",
        "note": (
            "This annexure forms part of the offer. Amounts are indicative CTC "
            "break-up before statutory deductions (PF, ESI, professional tax, TDS). "
            "Final structure follows company payroll policy."
        ),
    }


def _draw_header(pdf, org, logo_path: str | None):
    header_y = 12
    text_x = 18
    if logo_path:
        try:
            pdf.image(logo_path, x=18, y=header_y, h=14)
            text_x = 40
        except Exception:
            logger.exception("Failed to place org logo on offer PDF")

    company = _pdf_safe(org.name if org else "Company")
    pdf.set_xy(text_x, header_y)
    pdf.set_font("helvetica", "B", 13)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 6, company, ln=1)

    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(71, 85, 105)
    if org and org.headquarters_address:
        pdf.set_x(text_x)
        pdf.multi_cell(0, 4, _pdf_safe(str(org.headquarters_address).strip())[:180])

    bits = []
    if org:
        if org.gst_number:
            bits.append(f"GST: {org.gst_number}")
        if org.pan_number:
            bits.append(f"PAN: {org.pan_number}")
        if org.registration_number:
            bits.append(f"Reg: {org.registration_number}")
    if bits:
        pdf.set_x(text_x)
        pdf.multi_cell(0, 4, _pdf_safe(" | ".join(bits)))

    pdf.set_draw_color(16, 185, 129)
    pdf.set_line_width(0.7)
    y = max(pdf.get_y() + 2, 30)
    pdf.line(18, y, 192, y)
    pdf.set_y(y + 4)


def _draw_footer_signature(pdf):
    pdf.set_y(-18)
    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(0, 4, "- Acceptance Signature -", align="C")


def _fmt_inr(amount) -> str:
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return "-"
    # Indian-style grouping approximation
    return f"INR {val:,.2f}"


def _annual_to_lacs(annual: float) -> str:
    try:
        lacs = float(annual) / 100000.0
        if abs(lacs - round(lacs)) < 0.05:
            return f"{int(round(lacs))}.0 lac"
        return f"{lacs:.1f} lac"
    except Exception:
        return _fmt_inr(annual)


def render_offer_pdf_url(
    onboarding,
    subject: str,
    body_html: str,
    *,
    ctc_snapshot: dict | None = None,
) -> str:
    """
    Render a multi-page branded offer PDF (letter + terms + optional CTC
    annexure + acceptance) and upload to Cloudinary.
    """
    from datetime import date

    from fpdf import FPDF
    import cloudinary.uploader

    user = onboarding.user
    org = onboarding.organization
    body_text = _strip_html(body_html)
    tmp_paths: list[str] = []
    candidate = _pdf_safe(
        f"{user.first_name} {user.last_name}".strip() or user.email
    )
    company = _pdf_safe(org.name if org else "Company")
    designation = _pdf_safe(
        getattr(getattr(user, "designation", None), "name", None) or "your role"
    )
    department = _pdf_safe(
        getattr(getattr(user, "department", None), "name", None) or ""
    )
    join = (
        onboarding.join_date.strftime("%d %b %Y")
        if onboarding.join_date
        else "the mutually agreed date"
    )
    offer_date = date.today().strftime("%d %b %Y")
    location = _pdf_safe(
        (org.headquarters_address.split(",")[0].strip() if org and org.headquarters_address else "")
        or "Company base location"
    )

    try:
        logo_path, logo_is_temp = _resolve_logo_path(org)
        if logo_is_temp and logo_path:
            tmp_paths.append(logo_path)

        pdf = FPDF(unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=22)
        pdf.set_margins(18, 16, 18)

        # ---------- PAGE 1: Offer letter ----------
        pdf.add_page()
        _draw_header(pdf, org, logo_path)

        pdf.set_font("helvetica", "B", 16)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 9, "OFFER OF EMPLOYMENT", align="C", ln=1)
        pdf.ln(2)

        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(51, 65, 85)
        pdf.cell(0, 6, _pdf_safe(f"Date of Offer: {offer_date}"), ln=1)
        pdf.ln(2)
        pdf.set_font("helvetica", "B", 11)
        pdf.cell(0, 6, _pdf_safe(f"Dear {candidate},"), ln=1)
        pdf.ln(2)

        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(30, 41, 59)

        # Prefer structured opening; fall back to letter-template body paragraphs
        opening = (
            f"We are pleased to offer you the role of {designation}"
            + (f" in the {department} department" if department else "")
            + f" with {company}, as per the terms and conditions of this offer "
            f"letter and its accompanying annexures. You shall be employed as a "
            f"full-time member of {company}. We welcome you on board!"
        )
        pdf.multi_cell(0, 5.5, _pdf_safe(opening))
        pdf.ln(3)

        pdf.set_font("helvetica", "B", 10)
        pdf.cell(42, 6, "Role:", border=0)
        pdf.set_font("helvetica", "", 10)
        pdf.cell(0, 6, designation, ln=1)
        if department:
            pdf.set_font("helvetica", "B", 10)
            pdf.cell(42, 6, "Department:", border=0)
            pdf.set_font("helvetica", "", 10)
            pdf.cell(0, 6, department, ln=1)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(42, 6, "Date of Joining:", border=0)
        pdf.set_font("helvetica", "", 10)
        pdf.cell(0, 6, _pdf_safe(join), ln=1)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(42, 6, "Base Location:", border=0)
        pdf.set_font("helvetica", "", 10)
        pdf.cell(0, 6, location, ln=1)
        pdf.ln(3)

        if ctc_snapshot and ctc_snapshot.get("annual_ctc") is not None:
            annual = float(ctc_snapshot["annual_ctc"])
            ctc_para = (
                f"Your starting Cost To Company shall be {_annual_to_lacs(annual)} "
                f"per annum ({_fmt_inr(annual)}), which includes monthly salary, "
                f"allowances and other costs to company, along with statutory "
                f"contributions as applicable. A detailed break-up is set out in "
                f"Annexure A."
            )
            pdf.multi_cell(0, 5.5, _pdf_safe(ctc_para))
            pdf.ln(2)

        # Extra custom paragraphs from letter template (skip if too short/redundant)
        custom_paras = [p.strip() for p in body_text.split("\n") if p.strip()]
        # Skip generic short default lines already covered above
        skip_prefixes = (
            "dear ",
            "we are pleased to offer you the position",
            "your proposed joining date",
            "please review this offer",
            "welcome aboard",
            "department:",
        )
        added_custom = False
        for para in custom_paras:
            low = para.lower()
            if any(low.startswith(s) for s in skip_prefixes):
                continue
            if company.lower() in low and "hr" in low and len(para) < 40:
                continue
            pdf.multi_cell(0, 5.5, _pdf_safe(para))
            pdf.ln(1)
            added_custom = True
        if added_custom:
            pdf.ln(1)

        pdf.multi_cell(
            0,
            5.5,
            _pdf_safe(
                "Looking forward to working together with you. Please review this "
                "offer, complete preboarding formalities in the portal, and "
                "indicate your acceptance as described below."
            ),
        )
        pdf.ln(8)

        pdf.set_font("helvetica", "", 10)
        pdf.cell(0, 5, _pdf_safe(f"For {company}"), ln=1)
        pdf.ln(10)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(0, 5, "Authorized Signatory", ln=1)
        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(71, 85, 105)
        pdf.cell(0, 5, "HR / People Team", ln=1)
        _draw_footer_signature(pdf)

        # ---------- PAGE 2: Terms ----------
        pdf.add_page()
        _draw_header(pdf, org, logo_path)
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 7, "TERMS AND CONDITIONS", ln=1)
        pdf.ln(2)
        pdf.set_font("helvetica", "", 9.5)
        pdf.set_text_color(30, 41, 59)

        terms = [
            (
                "Base location & workplace. At any point in time, you will have a "
                f"company base location ({location}) considered for administrative "
                "and operational purposes. The Company reserves the right to require "
                "you to work from the office or a client location pursuant to "
                "business needs. Remote working, if permitted, is subject to "
                "company policy."
            ),
            (
                "Trainings & verifications. During your employment you may be "
                "required to undergo further trainings, assessments and "
                "verifications. Employment is subject to successful completion of "
                "such requirements and background verification."
            ),
            (
                "Acceptance. To accept this offer, please use the preboarding "
                "portal linked in your invite email (or upload a signed copy of "
                "this letter). Please also provide the documentation identified in "
                "Annexure B."
            ),
            (
                "Statutory disclosures. Where a government authority seeks "
                "information pertaining to your employment, the Company may "
                "provide such information as required by law without prior "
                "notification to you."
            ),
            (
                "Contingencies. This offer and your employment are contingent upon "
                "successful background verification and any role-specific checks "
                "the Company reasonably requires. If we do not receive your "
                "acceptance, or if after acceptance you do not join on the agreed "
                "date, this offer will be deemed rejected unless the Company "
                "communicates otherwise in writing."
            ),
            (
                "Taxes. All payments are subject to deduction of applicable taxes "
                "(TDS, professional tax, etc.). You remain solely liable for your "
                "personal tax obligations under applicable law."
            ),
        ]
        for block in terms:
            pdf.multi_cell(0, 5, _pdf_safe(block))
            pdf.ln(3)
        _draw_footer_signature(pdf)

        # ---------- Annexure A: CTC (when provided) ----------
        if ctc_snapshot and ctc_snapshot.get("annual_ctc") is not None:
            pdf.add_page()
            _draw_header(pdf, org, logo_path)
            pdf.set_font("helvetica", "B", 12)
            pdf.set_text_color(15, 23, 42)
            pdf.cell(0, 7, "ANNEXURE A", ln=1)
            pdf.set_font("helvetica", "B", 11)
            pdf.cell(0, 6, "CTC BREAK-UP (before statutory deductions)", ln=1)
            pdf.ln(2)

            pdf.set_font("helvetica", "", 10)
            pdf.set_text_color(30, 41, 59)
            pdf.multi_cell(
                0,
                5.5,
                _pdf_safe(
                    f"Annual CTC: {_fmt_inr(ctc_snapshot.get('annual_ctc'))}  |  "
                    f"Monthly CTC: {_fmt_inr(ctc_snapshot.get('monthly_ctc'))}"
                ),
            )
            pdf.ln(3)

            # Table header
            pdf.set_fill_color(236, 253, 245)
            pdf.set_font("helvetica", "B", 9)
            pdf.set_text_color(15, 23, 42)
            pdf.cell(78, 8, "Particulars", border=1, fill=True)
            pdf.cell(40, 8, "Monthly", border=1, fill=True, align="R")
            pdf.cell(48, 8, "Per annum", border=1, fill=True, align="R")
            pdf.ln()

            pdf.set_font("helvetica", "", 9)
            pdf.set_text_color(30, 41, 59)
            for row in ctc_snapshot.get("components") or []:
                name = _pdf_safe(str(row.get("name", "")))[:40]
                monthly = float(row.get("monthly") or 0)
                annual_amt = float(row.get("amount") or 0)
                pdf.cell(78, 7, name, border=1)
                pdf.cell(40, 7, _pdf_safe(f"{monthly:,.2f}"), border=1, align="R")
                pdf.cell(48, 7, _pdf_safe(f"{annual_amt:,.2f}"), border=1, align="R")
                pdf.ln()

            pdf.set_font("helvetica", "B", 9)
            pdf.set_fill_color(241, 245, 249)
            pdf.cell(78, 8, "TOTAL", border=1, fill=True)
            pdf.cell(
                40,
                8,
                _pdf_safe(f"{float(ctc_snapshot.get('monthly_ctc') or 0):,.2f}"),
                border=1,
                fill=True,
                align="R",
            )
            pdf.cell(
                48,
                8,
                _pdf_safe(f"{float(ctc_snapshot.get('annual_ctc') or 0):,.2f}"),
                border=1,
                fill=True,
                align="R",
            )
            pdf.ln(10)

            pdf.set_font("helvetica", "", 9)
            pdf.set_text_color(71, 85, 105)
            note = ctc_snapshot.get("note") or ""
            if note:
                pdf.multi_cell(0, 5, _pdf_safe(note))
            pdf.ln(2)
            pdf.multi_cell(
                0,
                5,
                _pdf_safe(
                    "Your annual compensation will be structured in line with "
                    "company policy. Variable components, if any, are subject to "
                    "applicable performance and eligibility criteria."
                ),
            )
            _draw_footer_signature(pdf)

        # ---------- Annexure B: Documents + acceptance ----------
        pdf.add_page()
        _draw_header(pdf, org, logo_path)
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 7, "ANNEXURE B", ln=1)
        pdf.set_font("helvetica", "B", 11)
        pdf.cell(0, 6, "DOCUMENTS & ACCEPTANCE", ln=1)
        pdf.ln(2)
        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(30, 41, 59)
        pdf.multi_cell(
            0,
            5.5,
            _pdf_safe(
                "Please upload / submit the following through the preboarding "
                "portal (or as otherwise directed by HR):"
            ),
        )
        pdf.ln(2)
        docs = [
            "Government photo ID proof",
            "PAN card",
            "Aadhaar (or equivalent address proof)",
            "Bank account proof (cancelled cheque / passbook)",
            "Educational certificates (as applicable)",
            "Signed copy of this offer letter (if wet-ink signature is required)",
        ]
        for d in docs:
            pdf.cell(0, 6, _pdf_safe(f"  - {d}"), ln=1)

        pdf.ln(6)
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(0, 6, "Declaration & acceptance", ln=1)
        pdf.set_font("helvetica", "", 9.5)
        pdf.multi_cell(
            0,
            5,
            _pdf_safe(
                "I hereby accept the terms of this Offer of Employment and its "
                "annexures. I confirm that I am free to accept this employment and "
                "will not bring confidential information or materials of any prior "
                "employer into the Company without authorization."
            ),
        )
        pdf.ln(10)
        pdf.set_font("helvetica", "", 10)
        pdf.cell(0, 6, "Signature: _______________________________", ln=1)
        pdf.ln(3)
        pdf.cell(0, 6, _pdf_safe(f"Name: {candidate}"), ln=1)
        pdf.ln(3)
        pdf.cell(0, 6, "Date: _______________________________", ln=1)
        pdf.ln(10)
        pdf.set_font("helvetica", "I", 8)
        pdf.set_text_color(100, 116, 139)
        pdf.multi_cell(
            0,
            4,
            _pdf_safe(
                f"This document is confidential and intended solely for {candidate} "
                f"({user.email}). Unauthorized use or disclosure is prohibited. "
                f"Generated via Teamzen Onboarding for {company}."
            ),
        )
        _draw_footer_signature(pdf)

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
