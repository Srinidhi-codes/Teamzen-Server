"""Distinct, conventional payslip layouts used by the Teamzen gallery."""

from decimal import Decimal

from fpdf import FPDF


def _amount(value):
    try:
        number = int(Decimal(str(value)).quantize(Decimal("1")))
    except Exception:
        return str(value)
    sign = "-" if number < 0 else ""
    digits = str(abs(number))
    if len(digits) <= 3:
        return sign + digits
    tail = digits[-3:]
    head = digits[:-3]
    pairs = []
    while head:
        pairs.append(head[-2:])
        head = head[:-2]
    return sign + ",".join(list(reversed(pairs)) + [tail])


def _rgb(value, fallback=(31, 41, 55)):
    value = (value or "").strip().lstrip("#")
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    except (TypeError, ValueError):
        return fallback


def _data(payslip):
    user = payslip.user
    earnings = list(payslip.components.filter(component_type="earning"))
    deductions = list(payslip.components.filter(component_type="deduction"))
    full_name = (
        user.get_full_name()
        if hasattr(user, "get_full_name")
        else f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}"
    ).strip()
    return {
        "org": payslip.payroll_run.organization.name,
        "period": f"{payslip.payroll_run.month:02d}/{payslip.payroll_run.year}",
        "name": full_name or user.email,
        "employee_id": user.employee_id or str(user.id),
        "department": payslip.department or "-",
        "designation": payslip.designation or "-",
        "pan": user.pan_number or "-",
        "bank": user.bank_account_number or "-",
        "worked": str(payslip.worked_days),
        "lop": str(payslip.lop_days),
        "earnings": earnings,
        "deductions": deductions,
        "gross": payslip.gross_earnings,
        "deduction_total": payslip.total_deductions,
        "net": payslip.net_pay,
    }


def _new_pdf():
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_margins(14, 14, 14)
    return pdf


def _footer(pdf):
    pdf.set_y(-15)
    pdf.set_font("helvetica", "", 7)
    pdf.set_text_color(113, 113, 122)
    pdf.cell(
        0,
        5,
        "Computer-generated payslip; no signature is required.",
        align="C",
    )


def _classic(payslip, theme):
    """Traditional Indian payslip: details grid and side-by-side pay tables."""
    d = _data(payslip)
    pdf = _new_pdf()
    accent = _rgb(theme.get("accent"), (15, 118, 110))

    pdf.set_font("helvetica", "B", 15)
    pdf.cell(0, 7, d["org"][:55], align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 6, f"SALARY SLIP FOR {d['period']}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*accent)
    pdf.set_line_width(0.6)
    pdf.line(14, pdf.get_y() + 1, 196, pdf.get_y() + 1)
    pdf.ln(5)

    details = [
        ("Employee name", d["name"], "Employee ID", d["employee_id"]),
        ("Designation", d["designation"], "Department", d["department"]),
        ("PAN", d["pan"], "Bank account", d["bank"]),
        ("Paid days", d["worked"], "LOP days", d["lop"]),
    ]
    for left_label, left, right_label, right in details:
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(82, 82, 91)
        pdf.cell(28, 7, left_label)
        pdf.set_font("helvetica", "B", 8)
        pdf.set_text_color(24, 24, 27)
        pdf.cell(63, 7, str(left)[:32])
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(82, 82, 91)
        pdf.cell(28, 7, right_label)
        pdf.set_font("helvetica", "B", 8)
        pdf.set_text_color(24, 24, 27)
        pdf.cell(63, 7, str(right)[:32], new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)
    x_left, x_right, table_w = 14, 107, 89
    for x, title in ((x_left, "EARNINGS"), (x_right, "DEDUCTIONS")):
        pdf.set_xy(x, pdf.get_y())
        pdf.set_fill_color(*accent)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("helvetica", "B", 8)
        pdf.cell(table_w, 7, title, fill=True)
    y = pdf.get_y() + 7
    rows = max(len(d["earnings"]), len(d["deductions"]), 1)
    for index in range(rows):
        for x, items in ((x_left, d["earnings"]), (x_right, d["deductions"])):
            item = items[index] if index < len(items) else None
            pdf.set_xy(x, y)
            pdf.set_text_color(39, 39, 42)
            pdf.set_font("helvetica", "", 8)
            pdf.cell(58, 7, item.component_name[:28] if item else "", border="B")
            pdf.cell(
                31,
                7,
                _amount(item.amount) if item else "",
                border="B",
                align="R",
            )
        y += 7

    pdf.set_xy(x_left, y + 1)
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(58, 8, "Gross earnings", fill=True)
    pdf.cell(31, 8, _amount(d["gross"]), align="R", fill=True)
    pdf.set_xy(x_right, y + 1)
    pdf.cell(58, 8, "Total deductions", fill=True)
    pdf.cell(31, 8, _amount(d["deduction_total"]), align="R", fill=True)
    pdf.set_xy(14, y + 13)
    pdf.set_fill_color(240, 253, 250)
    pdf.set_text_color(*accent)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(182, 13, f"NET PAY: INR {_amount(d['net'])}", align="R", fill=True)
    _footer(pdf)
    return bytes(pdf.output(dest="S"))


def _compact(payslip, theme):
    """Dense finance-register layout with a combined four-column table."""
    d = _data(payslip)
    pdf = _new_pdf()
    navy = _rgb(theme.get("table_header_bg"), (30, 58, 138))
    pdf.set_fill_color(*navy)
    pdf.rect(14, 12, 182, 21, "F")
    pdf.set_xy(18, 16)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 13)
    pdf.cell(105, 7, d["org"][:45])
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(69, 7, f"PAYSLIP {d['period']}", align="R")
    pdf.set_xy(18, 25)
    pdf.set_font("helvetica", "", 7)
    pdf.cell(174, 4, f"{d['name']}  |  {d['employee_id']}  |  {d['department']}  |  {d['designation']}")
    pdf.set_xy(14, 38)

    labels = [
        ("PAN", d["pan"]),
        ("Bank", d["bank"]),
        ("Paid days", d["worked"]),
        ("LOP", d["lop"]),
    ]
    for label, value in labels:
        pdf.set_font("helvetica", "B", 7)
        pdf.set_text_color(63, 63, 70)
        pdf.cell(20, 6, label)
        pdf.set_font("helvetica", "", 7)
        pdf.cell(25, 6, str(value)[:16])
    pdf.ln(9)

    widths = [59, 32, 59, 32]
    headers = ["Earning", "Amount", "Deduction", "Amount"]
    pdf.set_fill_color(*navy)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 8)
    for width, header in zip(widths, headers):
        pdf.cell(width, 7, header, fill=True, align="R" if header == "Amount" else "L")
    pdf.ln()
    rows = max(len(d["earnings"]), len(d["deductions"]), 1)
    pdf.set_text_color(39, 39, 42)
    pdf.set_font("helvetica", "", 8)
    for index in range(rows):
        earning = d["earnings"][index] if index < len(d["earnings"]) else None
        deduction = d["deductions"][index] if index < len(d["deductions"]) else None
        values = [
            earning.component_name[:28] if earning else "",
            _amount(earning.amount) if earning else "",
            deduction.component_name[:28] if deduction else "",
            _amount(deduction.amount) if deduction else "",
        ]
        for col, (width, value) in enumerate(zip(widths, values)):
            pdf.cell(width, 7, value, border="B", align="R" if col in (1, 3) else "L")
        pdf.ln()

    pdf.set_font("helvetica", "B", 8)
    for width, value, align in zip(
        widths,
        ["Gross", _amount(d["gross"]), "Deductions", _amount(d["deduction_total"])],
        ["L", "R", "L", "R"],
    ):
        pdf.cell(width, 8, value, fill=True, align=align)
    pdf.ln(12)
    pdf.set_fill_color(239, 246, 255)
    pdf.set_text_color(*navy)
    pdf.set_font("helvetica", "B", 13)
    pdf.cell(182, 14, f"NET PAY  INR {_amount(d['net'])}", fill=True, align="C")
    _footer(pdf)
    return bytes(pdf.output(dest="S"))


