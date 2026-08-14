"""
Clean corporate Indian payslip layout (Eazy ERP–style structure).

Drawn from scratch with FPDF so each employee gets correct data + org branding.
Matches the common uploaded structure: centered period title, employee name,
two-column info, paid attendance, side-by-side earnings/deductions, footer.
"""

from __future__ import annotations

import calendar
import io
import os
from decimal import Decimal


def _fmt_money(amount) -> str:
    try:
        n = Decimal(str(amount)).quantize(Decimal("0.01"))
    except Exception:
        return str(amount)
    # Indian-style grouping for whole part
    neg = n < 0
    n = abs(n)
    whole = int(n)
    frac = int((n - whole) * 100)
    s = str(whole)
    if len(s) <= 3:
        grouped = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        parts = []
        while rest:
            parts.append(rest[-2:])
            rest = rest[:-2]
        grouped = ",".join(list(reversed(parts)) + [last3])
    out = f"{grouped}.{frac:02d}"
    return f"-{out}" if neg else out


def _fmt_doj(d) -> str:
    if not d:
        return "-"
    if hasattr(d, "strftime"):
        return d.strftime("%d %B %Y")
    return str(d)


def _safe(text: str) -> str:
    s = str(text or "")
    # fpdf latin-1 safety
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _attr_name(obj, *attrs) -> str:
    for a in attrs:
        v = getattr(obj, a, None)
        if v is None:
            continue
        if hasattr(v, "name") and getattr(v, "name", None):
            return str(v.name)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def render_corporate_style_payslip(payslip) -> bytes:
    """
    Draw a clean payslip matching the uploaded corporate/Eazy structure.
    """
    from fpdf import FPDF

    org = payslip.payroll_run.organization
    user = payslip.user
    month = payslip.payroll_run.month
    year = payslip.payroll_run.year
    month_abbr = calendar.month_abbr[month]
    period = f"{month_abbr}-{year}"

    name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    if not name:
        name = getattr(user, "email", None) or "-"

    designation = payslip.designation or _attr_name(user, "designation") or "-"
    department = payslip.department or _attr_name(user, "department") or "-"
    emp_id = getattr(user, "employee_id", None) or str(getattr(user, "id", "-"))
    doj = _fmt_doj(getattr(user, "date_of_joining", None))
    pan = getattr(user, "pan_number", None) or "-"
    uan = getattr(user, "uan_number", None) or "-"
    bank = getattr(user, "bank_ifsc_code", None) or ""
    # Prefer short bank label if account exists
    if getattr(user, "bank_account_number", None):
        bank = bank or "Bank"
    else:
        bank = bank or "-"

    location = "-"
    loc = getattr(user, "office_location", None)
    if loc is not None:
        location = (
            getattr(loc, "name", None)
            or getattr(loc, "city", None)
            or "-"
        )

    earnings = list(payslip.components.filter(component_type="earning"))
    deductions = list(payslip.components.filter(component_type="deduction"))

    paid_days = payslip.worked_days
    try:
        paid_disp = f"{int(Decimal(str(paid_days)))} Days"
    except Exception:
        paid_disp = f"{paid_days} Days"

    company = getattr(org, "name", None) or "Company"
    address = (getattr(org, "headquarters_address", None) or "").strip()
    cin = (getattr(org, "registration_number", None) or "").strip()

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    page_w = 210.0
    margin = 14.0
    content_w = page_w - 2 * margin

    tmp_logo = None
    try:
        from payroll.services import _resolve_logo_path

        logo_path, is_temp = _resolve_logo_path(org)
        if logo_path:
            pdf.image(logo_path, x=page_w - margin - 32, y=10, h=18)
            if is_temp:
                tmp_logo = logo_path
    except Exception:
        pass

    # Soft geometric header accent (left)
    pdf.set_draw_color(200, 210, 220)
    pdf.set_line_width(0.2)
    for i in range(6):
        x0 = margin + i * 6
        pdf.line(x0, 12, x0 + 10, 28)
        pdf.line(x0 + 4, 12, x0 + 14, 28)

    # Title
    pdf.set_xy(margin, 32)
    pdf.set_font("helvetica", "B", 13)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(content_w, 7, _safe(f"Pay Slip for month of {period}"), align="C")

    # Employee name
    pdf.set_xy(margin, 40)
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(content_w, 9, _safe(name), align="C")

    # Info grid
    y = 54
    left_col = [
        ("Employee number", str(emp_id)),
        ("Function", department),
        ("Designation", designation),
        ("Location", location),
        ("Bank Details", bank),
        ("Date Of Joining", doj),
        ("PAN No", pan),
    ]
    right_col = [
        ("UAN Number", uan),
    ]

    col_w = content_w / 2
    label_w = 38
    pdf.set_font("helvetica", "", 9)
    row_h = 6.2

    def _info_row(x, yy, label, value):
        pdf.set_xy(x, yy)
        pdf.set_text_color(70, 70, 70)
        pdf.set_font("helvetica", "", 9)
        pdf.cell(label_w, row_h, _safe(f"{label}:"), align="L")
        pdf.set_text_color(20, 20, 20)
        pdf.set_font("helvetica", "B", 9)
        pdf.cell(col_w - label_w - 2, row_h, _safe(str(value)[:42]), align="L")

    for i, (lab, val) in enumerate(left_col):
        _info_row(margin, y + i * row_h, lab, val)
    for i, (lab, val) in enumerate(right_col):
        _info_row(margin + col_w, y + i * row_h, lab, val)

    y = y + len(left_col) * row_h + 6

    # Paid attendance box
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(180, 190, 200)
    pdf.rect(margin, y, 70, 14, style="D")
    pdf.set_xy(margin + 2, y + 1)
    pdf.set_font("helvetica", "B", 9)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(66, 5, "Paid Attendance", align="L")
    pdf.set_xy(margin + 2, y + 7)
    pdf.set_font("helvetica", "", 10)
    pdf.cell(66, 5, _safe(paid_disp), align="L")

    y += 20

    # Earnings | Deductions tables
    table_gap = 6
    tw = (content_w - table_gap) / 2
    left_x = margin
    right_x = margin + tw + table_gap

    def _draw_table(x, yy, title, rows, total_label, total_value, extra_rows=None):
        pdf.set_fill_color(235, 240, 245)
        pdf.set_draw_color(160, 170, 180)
        pdf.set_xy(x, yy)
        pdf.set_font("helvetica", "B", 9)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(tw * 0.62, 7, _safe(title), border=1, fill=True, align="C")
        pdf.cell(tw * 0.38, 7, "Amount", border=1, fill=True, align="C")
        cy = yy + 7
        pdf.set_font("helvetica", "", 9)
        max_rows = 10
        display = list(rows)[:max_rows]
        # Pad empty structural rows for visual similarity
        pad_names = extra_rows or []
        existing = {
            str(getattr(r, "component_name", "") or "").strip().lower()
            for r in display
        }
        for pname in pad_names:
            if len(display) >= max_rows:
                break
            key = pname.strip().lower()
            if key in existing or any(key in e or e in key for e in existing if e):
                continue
            display.append(
                type("R", (), {"component_name": pname, "amount": Decimal("0")})()
            )
            existing.add(key)

        for r in display:
            cname = getattr(r, "component_name", "")
            amt = getattr(r, "amount", 0)
            show_amt = _fmt_money(amt) if Decimal(str(amt or 0)) != 0 else ""
            pdf.set_xy(x, cy)
            pdf.set_text_color(30, 30, 30)
            pdf.cell(tw * 0.62, 6.2, _safe(str(cname)[:28]), border=1, align="L")
            pdf.cell(tw * 0.38, 6.2, _safe(show_amt), border=1, align="R")
            cy += 6.2

        # Totals
        pdf.set_fill_color(245, 248, 250)
        pdf.set_xy(x, cy)
        pdf.set_font("helvetica", "B", 9)
        pdf.cell(tw * 0.62, 7, _safe(total_label), border=1, fill=True, align="L")
        pdf.cell(tw * 0.38, 7, _safe(_fmt_money(total_value)), border=1, fill=True, align="R")
        return cy + 7

    earn_pad = [
        "Conveyance",
        "Special Allowance",
        "Bonus",
        "MedicalInsurance",
        "EmployerPF",
        "EmployerESI",
    ]
    ded_pad = [
        "TDS",
        "MedicalInsurance",
        "NATS",
        "PF",
        "ESI",
        "EmployerPF",
        "EmployerESI",
    ]

    end_l = _draw_table(
        left_x,
        y,
        "Earning",
        earnings,
        "Total Amount",
        payslip.gross_earnings,
        extra_rows=earn_pad,
    )
    end_r = _draw_table(
        right_x,
        y,
        "Deductions",
        deductions,
        "Total Deduction",
        payslip.total_deductions,
        extra_rows=ded_pad,
    )

    # Net pay under deductions table
    net_y = max(end_l, end_r) + 2
    pdf.set_xy(right_x, net_y)
    pdf.set_font("helvetica", "B", 10)
    pdf.set_fill_color(230, 240, 255)
    pdf.set_draw_color(120, 140, 180)
    pdf.cell(tw * 0.62, 8, "Net Pay", border=1, fill=True, align="L")
    pdf.cell(tw * 0.38, 8, _safe(_fmt_money(payslip.net_pay)), border=1, fill=True, align="R")

    # Footer
    foot_y = 250
    pdf.set_xy(margin, foot_y)
    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(
        content_w,
        5,
        "*This is computer generated salary slip, not valid unless signed by authorized signatory",
        align="L",
    )

    pdf.set_draw_color(180, 180, 180)
    pdf.line(margin, foot_y + 8, page_w - margin, foot_y + 8)

    pdf.set_xy(margin, foot_y + 11)
    pdf.set_font("helvetica", "B", 9)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(content_w * 0.55, 5, _safe(company[:48]), align="L")
    if cin:
        pdf.set_xy(margin + content_w * 0.55, foot_y + 11)
        pdf.set_font("helvetica", "", 8)
        pdf.cell(content_w * 0.45, 5, _safe(f"CIN No: {cin}"[:42]), align="R")

    if address:
        pdf.set_xy(margin, foot_y + 18)
        pdf.set_font("helvetica", "", 7)
        pdf.set_text_color(70, 70, 70)
        pdf.multi_cell(content_w, 3.8, _safe(address[:220]), align="L")

    out = pdf.output(dest="S")
    if tmp_logo:
        try:
            os.unlink(tmp_logo)
        except OSError:
            pass
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)
