"""Build bank payout CSV files from a payroll run's payslips."""

from __future__ import annotations

import csv
import io
import re
from calendar import month_abbr
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

FORMATS = ("neft", "imps", "hdfc", "icici")

IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$", re.IGNORECASE)
ACCOUNT_RE = re.compile(r"^[0-9A-Za-z]{6,34}$")


@dataclass
class PayoutRow:
    beneficiary_name: str
    account_number: str
    ifsc: str
    amount: Decimal
    email: str
    employee_id: str
    remarks: str


@dataclass
class ExportResult:
    csv_text: str
    filename: str
    included: int
    skipped: int
    total_amount: Decimal


def _safe_name(user) -> str:
    name = f"{getattr(user, 'first_name', '') or ''} {getattr(user, 'last_name', '') or ''}".strip()
    if name:
        return re.sub(r"\s+", " ", name)
    return (getattr(user, "email", None) or "Employee").split("@")[0]


def _clean_account(raw: Any) -> str:
    return re.sub(r"[\s\-]", "", str(raw or "").strip())


def _clean_ifsc(raw: Any) -> str:
    return str(raw or "").strip().upper().replace(" ", "")


def _is_valid_bank(account: str, ifsc: str) -> bool:
    if not account or not ifsc:
        return False
    if not ACCOUNT_RE.match(account):
        return False
    if not IFSC_RE.match(ifsc):
        return False
    return True


def collect_payout_rows(payroll_run) -> tuple[list[PayoutRow], int]:
    """Return (valid rows, skipped count) for payslips with net_pay > 0."""
    remarks = f"Salary {month_abbr[payroll_run.month]} {payroll_run.year}"
    skipped = 0
    rows: list[PayoutRow] = []

    payslips = (
        payroll_run.payslips.select_related("user")
        .filter(net_pay__gt=0)
        .order_by("user__first_name", "user__last_name", "id")
    )
    for slip in payslips:
        user = slip.user
        account = _clean_account(getattr(user, "bank_account_number", None))
        ifsc = _clean_ifsc(getattr(user, "bank_ifsc_code", None))
        if not _is_valid_bank(account, ifsc):
            skipped += 1
            continue
        rows.append(
            PayoutRow(
                beneficiary_name=_safe_name(user),
                account_number=account,
                ifsc=ifsc,
                amount=Decimal(slip.net_pay),
                email=(getattr(user, "email", None) or "").strip(),
                employee_id=str(getattr(user, "employee_id", None) or user.id),
                remarks=remarks,
            )
        )
    return rows, skipped


def _write_csv(headers: list[str], data_rows: list[list[Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    for row in data_rows:
        writer.writerow(row)
    return buf.getvalue()


def _amount_str(amount: Decimal) -> str:
    return f"{amount.quantize(Decimal('0.01'))}"


def render_neft(rows: list[PayoutRow], *, payment_mode: str = "NEFT") -> str:
    headers = [
        "Beneficiary Name",
        "Account Number",
        "IFSC",
        "Amount",
        "Payment Mode",
        "Remarks",
        "Email",
        "Employee ID",
    ]
    data = [
        [
            r.beneficiary_name,
            r.account_number,
            r.ifsc,
            _amount_str(r.amount),
            payment_mode,
            r.remarks,
            r.email,
            r.employee_id,
        ]
        for r in rows
    ]
    return _write_csv(headers, data)


def render_hdfc(rows: list[PayoutRow]) -> str:
    """
    Simplified HDFC bulk payment-style CSV.
    Columns commonly expected in corporate netbanking bulk payee uploads.
    """
    headers = [
        "Beneficiary Code",
        "Beneficiary Name",
        "Instrument Amount",
        "Beneficiary Account Number",
        "IFSC",
        "Payment Type",
        "Payable Location",
        "Print Location",
        "Beneficiary Email",
        "Beneficiary Mobile",
        "Debit Account",
        "Narration",
    ]
    data = [
        [
            r.employee_id,
            r.beneficiary_name,
            _amount_str(r.amount),
            r.account_number,
            r.ifsc,
            "N",  # NEFT
            "",
            "",
            r.email,
            "",
            "",
            r.remarks,
        ]
        for r in rows
    ]
    return _write_csv(headers, data)


def render_icici(rows: list[PayoutRow]) -> str:
    """Simplified ICICI bulk payment-style CSV."""
    headers = [
        "Payment Product Code",
        "Account Number",
        "Beneficiary Name",
        "Amount",
        "Payment Date",
        "IFSC Code",
        "Narration",
        "Beneficiary Email",
        "Customer Reference No",
    ]
    data = [
        [
            "NEFT",
            r.account_number,
            r.beneficiary_name,
            _amount_str(r.amount),
            "",
            r.ifsc,
            r.remarks,
            r.email,
            r.employee_id,
        ]
        for r in rows
    ]
    return _write_csv(headers, data)


def build_bank_export(payroll_run, format_key: str) -> ExportResult:
    fmt = (format_key or "neft").strip().lower()
    if fmt not in FORMATS:
        raise ValueError(f"Unsupported format. Use one of: {', '.join(FORMATS)}")

    rows, skipped = collect_payout_rows(payroll_run)
    if not rows:
        raise ValueError(
            "No payable rows with valid bank account and IFSC. "
            "Add bank details on employee profiles and try again."
        )

    if fmt == "neft":
        csv_text = render_neft(rows, payment_mode="NEFT")
    elif fmt == "imps":
        csv_text = render_neft(rows, payment_mode="IMPS")
    elif fmt == "hdfc":
        csv_text = render_hdfc(rows)
    else:
        csv_text = render_icici(rows)

    period = f"{payroll_run.year}{payroll_run.month:02d}"
    filename = f"bank_payout_{fmt}_{period}_run{payroll_run.id}.csv"
    total = sum((r.amount for r in rows), Decimal("0"))
    return ExportResult(
        csv_text=csv_text,
        filename=filename,
        included=len(rows),
        skipped=skipped,
        total_amount=total,
    )
