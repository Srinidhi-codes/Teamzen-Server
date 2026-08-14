"""
Fill an uploaded payslip PDF in-place (keep original layout pixel-perfect).

On upload we map label → value boxes and earnings/deduction amount boxes.
On generate we white-out those boxes and write the employee's current values
at the same coordinates / font sizes, and swap the company logo when possible.
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
    "employee_name": [
        "employee name",
        "name of the employee",
        "name of employee",
        "emp name",
        "employee",
        "staff name",
    ],
    "designation": ["designation", "job title", "position", "role"],
    "date_of_joining": [
        "date of joining",
        "joining date",
        "date of join",
        "doj",
        "joined on",
    ],
    "location": [
        "work location",
        "office location",
        "location",
        "place of posting",
        "base location",
    ],
    "pan": ["pan number", "pan no.", "pan no", "pan"],
    "bank_name": ["bank name", "bank"],
    "bank_account": [
        "a/c no.",
        "a/c no",
        "a/c number",
        "account no.",
        "account no",
        "account number",
        "bank a/c",
        "bank account",
        "account",
    ],
    "days_in_month": [
        "days in month",
        "total days",
        "calendar days",
        "month days",
    ],
    "lop_days": ["lop days", "loss of pay", "lop", "leave without pay"],
    "effective_days": [
        "effective days",
        "paid days",
        "working days",
        "present days",
        "days payable",
    ],
    "department": ["department", "dept", "dept."],
    "employee_id": [
        "employee id",
        "employee code",
        "emp id",
        "emp code",
        "staff id",
        "emp. code",
        "emp. id",
    ],
    "uan": ["uan number", "uan no.", "uan no", "uan"],
    "ifsc": ["ifsc code", "ifsc"],
    "company_name": [
        "company name",
        "organisation name",
        "organization name",
        "employer name",
    ],
}

# Short labels that must match exactly (avoid "name" matching "bank name")
_EXACT_ONLY_LABELS = {"pan", "uan", "lop", "bank", "account", "employee", "name"}

_AMOUNT_RE = re.compile(
    r"^[\-\u20b9RsINR\s]*\d{1,3}(?:,\d{2,3})*(?:\.\d+)?$|^[\-\u20b9RsINR\s]*\d+(?:\.\d+)?$",
    re.I,
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _norm_label(s: str) -> str:
    return _norm(s).rstrip(":").rstrip(".")


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
    return f"{n:,.2f}"


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
                        "bbox": list(bbox),
                        "size": float(sp.get("size") or 9),
                        "font": sp.get("font") or "",
                        "origin": list(sp.get("origin") or [bbox[0], bbox[3]]),
                    }
                )
    spans.sort(key=lambda s: (round(s["bbox"][1], 1), s["bbox"][0]))
    return spans


def _collect_lines(spans: list[dict]) -> list[dict]:
    """Merge same-line spans into logical lines for Label: Value detection."""
    if not spans:
        return []
    lines: list[list[dict]] = []
    current: list[dict] = [spans[0]]
    for sp in spans[1:]:
        if _same_line(current[-1], sp, tol=3.5):
            current.append(sp)
        else:
            lines.append(current)
            current = [sp]
    lines.append(current)

    out: list[dict] = []
    for group in lines:
        group = sorted(group, key=lambda s: s["bbox"][0])
        text = " ".join(s["text"] for s in group)
        x0 = min(s["bbox"][0] for s in group)
        y0 = min(s["bbox"][1] for s in group)
        x1 = max(s["bbox"][2] for s in group)
        y1 = max(s["bbox"][3] for s in group)
        out.append(
            {
                "text": text,
                "bbox": [x0, y0, x1, y1],
                "size": max(s["size"] for s in group),
                "spans": group,
            }
        )
    return out


def _same_line(a: dict, b: dict, tol: float = 4.0) -> bool:
    ay = (a["bbox"][1] + a["bbox"][3]) / 2
    by = (b["bbox"][1] + b["bbox"][3]) / 2
    return abs(ay - by) <= tol


def _looks_like_bare_label(text: str) -> bool:
    t = _norm_label(text)
    for variants in _FIELD_LABELS.values():
        if t in variants:
            return True
    return False


def _match_field_key(label_text: str) -> str | None:
    t = _norm_label(label_text)
    if ":" in t:
        t = t.split(":", 1)[0].strip()
    # Drop trailing separators like "Employee Name -"
    t = re.sub(r"[\-\|]+$", "", t).strip()

    best = None
    best_len = -1
    for key, variants in _FIELD_LABELS.items():
        for v in sorted(variants, key=len, reverse=True):
            if v in _EXACT_ONLY_LABELS:
                matched = t == v
            else:
                matched = (
                    t == v
                    or t.startswith(v + " ")
                    or t.endswith(" " + v)
                    or f" {v} " in f" {t} "
                )
            if matched and len(v) > best_len:
                best = key
                best_len = len(v)
    # Lone "name" only if clearly employee-ish
    if best is None and t in ("name", "emp. name", "emp name"):
        best = "employee_name"
    return best


def _find_value_for_label(label_span: dict, spans: list[dict], label_text: str) -> dict | None:
    """
    Prefer value on same line to the right of the label.
    If label text contains ':', take substring after ':' as value bbox (same span).
    """
    raw = label_span["text"]
    if ":" in raw:
        parts = raw.split(":", 1)
        after = parts[1].strip()
        if after and not _looks_like_bare_label(after):
            x0, y0, x1, y1 = label_span["bbox"]
            ratio = len(parts[0]) / max(len(raw), 1)
            vx0 = x0 + (x1 - x0) * min(max(ratio, 0.25), 0.75)
            return {
                "text": after,
                "bbox": [vx0, y0, x1, y1],
                "size": label_span["size"],
                "font": label_span.get("font") or "",
                "origin": [vx0, y1 - 1],
            }

    candidates = [
        s
        for s in spans
        if s is not label_span
        and _same_line(label_span, s)
        and s["bbox"][0] >= label_span["bbox"][2] - 2
    ]
    candidates.sort(key=lambda s: s["bbox"][0])
    if candidates:
        # Merge consecutive value spans on the same line (multi-word names)
        first = candidates[0]
        merged = [first]
        for s in candidates[1:]:
            if s["bbox"][0] - merged[-1]["bbox"][2] < 40 and not _is_amount(s["text"]):
                # stop if we hit another label
                if _match_field_key(s["text"]):
                    break
                merged.append(s)
            else:
                break
        text = " ".join(s["text"] for s in merged)
        return {
            "text": text,
            "bbox": [
                merged[0]["bbox"][0],
                min(s["bbox"][1] for s in merged),
                merged[-1]["bbox"][2],
                max(s["bbox"][3] for s in merged),
            ],
            "size": first["size"],
            "font": first.get("font") or "",
            "origin": list(first.get("origin") or [first["bbox"][0], first["bbox"][3]]),
        }

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


def _value_from_line(line: dict, label_key: str) -> dict | None:
    """Extract value bbox from a merged line that contains a known label."""
    text = line["text"]
    spans = line.get("spans") or [line]
    # Colon-separated on the full line
    if ":" in text:
        left, right = text.split(":", 1)
        if _match_field_key(left) == label_key and right.strip():
            # Approximate value region = right portion of line bbox
            ratio = len(left) / max(len(text), 1)
            x0, y0, x1, y1 = line["bbox"]
            vx0 = x0 + (x1 - x0) * min(max(ratio, 0.2), 0.85)
            # Prefer span-accurate bbox if possible
            val_spans = [
                s
                for s in spans
                if s["bbox"][0] >= vx0 - 2 and _norm(s["text"]) not in ("", ":")
            ]
            if val_spans:
                return {
                    "text": right.strip(),
                    "bbox": [
                        min(s["bbox"][0] for s in val_spans),
                        min(s["bbox"][1] for s in val_spans),
                        max(s["bbox"][2] for s in val_spans),
                        max(s["bbox"][3] for s in val_spans),
                    ],
                    "size": max(s["size"] for s in val_spans),
                }
            return {
                "text": right.strip(),
                "bbox": [vx0, y0, x1, y1],
                "size": line["size"],
            }

    # Label span then value spans to the right
    for i, sp in enumerate(spans):
        if _match_field_key(sp["text"]) == label_key:
            rest = spans[i + 1 :]
            # Skip pure separators
            rest = [s for s in rest if s["text"].strip() not in (":", "-", "|")]
            if not rest:
                return None
            return {
                "text": " ".join(s["text"] for s in rest),
                "bbox": [
                    rest[0]["bbox"][0],
                    min(s["bbox"][1] for s in rest),
                    rest[-1]["bbox"][2],
                    max(s["bbox"][3] for s in rest),
                ],
                "size": rest[0]["size"],
            }
    return None


def _detect_logo_bbox(page) -> list[float] | None:
    """Largest image in the top-left header zone (typical company logo)."""
    data = page.get_text("dict")
    candidates = []
    top = page.rect.height * 0.28
    mid_x = page.rect.width * 0.55
    for block in data.get("blocks", []):
        if block.get("type") != 1:
            continue
        bbox = block.get("bbox")
        if not bbox:
            continue
        x0, y0, x1, y1 = bbox
        if y1 > top or x0 > mid_x:
            continue
        area = max(0, x1 - x0) * max(0, y1 - y0)
        if area < 400:
            continue
        candidates.append((area, [x0, y0, x1, y1]))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def _detect_company_name(spans: list[dict], page, logo_bbox: list[float] | None) -> dict | None:
    """Heuristic: large text near top (not payslip title) ≈ company name."""
    top = page.rect.height * 0.22
    skip = ("payslip", "salary slip", "pay slip", "confidential", "private")
    best = None
    best_score = -1.0
    for sp in spans:
        if sp["bbox"][1] > top:
            continue
        t = _norm(sp["text"])
        if not t or len(t) < 3:
            continue
        if any(s in t for s in skip):
            continue
        if _is_amount(sp["text"]) or _match_field_key(sp["text"]):
            continue
        # Prefer larger fonts and left/center placement
        score = sp["size"] * 10 + min(len(sp["text"]), 40)
        if logo_bbox and sp["bbox"][0] < logo_bbox[2] + 20:
            score += 15
        if score > best_score:
            best_score = score
            best = sp
    if not best:
        return None
    return {
        "bbox": [round(x, 2) for x in best["bbox"]],
        "size": round(best["size"], 2),
        "sample": best["text"],
        "align": "left",
    }


def build_payslip_field_map(pdf_bytes: bytes) -> dict[str, Any]:
    """
    Analyze first page of a payslip PDF → fillable field / table map.
    """
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc.load_page(0)
        spans = _collect_spans(page)
        lines = _collect_lines(spans)
        fields: dict[str, Any] = {}

        # 1) Span-level label → value
        for sp in spans:
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
                "sample": val.get("text") or "",
            }

        # 2) Line-level Label: Value (catches split spans)
        for line in lines:
            key = _match_field_key(line["text"].split(":")[0])
            if not key or key in fields:
                continue
            val = _value_from_line(line, key)
            if not val:
                continue
            fields[key] = {
                "label": line["text"],
                "bbox": [round(x, 2) for x in val["bbox"]],
                "size": round(val["size"], 2),
                "align": "left",
                "sample": val.get("text") or "",
            }

        # Month header
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
        if header is None:
            for line in lines:
                t = _norm(line["text"])
                if "payslip" in t and ("month" in t or re.search(r"20\d{2}", t)):
                    header = {
                        "bbox": [round(x, 2) for x in line["bbox"]],
                        "size": round(line["size"], 2),
                        "sample": line["text"],
                    }
                    break

        # Earnings / deduction rows
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

        for sp in spans:
            tl = _norm(sp["text"])
            if tl in ("earnings", "earning", "deductions", "deduction"):
                continue
            if tl in ("full", "actual", "amount") or tl == "total":
                continue
            if tl.startswith("total ") or "total earnings" in tl or "total deductions" in tl:
                continue
            if any(
                n == tl or tl.startswith(n)
                for n in (
                    "net pay",
                    "net salary",
                    "net amount",
                    "take home",
                    "gross pay",
                    "gross earnings",
                    "gross salary",
                )
            ):
                continue
            if _is_amount(sp["text"]) or _looks_like_bare_label(sp["text"]):
                continue
            if _match_field_key(sp["text"]):
                continue

            header_y = (
                min(y for y in (earn_header_y, ded_header_y) if y is not None)
                if (earn_header_y is not None or ded_header_y is not None)
                else None
            )
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

        totals = {}
        for sp in spans:
            t = _norm_label(sp["text"])
            if ":" in t:
                t = t.split(":", 1)[0].strip()
            for key, needles in (
                ("net_pay", ["net pay", "net salary", "net amount", "take home"]),
                ("gross", ["gross pay", "gross earnings", "gross salary", "total earnings"]),
                ("total_deductions", ["total deductions", "total deduction"]),
            ):
                if any(n == t or t.startswith(n) for n in needles):
                    val = _find_value_for_label(sp, spans, sp["text"])
                    if val and (_is_amount(val["text"]) or val["text"]):
                        totals[key] = {
                            "bbox": [round(x, 2) for x in val["bbox"]],
                            "size": round(val["size"], 2),
                            "sample": val.get("text") or "",
                        }

        logo_bbox = _detect_logo_bbox(page)
        if "company_name" not in fields:
            company = _detect_company_name(spans, page, logo_bbox)
            if company:
                fields["company_name"] = {
                    "label": "company",
                    "bbox": company["bbox"],
                    "size": company["size"],
                    "align": "left",
                    "sample": company.get("sample") or "",
                }

        return {
            "page_size": [page.rect.width, page.rect.height],
            "fields": fields,
            "header": header,
            "earning_rows": earning_rows,
            "deduction_rows": deduction_rows,
            "totals": totals,
            "logo_bbox": [round(x, 2) for x in logo_bbox] if logo_bbox else None,
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
    box_h = max(y1 - y0, 1.0)
    box_w = max(x1 - x0, 1.0)
    fontsize = max(6.0, min(size, box_h - 0.5))
    text = (text or "")[:120]
    for _ in range(8):
        tw = fitz.get_text_length(text, fontname="helv", fontsize=fontsize)
        if tw <= box_w + 1 or fontsize <= 6.0:
            break
        fontsize = max(6.0, fontsize - 0.5)
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


def _match_amounts_to_rows(
    rows: list[dict], amounts: dict[str, str]
) -> list[tuple[dict, str | None]]:
    remaining = dict(amounts or {})
    assigned: list[tuple[dict, str | None]] = []

    for row in rows:
        amt = None
        matched_key = None
        for name, aval in remaining.items():
            if _fuzzy_component_match(name, [row]):
                amt = aval
                matched_key = name
                break
        if matched_key is not None:
            remaining.pop(matched_key, None)
        assigned.append((row, amt))

    leftovers = list(remaining.values())
    li = 0
    out: list[tuple[dict, str | None]] = []
    for row, amt in assigned:
        if amt is None and li < len(leftovers):
            amt = leftovers[li]
            li += 1
        out.append((row, amt))
    return out


def _resolve_org_logo_bytes(organization) -> bytes | None:
    """Load org logo as image bytes for PDF insertion."""
    if not organization or not getattr(organization, "logo", None):
        return None
    try:
        from payroll.services import _resolve_logo_path
        import os

        path, is_temp = _resolve_logo_path(organization)
        if not path or not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            data = f.read()
        if is_temp:
            try:
                os.unlink(path)
            except OSError:
                pass
        return data or None
    except Exception:
        logger.exception("Could not load org logo for payslip fill")
        return None


def fill_payslip_pdf(
    pdf_bytes: bytes,
    *,
    field_map: dict | None,
    values: dict[str, str],
    earning_amounts: dict[str, str],
    deduction_amounts: dict[str, str],
    logo_bytes: bytes | None = None,
) -> tuple[bytes, int]:
    """
    Return (new PDF bytes, rewrite_count).
    rewrite_count == 0 means nothing changed (caller should not use as filled slip).
    """
    import fitz

    fmap = field_map or {}
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc.load_page(0)
        redactions: list[list[float]] = []
        rewrite_count = 0

        def schedule(bbox):
            redactions.append(_expand_bbox(list(bbox), pad=0.8))

        header = fmap.get("header")
        if header and values.get("period_header"):
            schedule(header["bbox"])

        for key, meta in (fmap.get("fields") or {}).items():
            if key in values and values[key] not in (None, ""):
                schedule(meta["bbox"])

        for key, meta in (fmap.get("totals") or {}).items():
            if key in values and values[key] not in (None, ""):
                schedule(meta["bbox"])

        earn_pairs = _match_amounts_to_rows(
            fmap.get("earning_rows") or [], earning_amounts
        )
        ded_pairs = _match_amounts_to_rows(
            fmap.get("deduction_rows") or [], deduction_amounts
        )

        if earning_amounts:
            for row, _amt in earn_pairs:
                for ab in row.get("amount_bboxes") or []:
                    schedule(ab["bbox"])

        if deduction_amounts:
            for row, _amt in ded_pairs:
                for ab in row.get("amount_bboxes") or []:
                    schedule(ab["bbox"])

        logo_bbox = fmap.get("logo_bbox")
        if logo_bytes and logo_bbox:
            schedule(logo_bbox)

        for bbox in _dedupe_boxes(redactions):
            page.add_redact_annot(fitz.Rect(bbox), fill=(1, 1, 1))
        if redactions:
            page.apply_redactions(images=0)

        if header and values.get("period_header"):
            _insert_text(
                page,
                header["bbox"],
                values["period_header"],
                header.get("size") or 11,
                align="left",
            )
            rewrite_count += 1

        for key, meta in (fmap.get("fields") or {}).items():
            if key in values and values[key] not in (None, ""):
                _insert_text(
                    page,
                    meta["bbox"],
                    str(values[key]),
                    meta.get("size") or 9,
                    align=meta.get("align") or "left",
                )
                rewrite_count += 1

        for key, meta in (fmap.get("totals") or {}).items():
            if key in values and values[key] not in (None, ""):
                _insert_text(
                    page,
                    meta["bbox"],
                    str(values[key]),
                    meta.get("size") or 9,
                    align="right",
                )
                rewrite_count += 1

        for row, amt in earn_pairs:
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
            rewrite_count += 1
            if len(boxes) >= 2 and amt is not None:
                _insert_text(
                    page,
                    boxes[0]["bbox"],
                    text,
                    boxes[0].get("size") or 9,
                    align="right",
                )

        for row, amt in ded_pairs:
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
            rewrite_count += 1

        if logo_bytes and logo_bbox:
            try:
                page.insert_image(fitz.Rect(logo_bbox), stream=logo_bytes, keep_proportion=True)
                rewrite_count += 1
            except Exception:
                logger.exception("Failed to insert org logo into payslip")

        out = io.BytesIO()
        doc.save(out, garbage=3, deflate=True)
        return out.getvalue(), rewrite_count
    finally:
        doc.close()


def _dedupe_boxes(boxes: list[list[float]]) -> list[list[float]]:
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


def _attr_name(obj, *attrs) -> str:
    for a in attrs:
        v = getattr(obj, a, None)
        if v is None:
            continue
        if hasattr(v, "name"):
            return str(v.name or "")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def values_from_payslip(payslip) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Build fill values from a Payslip model / mock."""
    import calendar

    user = payslip.user
    name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    if not name:
        name = getattr(user, "email", None) or ""
    month = payslip.payroll_run.month
    year = payslip.payroll_run.year
    month_name = calendar.month_name[month]
    period_header = f"Payslip for the month of {month_name} {year}"

    org = getattr(payslip.payroll_run, "organization", None)
    company_name = getattr(org, "name", None) or ""

    def _d(d):
        if not d:
            return ""
        if hasattr(d, "strftime"):
            return d.strftime("%d %B %Y")
        return str(d)

    designation = (
        payslip.designation
        or _attr_name(user, "designation")
        or ""
    )
    department = (
        payslip.department
        or _attr_name(user, "department")
        or ""
    )

    values = {
        "employee_name": name,
        "designation": designation,
        "department": department,
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
        "company_name": company_name,
    }

    loc = getattr(user, "office_location", None)
    if loc is not None:
        values["location"] = getattr(loc, "name", None) or getattr(loc, "city", None) or ""

    earnings = {}
    deductions = {}
    comps = getattr(payslip, "components", None)
    if comps is not None and hasattr(comps, "filter"):
        for c in comps.filter(component_type="earning"):
            earnings[c.component_name] = _fmt_amount(c.amount)
        for c in comps.filter(component_type="deduction"):
            deductions[c.component_name] = _fmt_amount(c.amount)
    elif comps is not None:
        for c in list(comps):
            ctype = getattr(c, "component_type", "")
            cname = getattr(c, "component_name", "")
            if ctype == "earning":
                earnings[cname] = _fmt_amount(c.amount)
            elif ctype == "deduction":
                deductions[cname] = _fmt_amount(c.amount)

    return values, earnings, deductions


