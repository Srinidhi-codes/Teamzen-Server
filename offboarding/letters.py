"""Exit letter generation (experience / relieving) — formal Clarivate-style layout."""
from __future__ import annotations

import logging
import os
import re
from datetime import date

from django.utils import timezone

from offboarding.models import ExitLetter

logger = logging.getLogger(__name__)


def merge_exit_letter_fields(offboarding, text: str) -> str:
    user = offboarding.user
    org = offboarding.organization
    join = user.date_of_joining
    exit_d = offboarding.exit_date or offboarding.last_working_day
    lwd = offboarding.last_working_day or offboarding.exit_date

    tenure = ""
    if join and exit_d:
        months = (exit_d.year - join.year) * 12 + (exit_d.month - join.month)
        years, rem = divmod(max(months, 0), 12)
        if years and rem:
            tenure = f"{years} year(s) {rem} month(s)"
        elif years:
            tenure = f"{years} year(s)"
        else:
            tenure = f"{max(rem, 1)} month(s)"

    mapping = {
        "employee_name": f"{user.first_name} {user.last_name}".strip() or user.email,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "email": user.email,
        "employee_id": getattr(user, "employee_id", None) or str(user.id),
        "designation": getattr(user.designation, "name", None) or "",
        "department": getattr(user.department, "name", None) or "",
        "company_name": org.name if org else "Company",
        "company_address": (org.headquarters_address if org else "") or "",
        "join_date": join.strftime("%B %d, %Y") if join else "",
        "exit_date": exit_d.strftime("%B %d, %Y") if exit_d else "",
        "last_working_day": lwd.strftime("%B %d, %Y") if lwd else "",
        "tenure": tenure,
        "employment_type": user.employment_type or "",
        "today": timezone.localdate().strftime("%B %d, %Y"),
    }
    mapping["employee"] = mapping["employee_name"]
    mapping["name"] = mapping["employee_name"]
    mapping["role"] = mapping["designation"]
    mapping["company"] = mapping["company_name"]
    mapping["joining_date"] = mapping["join_date"]
    mapping["relieving_date"] = mapping["last_working_day"] or mapping["exit_date"]

    result = text or ""
    for key, value in mapping.items():
        # Prefer {{token}}; also accept legacy single-brace {token} from bad f-string subjects.
        for pattern in (
            re.compile(r"\{\{\s*" + re.escape(key) + r"\s*\}\}", flags=re.IGNORECASE),
            re.compile(r"(?<!\{)\{\s*" + re.escape(key) + r"\s*\}(?!\})", flags=re.IGNORECASE),
        ):
            result = pattern.sub(str(value), result)
    return result


def _default_body(letter_type: str) -> str:
    # Kept for template merge / HTML storage; PDF uses structured renderer.
    if letter_type == "relieving":
        return (
            "<p>This is to certify that <strong>{{employee_name}}</strong> "
            "was employed in our organization from <strong>{{join_date}}</strong> "
            "to <strong>{{last_working_day}}</strong> as a "
            "<strong>{{designation}}</strong>.</p>"
            "<p>They have been relieved of their duties with effect from "
            "<strong>{{last_working_day}}</strong>.</p>"
            "<p>We wish him/her all the best in his/her future endeavors.</p>"
        )
    if letter_type == "experience":
        return (
            "<p>This is to certify that <strong>{{employee_name}}</strong> "
            "was employed in our organization from <strong>{{join_date}}</strong> "
            "to <strong>{{exit_date}}</strong> as a "
            "<strong>{{designation}}</strong>.</p>"
            "<p>We wish him/her all the best in his/her future endeavors.</p>"
        )
    return (
        "<p>Salary certificate for {{employee_name}} ({{designation}}) "
        "at {{company_name}}.</p>"
    )


