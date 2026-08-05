"""
Fill an uploaded payslip PDF in-place (keep original layout pixel-perfect).

On upload we map label → value boxes and earnings/deduction amount boxes.
On generate we white-out those boxes and write the employee's current values
at the same coordinates / font sizes.
"""

from __future__ import annotations

import io
import logging
import re
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# Canonical field → label variants found on Indian payslips
_FIELD_LABELS: dict[str, list[str]] = {
    "employee_name": ["employee name", "emp name", "name of the employee", "name"],
    "designation": ["designation", "job title", "position"],
    "date_of_joining": ["date of joining", "joining date", "doj", "date of join"],
    "location": ["location", "work location", "office location", "place"],
    "pan": ["pan number", "pan no", "pan"],
    "bank_name": ["bank name", "bank"],
    "bank_account": ["a/c no", "a/c number", "account no", "account number", "bank a/c", "account"],
    "days_in_month": ["days in month", "total days", "calendar days"],
    "lop_days": ["lop days", "lop", "loss of pay"],
    "effective_days": ["effective days", "paid days", "working days", "present days"],
    "department": ["department", "dept"],
    "employee_id": ["employee id", "emp id", "emp code", "employee code", "staff id"],
    "uan": ["uan number", "uan"],
    "ifsc": ["ifsc code", "ifsc"],
}