def field_map_quality(fmap: dict | None) -> int:
    """Rough score — how much we can rewrite on this template."""
    if not fmap:
        return 0
    score = 0
    score += len(fmap.get("fields") or {})
    score += 1 if fmap.get("header") else 0
    score += len(fmap.get("totals") or {})
    score += min(len(fmap.get("earning_rows") or {}), 8)
    score += min(len(fmap.get("deduction_rows") or {}), 8)
    return score


def fill_pdf_for_payslip(pdf_bytes: bytes, field_map: dict | None, payslip) -> bytes:
    """
    Fill the source PDF for this payslip.
    Raises ValueError if the PDF could not be meaningfully rewritten
    (so callers can fall back to a drawn layout instead of shipping the sample).
    """
    values, earnings, deductions = values_from_payslip(payslip)
    fmap = field_map or {}
    try:
        rebuilt = build_payslip_field_map(pdf_bytes)
        if field_map_quality(rebuilt) >= field_map_quality(fmap):
            fmap = rebuilt or fmap
        elif not fmap:
            fmap = rebuilt or {}
    except Exception:
        logger.exception("field map rebuild failed; using stored map")
        fmap = field_map or {}

    if field_map_quality(fmap) < 1 and not fmap.get("logo_bbox"):
        raise ValueError(
            "Uploaded payslip has no detectable text fields to fill "
            "(scanned/image PDF?). Cannot pin-to-pin rewrite employee data."
        )

    org = getattr(getattr(payslip, "payroll_run", None), "organization", None)
    logo_bytes = _resolve_org_logo_bytes(org)

    filled, rewrite_count = fill_payslip_pdf(
        pdf_bytes,
        field_map=fmap,
        values=values,
        earning_amounts=earnings,
        deduction_amounts=deductions,
        logo_bytes=logo_bytes,
    )
    if rewrite_count < 1:
        raise ValueError(
            "Payslip fill produced no changes — refusing to return unmodified sample PDF"
        )
    logger.info(
        "Filled payslip PDF with %s rewrites (fields=%s earnings=%s deductions=%s)",
        rewrite_count,
        len(fmap.get("fields") or {}),
        len(fmap.get("earning_rows") or {}),
        len(fmap.get("deduction_rows") or {}),
    )
    return filled
