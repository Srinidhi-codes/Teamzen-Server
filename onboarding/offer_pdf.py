"""Offer letter PDF generation via FPDF (same stack as payslips)."""

from __future__ import annotations

import logging
import re
from html import unescape
from io import BytesIO

logger = logging.getLogger(__name__)


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def render_offer_pdf_url(onboarding, subject: str, body_html: str) -> str:
    """
    Render a simple offer PDF and upload to Cloudinary.
    Returns the secure URL or empty string on failure.
    """
    from fpdf import FPDF
    import cloudinary.uploader

    user = onboarding.user
    org = onboarding.organization
    body_text = _strip_html(body_html)

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(18, 18, 18)

    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(33, 37, 41)
    pdf.multi_cell(0, 8, (org.name if org else "Offer Letter")[:80])

    pdf.ln(4)
    pdf.set_font("helvetica", "B", 12)
    pdf.multi_cell(0, 7, (subject or "Offer of Employment")[:120])

    pdf.ln(6)
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(55, 65, 81)
    for para in body_text.split("\n"):
        line = para.strip()
        if not line:
            pdf.ln(3)
            continue
        pdf.multi_cell(0, 6, line)
        pdf.ln(1)

    pdf.ln(10)
    pdf.set_font("helvetica", "I", 9)
    pdf.set_text_color(108, 117, 125)
    pdf.multi_cell(
        0,
        5,
        f"Generated for {user.email} · Teamzen Onboarding",
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