_AMOUNT_RE = re.compile(
    r"^[\-\u20b9RsINR\s]*\d{1,3}(?:,\d{2,3})*(?:\.\d+)?$|^[\-\u20b9RsINR\s]*\d+(?:\.\d+)?$",
    re.I,
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _norm_label(s: str) -> str:
    t = _norm(s).rstrip(":")
    return t


def _is_amount(text: str) -> bool:
    t = (text or "").strip().replace("\u20b9", "").replace(",", "")
    if not t:
        return False
    return bool(_AMOUNT_RE.match((text or "").strip())) or bool(
        re.fullmatch(r"-?\d+(\.\d+)?", t)
    )


def _fmt_amount(value) -> str:
    try:
        n = Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return str(value)
    # Match common payslip style: 1,234.00
    s = f"{n:,.2f}"
    return s


def _collect_spans(page) -> list[dict]:
    """Flatten page text into spans with bboxes."""
    spans: list[dict] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for sp in line.get("spans", []):
                text = (sp.get("text") or "").strip()
                if not text:
                    continue
                bbox = sp.get("bbox")
                if not bbox:
                    continue
                spans.append(
                    {
                        "text": text,
                        "bbox": list(bbox),  # x0,y0,x1,y1
                        "size": float(sp.get("size") or 9),
                        "font": sp.get("font") or "",
                        "origin": list(sp.get("origin") or [bbox[0], bbox[3]]),
                    }
                )
    spans.sort(key=lambda s: (round(s["bbox"][1], 1), s["bbox"][0]))
    return spans


def _same_line(a: dict, b: dict, tol: float = 4.0) -> bool:
    ay = (a["bbox"][1] + a["bbox"][3]) / 2
    by = (b["bbox"][1] + b["bbox"][3]) / 2
    return abs(ay - by) <= tol


def _find_value_for_label(label_span: dict, spans: list[dict], label_text: str) -> dict | None:
    """
    Prefer value on same line to the right of the label.
    If label text contains ':', take substring after ':' as value bbox (same span).
    Else look for next span to the right on same line.
    """
    raw = label_span["text"]
    if ":" in raw:
        parts = raw.split(":", 1)
        after = parts[1].strip()
        if after and not _looks_like_bare_label(after):
            # Value lives in same span after colon — estimate right half bbox
            x0, y0, x1, y1 = label_span["bbox"]
            # Approximate colon split by character ratio
            ratio = len(parts[0]) / max(len(raw), 1)
            vx0 = x0 + (x1 - x0) * min(max(ratio, 0.25), 0.75)
            return {
                "text": after,
                "bbox": [vx0, y0, x1, y1],
                "size": label_span["size"],
                "font": label_span["font"],
                "origin": [vx0, y1 - 1],
            }

    # Next span to the right on same line
    candidates = [
        s
        for s in spans
        if s is not label_span
        and _same_line(label_span, s)
        and s["bbox"][0] >= label_span["bbox"][2] - 2
    ]
    candidates.sort(key=lambda s: s["bbox"][0])
    if candidates:
        return candidates[0]

    # Value on next line below (left-aligned-ish)
    below = [
        s
        for s in spans
        if s is not label_span
        and s["bbox"][1] > label_span["bbox"][3] - 1
        and s["bbox"][1] < label_span["bbox"][3] + label_span["size"] * 2.2
        and abs(s["bbox"][0] - label_span["bbox"][0]) < 80
    ]
    below.sort(key=lambda s: s["bbox"][1])
    return below[0] if below else None


def _looks_like_bare_label(text: str) -> bool:
    t = _norm_label(text)
    for variants in _FIELD_LABELS.values():
        if t in variants:
            return True
    return False


def _match_field_key(label_text: str) -> str | None:
    t = _norm_label(label_text)
    # Strip trailing value if "Name: John"
    if ":" in t:
        t = t.split(":", 1)[0].strip()
    # Prefer longer / more specific matches
    best = None
    best_len = -1
    for key, variants in _FIELD_LABELS.items():
        for v in variants:
            if t == v or t.startswith(v + " ") or v == t:
                if len(v) > best_len:
                    best = key
                    best_len = len(v)
    return best


def build_payslip_field_map(pdf_bytes: bytes) -> dict[str, Any]:
    """
    Analyze first page of a payslip PDF → fillable field / table map.
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc.load_page(0)
        spans = _collect_spans(page)
        fields: dict[str, Any] = {}
        used_span_ids: set[int] = set()

        for i, sp in enumerate(spans):
            key = _match_field_key(sp["text"])
            if not key or key in fields:
                continue
            val = _find_value_for_label(sp, spans, sp["text"])
            if not val:
                continue
            fields[key] = {
                "label": sp["text"],
                "bbox": [round(x, 2) for x in val["bbox"]],
                "size": round(val["size"], 2),
                "align": "left",
            }
            used_span_ids.add(i)

        # Month header: "Payslip for the month of May 2026"
        header = None
        for sp in spans:
            t = _norm(sp["text"])
            if "payslip" in t and ("month" in t or re.search(r"20\d{2}", t)):
                header = {
                    "bbox": [round(x, 2) for x in sp["bbox"]],
                    "size": round(sp["size"], 2),
                    "sample": sp["text"],
                }
                break

        # Earnings / deduction amount rows — column-aware (side-by-side tables)
        earning_rows = []
        deduction_rows = []
        page_mid = page.rect.width / 2
        earn_header_y = None
        ded_header_y = None
        for sp in spans:
            tl = _norm(sp["text"])
            if tl in ("earnings", "earning") or tl.startswith("earnings"):
                earn_header_y = sp["bbox"][1]
                continue
            if tl in ("deductions", "deduction") or tl.startswith("deductions"):
                ded_header_y = sp["bbox"][1]
                continue
            if tl in ("full", "actual", "amount") or tl == "total":
                continue
            if tl.startswith("total ") or "total earnings" in tl or "total deductions" in tl:
                continue
            if _is_amount(sp["text"]) or _looks_like_bare_label(sp["text"]):
                continue

            # Only rows below the earnings/deductions headers
            header_y = min(
                y for y in (earn_header_y, ded_header_y) if y is not None
            ) if (earn_header_y is not None or ded_header_y is not None) else None
            if header_y is None or sp["bbox"][1] < header_y - 2:
                continue

            amts = [
                s
                for s in spans
                if _same_line(sp, s)
                and s["bbox"][0] > sp["bbox"][2]
                and _is_amount(s["text"])
            ]
            amts.sort(key=lambda s: s["bbox"][0])
            if not amts:
                continue

            # Left half ≈ earnings, right half ≈ deductions
            cx = (sp["bbox"][0] + sp["bbox"][2]) / 2
            section = "earning" if cx < page_mid else "deduction"
            row = {
                "name": sp["text"].strip(),
                "name_key": _norm(sp["text"]),
                "amount_bboxes": [
                    {
                        "bbox": [round(x, 2) for x in a["bbox"]],
                        "size": round(a["size"], 2),
                        "sample": a["text"],
                    }
                    for a in amts[-2:]
                ],
            }
            if section == "earning":
                earning_rows.append(row)
            else:
                deduction_rows.append(row)

        # Net pay / totals if present as labeled amounts
        totals = {}
        for sp in spans:
            t = _norm_label(sp["text"])
            for key, needles in (
                ("net_pay", ["net pay", "net salary", "net amount"]),
                ("gross", ["gross pay", "gross earnings", "gross salary", "total earnings"]),
                ("total_deductions", ["total deductions", "total deduction"]),
            ):
                if any(n == t or t.startswith(n) for n in needles):
                    val = _find_value_for_label(sp, spans, sp["text"])
                    if val and (_is_amount(val["text"]) or val["text"]):
                        totals[key] = {
                            "bbox": [round(x, 2) for x in val["bbox"]],
                            "size": round(val["size"], 2),
                        }

        return {
            "page_size": [page.rect.width, page.rect.height],
            "fields": fields,
            "header": header,
            "earning_rows": earning_rows,
            "deduction_rows": deduction_rows,
            "totals": totals,
            "span_count": len(spans),
        }
    finally:
        doc.close()


def _expand_bbox(bbox: list[float], pad: float = 0.8) -> list[float]:
    x0, y0, x1, y1 = bbox
    return [x0 - pad, y0 - pad, x1 + pad, y1 + pad]


def _insert_text(page, bbox: list[float], text: str, size: float, align: str = "left"):
    import fitz

    x0, y0, x1, y1 = bbox
    # Baseline slightly above bottom of box
    fontsize = max(6.0, min(size, y1 - y0 - 0.5))
    text = (text or "")[:80]
    if align == "right":
        tw = fitz.get_text_length(text, fontname="helv", fontsize=fontsize)
        x = max(x0, x1 - tw - 1)
    else:
        x = x0 + 0.5
    y = y1 - 1.5
    page.insert_text(
        (x, y),
        text,
        fontname="helv",
        fontsize=fontsize,
        color=(0, 0, 0),
    )


def _fuzzy_component_match(name: str, rows: list[dict]) -> dict | None:
    key = _norm(name)
    if not key:
        return None
    for row in rows:
        rk = row.get("name_key") or _norm(row.get("name", ""))
        if key == rk or key in rk or rk in key:
            return row
    # token overlap
    tokens = set(key.split())
    best = None
    best_score = 0
    for row in rows:
        rk = row.get("name_key") or _norm(row.get("name", ""))
        score = len(tokens & set(rk.split()))
        if score > best_score:
            best_score = score
            best = row
    return best if best_score >= 1 else None


def fill_payslip_pdf(
    pdf_bytes: bytes,
    *,
    field_map: dict | None,
    values: dict[str, str],
    earning_amounts: dict[str, str],
    deduction_amounts: dict[str, str],
) -> bytes:
    """
    Return a new PDF: original layout with mapped boxes rewritten.
    """
    import fitz

    fmap = field_map or {}
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc.load_page(0)
        redactions: list[list[float]] = []

        def schedule(bbox):
            redactions.append(_expand_bbox(list(bbox), pad=0.6))

        # Header month/year
        header = fmap.get("header")
        if header and values.get("period_header"):
            schedule(header["bbox"])

        for key, meta in (fmap.get("fields") or {}).items():
            if key in values and values[key] is not None:
                schedule(meta["bbox"])

        for key, meta in (fmap.get("totals") or {}).items():
            if key in values and values[key] is not None:
                schedule(meta["bbox"])

        for row in fmap.get("earning_rows") or []:
            if earning_amounts:
                for ab in row.get("amount_bboxes") or []:
                    schedule(ab["bbox"])

        for row in fmap.get("deduction_rows") or []:
            if deduction_amounts:
                for ab in row.get("amount_bboxes") or []:
                    schedule(ab["bbox"])

        for bbox in _dedupe_boxes(redactions):
            page.add_redact_annot(fitz.Rect(bbox), fill=(1, 1, 1))
        page.apply_redactions(images=0)

        # Write new values
        if header and values.get("period_header"):
            _insert_text(
                page,
                header["bbox"],
                values["period_header"],
                header.get("size") or 11,
                align="left",
            )

        for key, meta in (fmap.get("fields") or {}).items():
            if key in values and values[key] is not None:
                _insert_text(
                    page,
                    meta["bbox"],
                    str(values[key]),
                    meta.get("size") or 9,
                    align=meta.get("align") or "left",
                )

        for key, meta in (fmap.get("totals") or {}).items():
            if key in values and values[key] is not None:
                _insert_text(
                    page,
                    meta["bbox"],
                    str(values[key]),
                    meta.get("size") or 9,
                    align="right",
                )

        # Component amounts — write into the rightmost amount box (Actual)
        for row in fmap.get("earning_rows") or []:
            amt = None
            for name, aval in earning_amounts.items():
                if _fuzzy_component_match(name, [row]):
                    amt = aval
                    break
            boxes = row.get("amount_bboxes") or []
            if not boxes:
                continue
            # If Full + Actual, set both to same (or Full=actual for simplicity)
            target = boxes[-1]
            text = amt if amt is not None else "0.00"
            _insert_text(
                page,
                target["bbox"],
                text,
                target.get("size") or 9,
                align="right",
            )
            if len(boxes) >= 2 and amt is not None:
                _insert_text(
                    page,
                    boxes[0]["bbox"],
                    text,
                    boxes[0].get("size") or 9,
                    align="right",
                )

        for row in fmap.get("deduction_rows") or []:
            amt = None
            for name, aval in deduction_amounts.items():
                if _fuzzy_component_match(name, [row]):
                    amt = aval
                    break
            boxes = row.get("amount_bboxes") or []
            if not boxes:
                continue
            target = boxes[-1]
            text = amt if amt is not None else "0.00"
            _insert_text(
                page,
                target["bbox"],
                text,
                target.get("size") or 9,
                align="right",
            )

        out = io.BytesIO()
        doc.save(out, garbage=3, deflate=True)
        return out.getvalue()
    finally:
        doc.close()


def _dedupe_boxes(boxes: list[list[float]]) -> list[list[float]]:
    """Deduplicate heavily overlapping redaction boxes."""
    out: list[list[float]] = []
    for b in boxes:
        if not b or b[2] <= b[0] or b[3] <= b[1]:
            continue
        overlap = False
        for o in out:
            ix0 = max(b[0], o[0])
            iy0 = max(b[1], o[1])
            ix1 = min(b[2], o[2])
            iy1 = min(b[3], o[3])
            if ix1 > ix0 and iy1 > iy0:
                inter = (ix1 - ix0) * (iy1 - iy0)
                area = (b[2] - b[0]) * (b[3] - b[1])
                if area > 0 and inter / area > 0.7:
                    overlap = True
                    break
        if not overlap:
            out.append(b)
    return out


def values_from_payslip(payslip) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Build fill values from a Payslip model / mock."""
    import calendar

    user = payslip.user
    name = f"{user.first_name} {user.last_name}".strip() or (user.email or "")
    month = payslip.payroll_run.month
    year = payslip.payroll_run.year
    month_name = calendar.month_name[month]
    period_header = f"Payslip for the month of {month_name} {year}"

    def _d(d):
        if not d:
            return ""
        if hasattr(d, "strftime"):
            return d.strftime("%d %B %Y")
        return str(d)

    values = {
        "employee_name": name,
        "designation": payslip.designation or "",
        "department": payslip.department or "",
        "date_of_joining": _d(getattr(user, "date_of_joining", None)),
        "location": "",
        "pan": getattr(user, "pan_number", None) or "",
        "bank_name": "",
        "bank_account": getattr(user, "bank_account_number", None) or "",
        "ifsc": getattr(user, "bank_ifsc_code", None) or "",
        "employee_id": getattr(user, "employee_id", None) or str(getattr(user, "id", "")),
        "uan": getattr(user, "uan_number", None) or "",
        "days_in_month": str(payslip.worked_days),
        "lop_days": str(payslip.lop_days),
        "effective_days": str(payslip.worked_days),
        "period_header": period_header,
        "net_pay": _fmt_amount(payslip.net_pay),
        "gross": _fmt_amount(payslip.gross_earnings),
        "total_deductions": _fmt_amount(payslip.total_deductions),
    }

    # Office location name if available
    loc = getattr(user, "office_location", None)
    if loc is not None:
        values["location"] = getattr(loc, "name", None) or getattr(loc, "city", None) or ""

    earnings = {}
    deductions = {}
    for c in payslip.components.filter(component_type="earning"):
        earnings[c.component_name] = _fmt_amount(c.amount)
    for c in payslip.components.filter(component_type="deduction"):
        deductions[c.component_name] = _fmt_amount(c.amount)

    return values, earnings, deductions


def fill_pdf_for_payslip(pdf_bytes: bytes, field_map: dict | None, payslip) -> bytes:
    values, earnings, deductions = values_from_payslip(payslip)
    fmap = field_map
    if not fmap or not fmap.get("fields"):
        try:
            fmap = build_payslip_field_map(pdf_bytes)
        except Exception:
            logger.exception("field map rebuild failed")
            fmap = field_map or {}
    return fill_payslip_pdf(
        pdf_bytes,
        field_map=fmap,
        values=values,
        earning_amounts=earnings,
        deduction_amounts=deductions,
    )
