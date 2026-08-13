"""
Form 16 Part B PDF renderer.

Uses the official TRACES-style blank (watermark + logos + table grid extracted
from MSXPS6972G_PARTB_2026-27.pdf) and stamps labels/values at the sample's
exact text coordinates.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

import fitz

ASSETS_DIR = Path(__file__).resolve().parent / "form16_assets"
BLANK_PDF = ASSETS_DIR / "form16_partb_blank.pdf"
SAMPLE_PDF = ASSETS_DIR / "form16_partb_sample.pdf"
LAYOUT_DIR = ASSETS_DIR / "layout"
REPO_SAMPLE = Path(__file__).resolve().parents[2] / "MSXPS6972G_PARTB_2026-27.pdf"


def _ensure_blank_template() -> Path:
    if BLANK_PDF.exists() and BLANK_PDF.stat().st_size > 1000:
        return BLANK_PDF
    # Rebuild from sample if blank missing
    sample = SAMPLE_PDF if SAMPLE_PDF.exists() else REPO_SAMPLE
    if not sample.exists():
        raise FileNotFoundError(
            "Form 16 template missing. Place MSXPS6972G_PARTB_2026-27.pdf in repo root."
        )
    from documents._build_form16_blank import build_blank

    return Path(build_blank())


def _fmt_money(n: Any) -> str:
    try:
        return f"{float(n or 0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _pdf_text(text: str) -> str:
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
        .replace("\u20b9", "Rs.")
    )


def _split_lines(text: str, max_lines: int = 5) -> list[str]:
    raw = (text or "").replace("\r", "").strip()
    if not raw:
        return [""]
    parts: list[str] = []
    for chunk in raw.split("\n"):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    if len(parts) == 1 and len(parts[0]) > 48:
        # soft-wrap long single-line addresses
        words = parts[0].split()
        parts = []
        cur = ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if len(trial) > 48 and cur:
                parts.append(cur)
                cur = w
            else:
                cur = trial
        if cur:
            parts.append(cur)
    return (parts + [""] * max_lines)[:max_lines]


def _font_for(sample_font: str | None, flags: int | None) -> str:
    bold = bool(flags and (flags & 16))
    name = (sample_font or "").lower()
    if "bold" in name or bold:
        return "times-bold"
    return "times-roman"


def _insert(
    page: fitz.Page,
    x: float,
    y: float,
    text: str,
    *,
    size: float = 8,
    font: str = "times-roman",
    align_right: bool = False,
    max_width: float | None = None,
) -> None:
    text = _pdf_text(text)
    if not text:
        return
    # PyMuPDF insert_text uses baseline; sample bbox y is top — adjust
    baseline = y + size * 0.85
    if align_right:
        tw = fitz.get_text_length(text, fontname=font, fontsize=size)
        x = x - tw
    if max_width:
        # simple clip via truncate
        while (
            len(text) > 3
            and fitz.get_text_length(text, fontname=font, fontsize=size) > max_width
        ):
            text = text[:-2]
        if text and not text.endswith("…") and len(_pdf_text(text)) >= 3:
            pass
    page.insert_text(
        (x, baseline),
        text,
        fontname=font,
        fontsize=size,
        color=(0, 0, 0),
    )


def _load_layout(page_no: int) -> list[dict]:
    path = LAYOUT_DIR / f"page{page_no}_lines.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _build_value_map(summary: dict[str, Any]) -> dict[tuple[int, float, float], str]:
    """
    Map (page_index_0based, y, x) → replacement text for sample value positions.
    Coordinates taken from MSXPS6972G_PARTB_2026-27.pdf text extraction.
    """
    emp_addr = _split_lines(summary.get("employer_address") or "", 4)
    # Fill employer block: name + up to 4 addr + phone + email (sample used 5 lines under name)
    employer_lines = [summary.get("employer_name") or ""] + [
        x for x in emp_addr if x
    ]
    while len(employer_lines) < 4:
        employer_lines.append("")
    employer_lines = employer_lines[:4]
    # phone / email on last two sample rows if present
    phone = summary.get("employer_phone") or ""
    email = summary.get("employer_email") or ""

    ee_addr = _split_lines(summary.get("employee_address") or "", 4)
    employee_lines = [summary.get("employee_name") or ""] + [x for x in ee_addr if x]
    while len(employee_lines) < 4:
        employee_lines.append("")
    employee_lines = employee_lines[:4]

    cit = _split_lines(summary.get("cit_tds_office") or "", 3)
    while len(cit) < 3:
        cit.append("")

    money = {
        "gross": _fmt_money(summary.get("gross_salary")),
        "zero": "0.00",
        "exempt_total": _fmt_money(summary.get("total_exempt_10")),
        "hra_exempt": _fmt_money(summary.get("hra_exempt")),
        "salary_employer": _fmt_money(summary.get("salary_from_employer")),
        "std_deduction": _fmt_money(summary.get("std_deduction")),
        "income_salaries": _fmt_money(summary.get("income_salaries")),
        "gross_total": _fmt_money(summary.get("income_salaries")),  # + other income ~0
        "section_80c": _fmt_money(summary.get("section_80c")),
        "chapter_via": _fmt_money(summary.get("chapter_via_total")),
        "taxable": _fmt_money(summary.get("total_taxable")),
        "tax_on_total": _fmt_money(summary.get("tax_on_total")),
        "rebate_87a": _fmt_money(summary.get("rebate_87a")),
        "tds_total": _fmt_money(summary.get("tds_total")),
        "net_tax": _fmt_money(
            max(
                float(summary.get("tax_on_total") or 0)
                - float(summary.get("rebate_87a") or 0)
                - float(summary.get("tds_total") or 0),
                0,
            )
        ),
    }

    opting = summary.get("opting_out_115bac") or "No"
    cert = summary.get("certificate_no") or ""
    updated = summary.get("generated_on") or ""
    ay = summary.get("assessment_year") or ""
    period_from = summary.get("period_from") or ""
    period_to = summary.get("period_to") or ""
    pan_d = summary.get("employer_pan") or ""
    tan = summary.get("employer_tan") or ""
    pan_e = summary.get("employee_pan") or ""
    place = summary.get("place") or ""
    signatory = summary.get("signatory_name") or ""
    father = summary.get("signatory_father") or ""
    designation = summary.get("signatory_designation") or "Authorised Signatory"

    verification = (
        f"I,  {signatory or '________________'}, son/daughter of {father or '________________'} "
        f".Working in the capacity of {designation} (Designation) do"
    )

    m: dict[tuple[int, float, float], str] = {
        # Page 1 header meta
        (0, 138.3, 81.0): cert,
        (0, 138.8, 513.3): updated,
        # Employer block
        (0, 181.2, 29.0): employer_lines[0],
        (0, 191.3, 29.0): employer_lines[1],
        (0, 201.3, 29.0): employer_lines[2],
        (0, 211.4, 29.0): employer_lines[3],
        (0, 221.4, 29.0): phone,
        (0, 231.5, 29.0): email,
        # Employee block
        (0, 191.3, 321.0): employee_lines[0],
        (0, 201.3, 321.0): employee_lines[1],
        (0, 211.4, 321.0): employee_lines[2],
        (0, 221.4, 321.0): employee_lines[3],
        # IDs
        (0, 273.8, 86.9): pan_d,
        (0, 273.8, 267.7): tan,
        (0, 273.8, 452.0): pan_e,
        # CIT / AY / period
        (0, 318.8, 93.2): cit[0] or "The Commissioner of Income Tax (TDS)",
        (0, 328.8, 67.8): cit[1],
        (0, 338.9, 106.4): cit[2],
        (0, 329.3, 354.2): ay,
        (0, 332.8, 446.6): period_from,
        (0, 332.8, 515.7): period_to,
        # Opting out
        (0, 404.6, 455.4): opting,
        # Gross salary amounts
        (0, 452.6, 418.5): money["gross"],
        (0, 480.6, 443.5): money["zero"],
        (0, 507.1, 443.5): money["zero"],
        (0, 529.1, 530.5): money["gross"],
        (0, 552.1, 555.5): money["zero"],
        # Sec 10 exemptions
        (0, 603.1, 443.5): money["zero"],
        (0, 632.1, 443.5): money["zero"],
        (0, 661.1, 443.5): money["zero"],
        (0, 690.6, 443.5): money["zero"],
        (0, 719.6, 443.5): money["hra_exempt"],
        (0, 747.6, 443.5): money["zero"],
        # Page 2 header
        (1, 33.7, 29.9): f"Certificate Number: {cert}",
        (1, 33.7, 162.0): f"TAN of Employer: {tan}",
        (1, 33.7, 312.3): f"PAN of Employee: {pan_e}",
        (1, 33.7, 459.5): f"Assessment Year: {ay}",
        # Page 2 amounts
        (1, 135.1, 443.5): money["zero"],
        (1, 170.1, 555.5): money["exempt_total"],
        (1, 205.6, 530.5): money["salary_employer"],
        (1, 247.6, 423.5): money["std_deduction"],
        (1, 270.6, 443.5): money["zero"],
        (1, 294.6, 443.5): money["zero"],
        (1, 320.6, 535.5): money["std_deduction"],
        (1, 353.6, 530.5): money["income_salaries"],
        (1, 410.6, 443.5): money["zero"],
        (1, 445.6, 443.5): money["zero"],
        (1, 475.6, 555.5): money["zero"],
        (1, 500.1, 530.5): money["gross_total"],
        # 80C block — put section_80c in (a) deductible
        (1, 552.1, 443.5): money["section_80c"],
        (1, 552.1, 555.5): money["section_80c"],
        (1, 585.6, 443.5): money["zero"],
        (1, 585.6, 555.5): money["zero"],
        (1, 615.6, 443.5): money["zero"],
        (1, 615.6, 555.5): money["zero"],
        (1, 645.6, 443.5): money["section_80c"],
        (1, 645.6, 555.5): money["section_80c"],
        (1, 676.6, 443.5): money["zero"],
        (1, 676.6, 555.5): money["zero"],
        (1, 709.1, 443.5): money["zero"],
        (1, 709.1, 555.5): money["zero"],
        (1, 741.6, 443.5): money["zero"],
        (1, 741.6, 555.5): money["zero"],
        # Page 3 header
        (2, 33.7, 29.9): f"Certificate Number: {cert}",
        (2, 33.7, 162.0): f"TAN of Employer: {tan}",
        (2, 33.7, 312.3): f"PAN of Employee: {pan_e}",
        (2, 33.7, 459.5): f"Assessment Year: {ay}",
        (2, 59.6, 443.5): money["zero"],
        (2, 59.6, 555.5): money["zero"],
        (2, 91.6, 443.5): money["zero"],
        (2, 91.6, 470.0): money["zero"],
        (2, 123.6, 443.5): money["zero"],
        (2, 123.6, 470.0): money["zero"],
        (2, 185.6, 406.5): money["zero"],
        (2, 185.6, 480.5): money["zero"],
        (2, 185.6, 555.5): money["zero"],
        (2, 216.1, 406.5): money["zero"],
        (2, 216.1, 480.5): money["zero"],
        (2, 216.1, 555.5): money["zero"],
        (2, 309.6, 406.5): money["zero"],
        (2, 309.6, 480.5): money["zero"],
        (2, 309.6, 555.5): money["zero"],
        (2, 343.1, 555.5): money["chapter_via"],
        (2, 373.1, 530.5): money["taxable"],
        (2, 398.1, 540.5): money["tax_on_total"],
        (2, 423.1, 540.5): money["rebate_87a"],
        (2, 448.1, 555.5): money["zero"],
        (2, 473.1, 555.5): money["zero"],
        (2, 498.1, 555.5): _fmt_money(
            max(
                float(summary.get("tax_on_total") or 0)
                - float(summary.get("rebate_87a") or 0),
                0,
            )
        ),
        (2, 521.6, 555.5): money["zero"],
        (2, 568.6, 555.5): money["tds_total"],
        (2, 615.6, 555.5): money["net_tax"],
        # Verification
        (2, 652.0, 25.0): verification,
        (2, 700.3, 150.7): place,
        (2, 720.8, 181.8): updated,
        (2, 720.8, 366.0): signatory,
        # Page 4
        (3, 33.7, 29.9): f"Certificate Number: {cert}",
        (3, 33.7, 162.0): f"TAN of Employer: {tan}",
        (3, 33.7, 312.3): f"PAN of Employee: {pan_e}",
        (3, 33.7, 459.5): f"Assessment Year: {ay}",
        (3, 408.3, 158.2): place,
        (3, 442.3, 189.3): updated,
        (3, 442.3, 381.0): signatory,
    }
    return m


# Sample-only strings that must never be re-stamped as labels
_SAMPLE_SKIP_EXACT = {
    "MVQSNRA",
    "24-Jun-2026",
    "NETWORTH DATA PRODUCTS PRIVATE LIMITED",
    "132 C,, ECC ROAD,",
    "WHITEFIELD, Bangalore - 560066",
    "Karnataka",
    "+(91)91-9739217445",
    "sufyaan@saseca.in",
    "SOMAMBUDIAGRAHARA NAGESHACHAR SRINIDHI",
    "12 BRAHHENDRA SWAMY, KRUPA SRI SAI JYOTHI, LAYOUT",
    "SINGANAYAKANHALLI, YELAHANKA, BANGALORE - 560064",
    "AAGCN2055H",
    "BLRN12363B",
    "MSXPS6972G",
    "2026-27",
    "The Commissioner of Income Tax (TDS)",
    "Room No. 59, H.M.T. Bhawan, 4th Floor, Bellary Road ,",
    "Ganganagar, Bangalore - 560032",
    "01-Apr-2025",
    "31-Mar-2026",
    "No",
    "660000.00",
    "0.00",
    "75000.00",
    "585000.00",
    "9250.00",
    "BANGALORE, BANGALORE",
    "NITISH  VISHWANATH",
    "NITISH VISHWANATH",
}


def _is_sample_header_line(text: str) -> bool:
    t = text.strip()
    return (
        t.startswith("Certificate Number:")
        or t.startswith("TAN of Employer:")
        or t.startswith("PAN of Employee:")
        or t.startswith("Assessment Year:")
    )


def _is_money_token(text: str) -> bool:
    t = text.strip().replace(",", "")
    if not t:
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False


def _lookup_value(
    values: dict[tuple[int, float, float], str], page_i: int, y: float, x: float
) -> str | None:
    # Exact then near match (float rounding)
    if (page_i, y, x) in values:
        return values[(page_i, y, x)]
    for (pi, yy, xx), val in values.items():
        if pi == page_i and abs(yy - y) < 0.6 and abs(xx - x) < 0.6:
            return val
    return None


def _is_amount_x(x: float) -> bool:
    """Amount columns in the TRACES Part B grid."""
    return x >= 400


def _amount_right_edge(x: float) -> float:
    if x >= 520:
        return 572.0
    if x >= 470:
        return 510.0
    if x >= 400:
        return 470.0
    return x


def render_form16_part_b_from_template(summary: dict[str, Any]) -> bytes:
    blank = _ensure_blank_template()
    doc = fitz.open(blank)
    values = _build_value_map(summary)

    # Center TRACES word (text-only in sample; not part of logo image strip)
    if doc.page_count:
        p0 = doc[0]
        p0.insert_text(
            (248, 42),
            "TRACES",
            fontname="helv",
            fontsize=14,
            color=(0.05, 0.25, 0.55),
        )
        p0.insert_text(
            (175, 54),
            "TDS Reconciliation Analysis and Correction Enabling System",
            fontname="helv",
            fontsize=5,
            color=(0.05, 0.25, 0.55),
        )

    for page_i in range(doc.page_count):
        page = doc[page_i]
        layout = _load_layout(page_i + 1)
        written_slots: set[tuple[int, float, float]] = set()

        for line in layout:
            text = (line.get("text") or "").strip()
            if not text:
                continue
            y = float(line["y"])
            x = float(line["x"])
            size = float(line.get("size") or 8)
            font = _font_for(line.get("font"), line.get("flags"))

            slot_val = _lookup_value(values, page_i, y, x)
            if slot_val is not None:
                if _is_amount_x(x) and _is_money_token(slot_val):
                    _insert(
                        page,
                        _amount_right_edge(x),
                        y,
                        slot_val,
                        size=size,
                        font=font,
                        align_right=True,
                    )
                else:
                    _insert(page, x, y, slot_val, size=size, font=font)
                written_slots.add((page_i, y, x))
                continue

            # Skip leftover sample personal/money lines not mapped
            if text in _SAMPLE_SKIP_EXACT or _is_sample_header_line(text):
                continue
            if _is_money_token(text):
                continue
            if text.startswith("I,  NITISH") or "NITISH VISHWANATH" in text:
                continue

            _insert(page, x, y, text, size=size, font=font)
            # Sample underlines PART B
            if page_i == 0 and text == "PART B":
                tw = fitz.get_text_length(text, fontname=font, fontsize=size)
                page.draw_line(
                    fitz.Point(x, y + size + 1),
                    fitz.Point(x + tw, y + size + 1),
                    width=0.6,
                    color=(0, 0, 0),
                )

        # Ensure critical slots were written even if layout miss
        for (pi, yy, xx), val in values.items():
            if pi != page_i:
                continue
            if any(abs(yy - s[1]) < 0.6 and abs(xx - s[2]) < 0.6 for s in written_slots):
                continue
            size = 8 if pi == 0 else (6 if yy < 40 else 10)
            if _is_amount_x(xx) and _is_money_token(val):
                _insert(
                    page,
                    _amount_right_edge(xx),
                    yy,
                    val,
                    size=size,
                    font="times-roman",
                    align_right=True,
                )
            else:
                _insert(page, xx, yy, val, size=size)

    out = io.BytesIO()
    doc.save(out, deflate=True, garbage=3)
    doc.close()
    return out.getvalue()
