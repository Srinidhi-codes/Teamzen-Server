"""
Clean pixel-faithful Networth-style payslip layout (drawn from scratch).

Used when an org uploads a Networth-like payslip PDF — we do NOT patch the
uploaded PDF (that caused overlapping text). We recreate the same visual
structure with FPDF so every slip is crisp.
"""

from __future__ import annotations

import calendar
import io
import os
import tempfile
from decimal import Decimal


def _fmt_money(amount) -> str:
    try:
        n = Decimal(str(amount)).quantize(Decimal("0.01"))
    except Exception:
        return str(amount)
    return f"{n:,.2f}"


def _fmt_date_long(d) -> str:
    if not d:
        return "-"
    if hasattr(d, "strftime"):
        # 16th January 2025 style
        day = d.day
        suffix = "th"
        if day % 10 == 1 and day % 100 != 11:
            suffix = "st"
        elif day % 10 == 2 and day % 100 != 12:
            suffix = "nd"
        elif day % 10 == 3 and day % 100 != 13:
            suffix = "rd"
        return f"{day}{suffix} {d.strftime('%B %Y')}"
    return str(d)


def amount_in_words_inr(amount) -> str:
    """Indian-style amount in words for payslip footer."""
    try:
        n = int(Decimal(str(amount)).quantize(Decimal("1")))
        paise = int((Decimal(str(amount)).quantize(Decimal("0.01")) % 1) * 100)
    except Exception:
        return ""

    ones = [
        "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
        "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
        "Seventeen", "Eighteen", "Nineteen",
    ]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def two_digits(x: int) -> str:
        if x < 20:
            return ones[x]
        return (tens[x // 10] + (" " + ones[x % 10] if x % 10 else "")).strip()

    def three_digits(x: int) -> str:
        h = x // 100
        r = x % 100
        parts = []
        if h:
            parts.append(ones[h] + " Hundred")
        if r:
            parts.append(two_digits(r))
        return " ".join(parts)

    if n == 0 and paise == 0:
        words = "Zero"
    else:
        crore = n // 10000000
        n %= 10000000
        lakh = n // 100000
        n %= 100000
        thousand = n // 1000
        n %= 1000
        rest = n
        parts = []
        if crore:
            parts.append(three_digits(crore) + " Crore")
        if lakh:
            parts.append(three_digits(lakh) + " Lakh")
        if thousand:
            parts.append(three_digits(thousand) + " Thousand")
        if rest:
            parts.append(three_digits(rest))
        words = " ".join(parts) if parts else "Zero"

    if paise:
        words = f"{words} Point {two_digits(paise)}"
    return f"Rupees {words} only"


def _safe_text(text: str) -> str:
    """Helvetica core fonts are latin-1 only — strip unsupported glyphs."""
    if text is None:
        return ""
    s = str(text)
    replacements = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u20b9": "Rs.",
        "\u00a0": " ",
    }
    for a, b in replacements.items():
        s = s.replace(a, b)
    return s.encode("latin-1", errors="replace").decode("latin-1")


def render_networth_style_payslip(payslip) -> bytes:
    """
    Draw a clean Networth Corp–style payslip matching the uploaded sample layout.
    Returns PDF bytes.
    """
    from fpdf import FPDF

    org = payslip.payroll_run.organization
    user = payslip.user
    month = payslip.payroll_run.month
    year = payslip.payroll_run.year
    month_name = calendar.month_name[month]
    period = f"{month_name} {year}"

    name = f"{user.first_name} {user.last_name}".strip() or (user.email or "-")
    designation = payslip.designation or "-"
    department = payslip.department or ""
    doj = _fmt_date_long(getattr(user, "date_of_joining", None))
    pan = getattr(user, "pan_number", None) or "-"
    account = getattr(user, "bank_account_number", None) or "-"
    ifsc = getattr(user, "bank_ifsc_code", None) or ""
    location = "-"
    loc = getattr(user, "office_location", None)
    if loc is not None:
        location = (
            getattr(loc, "city", None)
            or getattr(loc, "name", None)
            or "-"
        )

    earnings = list(payslip.components.filter(component_type="earning"))
    deductions = list(payslip.components.filter(component_type="deduction"))

    worked = payslip.worked_days
    lop = payslip.lop_days
    # Approximate days in month for display
    import calendar as cal

    days_in_month = cal.monthrange(year, month)[1]

    company = org.name or "Company"
    # Prefer a short brand if name is long legal name
    brand = company
    website = getattr(org, "website", None) or ""
    legal = company

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    page_w, page_h = 210.0, 297.0
    # Margins inside decorative bars
    left_bar = 6.0
    right_bar = 8.0
    content_x = left_bar + 8.0
    content_w = page_w - left_bar - right_bar - 16.0

    # ── Left black bar ──
    pdf.set_fill_color(20, 20, 20)
    pdf.rect(0, 0, left_bar, 42, "F")

    # ── Right multicolor bar (maroon / blue / yellow / green) ──
    colors = [
        (128, 0, 32),    # maroon
        (30, 64, 175),   # blue
        (202, 138, 4),   # yellow/gold
        (22, 101, 52),   # green
    ]
    seg_h = page_h / 4
    for i, rgb in enumerate(colors):
        pdf.set_fill_color(*rgb)
        pdf.rect(page_w - right_bar, i * seg_h, right_bar, seg_h + 0.5, "F")

    # ── Org logo (top-right of header) ──
    logo_tmp = None
    try:
        from payroll.services import _resolve_logo_path

        logo_path, logo_is_temp = _resolve_logo_path(org)
        if logo_path:
            pdf.image(logo_path, x=page_w - right_bar - 28, y=10, h=16)
            if logo_is_temp:
                logo_tmp = logo_path
    except Exception:
        pass

    # ── Company name ──
    pdf.set_xy(content_x, 14)
    pdf.set_font("helvetica", "B", 22)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(content_w * 0.75, 10, _safe_text(brand[:40]), align="L")

    # ── Period title ──
    pdf.set_xy(content_x, 28)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(content_w, 7, _safe_text(f"Payslip for the month of {period}"), align="C")

    # ── Employee info grid (2 columns) ──
    y = 42
    left_info = [
        ("Name", name),
        ("Designation", designation),
        ("Skill Badges", department or "-"),
        ("Date of Joining", doj),
        ("Location", location),
        ("PAN", pan),
    ]
    right_info = [
        ("Bank Name", "-"),
        ("A/C No", account),
        ("Days in Month", str(days_in_month)),
        ("LOP", f"{float(lop):02.0f}" if float(lop) < 100 else str(lop)),
        ("Effective days", str(worked).rstrip("0").rstrip(".") if "." in str(worked) else str(worked)),
    ]
    # Pad LOP as 00 style when zero
    if float(lop) == 0:
        right_info[3] = ("LOP", "00")

    col_w = content_w / 2
    row_h = 6.2
    label_w = 38
    pdf.set_font("helvetica", "", 9)
    for i in range(max(len(left_info), len(right_info))):
        cy = y + i * row_h
        if i < len(left_info):
            label, val = left_info[i]
            pdf.set_xy(content_x, cy)
            pdf.set_font("helvetica", "", 9)
            pdf.set_text_color(60, 60, 60)
            pdf.cell(label_w, row_h, f"{label}:", align="L")
            pdf.set_font("helvetica", "B", 9)
            pdf.set_text_color(20, 20, 20)
            pdf.cell(col_w - label_w - 4, row_h, _safe_text(str(val)[:42]), align="L")
        if i < len(right_info):
            label, val = right_info[i]
            rx = content_x + col_w + 2
            pdf.set_xy(rx, cy)
            pdf.set_font("helvetica", "", 9)
            pdf.set_text_color(60, 60, 60)
            pdf.cell(label_w, row_h, f"{label}:", align="L")
            pdf.set_font("helvetica", "B", 9)
            pdf.set_text_color(20, 20, 20)
            pdf.cell(col_w - label_w - 4, row_h, _safe_text(str(val)[:42]), align="L")

    # ── Earnings / Deductions table ──
    table_top = y + max(len(left_info), len(right_info)) * row_h + 6
    table_x = content_x
    table_w = content_w
    # Column widths: Earnings name | Full | Actual | Deductions name | Actual
    # Mirror sample: left 3 cols, right 2 cols
    w_en = table_w * 0.28
    w_ef = table_w * 0.12
    w_ea = table_w * 0.12
    w_dn = table_w * 0.30
    w_da = table_w * 0.18

    header_h = 7
    pdf.set_draw_color(30, 30, 30)
    pdf.set_line_width(0.35)

    # Outer border start — we'll close after rows
    max_rows = max(len(earnings), len(deductions), 1)
    # Ensure at least room for typical Networth rows
    row_th = 6.0
    body_h = header_h + max_rows * row_th + 8  # + totals line

    # Header row
    pdf.set_fill_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 9)
    pdf.set_text_color(20, 20, 20)
    x = table_x
    pdf.set_xy(x, table_top)
    for text, w in (
        ("Earnings", w_en),
        ("Full", w_ef),
        ("Actual", w_ea),
        ("Deductions", w_dn),
        ("Actual", w_da),
    ):
        pdf.cell(w, header_h, text, border=1, align="C")

    # Body rows
    pdf.set_font("helvetica", "", 8)
    for i in range(max_rows):
        cy = table_top + header_h + i * row_th
        pdf.set_xy(table_x, cy)
        # Earnings cells
        if i < len(earnings):
            e = earnings[i]
            amt = _fmt_money(e.amount)
            pdf.cell(w_en, row_th, _safe_text(str(e.component_name)[:32]), border=1, align="L")
            pdf.cell(w_ef, row_th, amt, border=1, align="R")
            pdf.cell(w_ea, row_th, amt, border=1, align="R")
        else:
            pdf.cell(w_en, row_th, "", border=1)
            pdf.cell(w_ef, row_th, "", border=1)
            pdf.cell(w_ea, row_th, "", border=1)
        # Deductions cells
        if i < len(deductions):
            d = deductions[i]
            amt = _fmt_money(d.amount)
            pdf.cell(w_dn, row_th, _safe_text(str(d.component_name)[:32]), border=1, align="L")
            pdf.cell(w_da, row_th, amt, border=1, align="R")
        else:
            pdf.cell(w_dn, row_th, "", border=1)
            pdf.cell(w_da, row_th, "", border=1)

    # Totals row
    totals_y = table_top + header_h + max_rows * row_th
    pdf.set_xy(table_x, totals_y)
    pdf.set_font("helvetica", "B", 8)
    gross = _fmt_money(payslip.gross_earnings)
    tded = _fmt_money(payslip.total_deductions)
    pdf.cell(w_en + w_ef, row_th, _safe_text(f"Total Earnings: Rs. {gross}"), border=1, align="L")
    pdf.cell(w_ea, row_th, "", border=1)
    pdf.cell(w_dn, row_th, _safe_text(f"Total Deductions: Rs. {tded}"), border=1, align="L")
    pdf.cell(w_da, row_th, "", border=1)

    # Net pay line inside bordered area
    net_y = totals_y + row_th
    pdf.set_xy(table_x, net_y)
    pdf.set_font("helvetica", "B", 9)
    net = _fmt_money(payslip.net_pay)
    pdf.cell(
        table_w,
        8,
        _safe_text(f"Net Pay for the month (Total Earnings - Total Deductions): {net}"),
        border=1,
        align="L",
    )

    # Amount in words
    words_y = net_y + 10
    words = amount_in_words_inr(payslip.net_pay)
    pdf.set_xy(table_x, words_y)
    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(table_w, 4.5, _safe_text(f"({words})"), align="L")

    # Disclaimer
    pdf.set_xy(content_x, 255)
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(
        content_w,
        5,
        "This is a system generated pay slip and does not require signature.",
        align="C",
    )

    # Footer brand / website
    pdf.set_xy(content_x, 275)
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(content_w * 0.45, 5, "", align="L")  # logo space
    pdf.set_xy(content_x + content_w * 0.45, 272)
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(30, 30, 30)
    if website:
        pdf.cell(content_w * 0.55, 4, _safe_text(str(website)[:50]), align="R")
    pdf.set_xy(content_x + content_w * 0.45, 277)
    pdf.set_font("helvetica", "", 7)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(content_w * 0.55, 4, _safe_text(legal[:48]), align="R")

    out = pdf.output(dest="S")
    if logo_tmp:
        try:
            os.unlink(logo_tmp)
        except OSError:
            pass
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)