def _format_long_date(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return value.strftime("%B %d, %Y")


def _signatory(actor, organization):
    """Resolve signatory name/title for the letter footer block."""
    if actor:
        name = f"{actor.first_name} {actor.last_name}".strip() or actor.email
        title = getattr(getattr(actor, "designation", None), "name", None) or "HR"
        return name, title
    return "Human Resources", (organization.name if organization else "Company")


def render_experience_style_pdf(
    offboarding,
    *,
    letter_type: str = "experience",
    actor=None,
) -> bytes:
    """
    Clarivate-style formal letter:
    logo + date header, centered underlined title, emp details,
    certification paragraph with bold fields, closing wish, signatory, footer.
    """
    from fpdf import FPDF
    from onboarding.offer_pdf import _pdf_safe, _resolve_logo_path

    user = offboarding.user
    org = offboarding.organization
    join = user.date_of_joining
    exit_d = offboarding.exit_date or offboarding.last_working_day
    lwd = offboarding.last_working_day or offboarding.exit_date
    end_date = lwd if letter_type == "relieving" else (exit_d or lwd)

    employee_name = _pdf_safe(
        f"{user.first_name} {user.last_name}".strip() or user.email
    )
    emp_code = _pdf_safe(getattr(user, "employee_id", None) or str(user.id))
    designation = _pdf_safe(
        getattr(getattr(user, "designation", None), "name", None) or "Employee"
    )
    company = _pdf_safe(org.name if org else "Company")
    company_address = _pdf_safe((org.headquarters_address if org else "") or "")
    letter_date = _pdf_safe(timezone.localdate().strftime("%B %d, %Y"))
    join_s = _pdf_safe(_format_long_date(join) or "—")
    end_s = _pdf_safe(_format_long_date(end_date) or "—")
    signatory_name, signatory_title = _signatory(actor, org)
    signatory_name = _pdf_safe(signatory_name)
    signatory_title = _pdf_safe(signatory_title)

    if letter_type == "relieving":
        title = "Relieving Letter"
    elif letter_type == "salary_certificate":
        title = "Salary Certificate"
    else:
        title = "Experience Letter"

    tmp_paths: list[str] = []
    logo_path, logo_is_temp = _resolve_logo_path(org)
    if logo_is_temp and logo_path:
        tmp_paths.append(logo_path)

    class LetterPDF(FPDF):
        def footer(self):
            self.set_y(-18)
            self.set_draw_color(200, 200, 200)
            self.set_line_width(0.2)
            self.line(18, self.get_y(), 192, self.get_y())
            self.ln(2)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(120, 120, 120)
            left = company
            if company_address:
                # First line of address only for compactness
                first_line = company_address.split("\n")[0][:70]
                left = f"{company}  |  {first_line}"
            self.set_x(18)
            self.cell(110, 4, left[:95], align="L")
            self.cell(64, 4, "", align="R")  # contact placeholder if needed

    try:
        pdf = LetterPDF(unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=22)
        pdf.add_page()
        pdf.set_margins(18, 18, 18)

        # —— Header: logo left, date right ——
        header_y = 16
        if logo_path:
            try:
                pdf.image(logo_path, x=18, y=header_y, h=12)
            except Exception:
                logger.exception("Failed to place org logo on experience letter")
                pdf.set_xy(18, header_y)
                pdf.set_font("Helvetica", "B", 14)
                pdf.set_text_color(20, 20, 20)
                pdf.cell(80, 8, company[:40], align="L")
        else:
            pdf.set_xy(18, header_y)
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(20, 20, 20)
            pdf.cell(80, 8, company[:40], align="L")

        pdf.set_xy(120, header_y + 2)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(72, 6, letter_date, align="R")

        # —— Centered underlined title ——
        pdf.set_y(40)
        pdf.set_font("Helvetica", "BU", 14)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 8, title, align="C", ln=1)

        # —— Employee block ——
        pdf.ln(10)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_x(18)
        pdf.cell(0, 6, employee_name, ln=1)
        pdf.set_x(18)
        pdf.cell(0, 6, f"Emp Code: {emp_code}", ln=1)

        # —— Certification body (mixed bold via write) ——
        pdf.ln(8)
        pdf.set_x(18)
        pdf.set_font("Helvetica", "", 11)
        pdf.write(6, "This is to certify that ")
        pdf.set_font("Helvetica", "B", 11)
        pdf.write(6, employee_name)
        pdf.set_font("Helvetica", "", 11)
        pdf.write(6, " was employed in our organization from ")
        pdf.set_font("Helvetica", "B", 11)
        pdf.write(6, join_s)
        pdf.set_font("Helvetica", "", 11)
        pdf.write(6, " to ")
        pdf.set_font("Helvetica", "B", 11)
        pdf.write(6, end_s)
        pdf.set_font("Helvetica", "", 11)
        pdf.write(6, " as a ")
        pdf.set_font("Helvetica", "B", 11)
        pdf.write(6, f"{designation}.")
        pdf.ln(10)

        if letter_type == "relieving":
            pdf.set_x(18)
            pdf.set_font("Helvetica", "", 11)
            pdf.write(6, "They have been relieved of their duties with effect from ")
            pdf.set_font("Helvetica", "B", 11)
            pdf.write(6, end_s)
            pdf.set_font("Helvetica", "", 11)
            pdf.write(6, ".")
            pdf.ln(10)

        pdf.set_x(18)
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(
            0,
            6,
            "We wish him/her all the best in his/her future endeavors.",
        )

        # —— Signatory ——
        pdf.ln(14)
        pdf.set_x(18)
        pdf.set_font("Helvetica", "", 11)
        pdf.write(6, "For ")
        pdf.set_font("Helvetica", "B", 11)
        pdf.write(6, company)
        pdf.ln(16)

        # Signature space (blank line for wet ink / digital later)
        pdf.set_x(18)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 5, "[Authorized Signatory]", ln=1)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)

        pdf.set_x(18)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 6, signatory_name, ln=1)
        pdf.set_x(18)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, signatory_title, ln=1)

        out = pdf.output(dest="S")
        if isinstance(out, (bytes, bytearray)):
            data = bytes(out)
        else:
            data = str(out).encode("latin-1", "replace")
        if data[:4] != b"%PDF":
            raise ValueError("Invalid PDF output")
        return data
    finally:
        for path in tmp_paths:
            try:
                if path and os.path.isfile(path):
                    os.unlink(path)
            except Exception:
                pass