def _minimal(payslip, theme):
    """Formal monochrome format with no cards, color blocks, or hero panel."""
    d = _data(payslip)
    pdf = _new_pdf()
    pdf.set_text_color(24, 24, 27)
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(125, 7, d["org"][:48])
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(57, 7, "PAYSLIP", align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 8)
    pdf.cell(125, 5, f"{d['name']} ({d['employee_id']})")
    pdf.cell(57, 5, d["period"], align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(63, 63, 70)
    pdf.line(14, pdf.get_y() + 2, 196, pdf.get_y() + 2)
    pdf.ln(7)

    for label, value in [
        ("Department / designation", f"{d['department']} / {d['designation']}"),
        ("PAN / bank account", f"{d['pan']} / {d['bank']}"),
        ("Paid days / LOP", f"{d['worked']} / {d['lop']}"),
    ]:
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(82, 82, 91)
        pdf.cell(48, 7, label)
        pdf.set_font("helvetica", "B", 8)
        pdf.set_text_color(24, 24, 27)
        pdf.cell(134, 7, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    def section(title, items, total_label, total):
        pdf.set_font("helvetica", "B", 9)
        pdf.cell(0, 7, title, border="B", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 8)
        for item in items:
            pdf.cell(140, 7, item.component_name[:45], border="B")
            pdf.cell(42, 7, _amount(item.amount), border="B", align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "B", 8)
        pdf.cell(140, 8, total_label)
        pdf.cell(42, 8, _amount(total), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    section("EARNINGS", d["earnings"], "GROSS EARNINGS", d["gross"])
    section("DEDUCTIONS", d["deductions"], "TOTAL DEDUCTIONS", d["deduction_total"])
    pdf.set_draw_color(24, 24, 27)
    pdf.line(14, pdf.get_y(), 196, pdf.get_y())
    pdf.ln(4)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(140, 10, "NET PAY")
    pdf.cell(42, 10, f"INR {_amount(d['net'])}", align="R")
    _footer(pdf)
    return bytes(pdf.output(dest="S"))


def render_standard_payslip(payslip, layout_key, theme):
    if layout_key == "classic":
        return _classic(payslip, theme)
    if layout_key == "compact":
        return _compact(payslip, theme)
    if layout_key == "minimal":
        return _minimal(payslip, theme)
    raise ValueError(f"Unsupported standard payslip layout: {layout_key}")