def upload_exit_letter_pdf(
    offboarding, file_bytes: bytes, *, letter_type: str, filename: str
) -> str:
    """Upload PDF to Cloudinary raw storage (same pattern as offer letters)."""
    import cloudinary.uploader
    import io

    buf = io.BytesIO(file_bytes)
    buf.seek(0)
    result = cloudinary.uploader.upload(
        buf,
        resource_type="raw",
        folder=f"exit_letters/{offboarding.organization_id}/{offboarding.user_id}",
        public_id=f"{letter_type}_{offboarding.id}",
        overwrite=True,
        format="pdf",
        filename_override=filename,
    )
    return result.get("secure_url") or result.get("url") or ""


def generate_exit_letter(
    offboarding,
    *,
    letter_type: str,
    actor=None,
    letter_template_id=None,
    publish_to_vault: bool = True,
) -> ExitLetter:
    from onboarding.models import DocumentLetterTemplate
    from documents.services import publish_issued_document

    if letter_type not in ("experience", "relieving", "salary_certificate"):
        raise ValueError("Invalid letter_type")

    tpl = None
    if letter_template_id:
        tpl = DocumentLetterTemplate.objects.filter(
            id=letter_template_id, organization=offboarding.organization
        ).first()
    if not tpl:
        tpl = (
            DocumentLetterTemplate.objects.filter(
                organization=offboarding.organization,
                letter_type=letter_type,
                is_default=True,
            ).first()
            or DocumentLetterTemplate.objects.filter(
                organization=offboarding.organization, letter_type=letter_type
            ).first()
        )

    if tpl:
        subject = merge_exit_letter_fields(
            offboarding, tpl.subject or letter_type.replace("_", " ").title()
        )
        body = merge_exit_letter_fields(offboarding, tpl.body_html)
    else:
        # Do not use an f-string here: `{{employee_name}}` would collapse to
        # `{employee_name}` and skip merge (regex expects double braces).
        subject = merge_exit_letter_fields(
            offboarding,
            letter_type.replace("_", " ").title() + " - {{employee_name}}",
        )
        body = merge_exit_letter_fields(offboarding, _default_body(letter_type))

    # Structured Clarivate-style PDF for experience / relieving;
    # salary_certificate still uses the same formal layout with its title.
    pdf_bytes = render_experience_style_pdf(
        offboarding, letter_type=letter_type, actor=actor
    )
    filename = f"{letter_type}_{offboarding.user_id}.pdf"
    pdf_url = upload_exit_letter_pdf(
        offboarding, pdf_bytes, letter_type=letter_type, filename=filename
    )
    if not pdf_url:
        raise ValueError("Cloudinary upload returned no URL for exit letter PDF")

    letter, _ = ExitLetter.objects.update_or_create(
        offboarding=offboarding,
        letter_type=letter_type,
        defaults={
            "letter_template": tpl,
            "subject": subject,
            "body_html": body,
            "pdf_url": pdf_url,
            "status": "issued",
            "created_by": actor,
            "issued_at": timezone.now(),
        },
    )

    if publish_to_vault:
        category = (
            "relieving"
            if letter_type == "relieving"
            else ("experience" if letter_type == "experience" else "salary_certificate")
        )
        issued = publish_issued_document(
            actor=actor,
            user=offboarding.user,
            organization=offboarding.organization,
            title=subject[:255],
            category=category,
            file_url=pdf_url,
            file_name=filename,
            notes=f"Auto-issued from offboarding #{offboarding.id}",
            notify=True,
        )
        letter.issued_document = issued
        letter.pdf_url = pdf_url
        letter.save(update_fields=["issued_document", "pdf_url", "updated_at"])

    return letter
