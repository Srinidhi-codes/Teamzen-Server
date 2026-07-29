"""
Payroll anomaly scanner — rule-based checks on completed PayrollRun payslips.
Returns a list of anomaly flags for admin review before publishing.
"""
from __future__ import annotations

import calendar
from collections import Counter
from decimal import Decimal
from typing import Any

from .models import (
    EmployeeSalaryStructure,
    Payslip,
    PayslipComponent,
    PayrollRun,
)


# ── Thresholds ──────────────────────────────────────────────────────────
HIGH_LOP_ABS = 5
HIGH_LOP_JUMP = 3
NET_SWING_PCT = Decimal("0.20")


def _prev_month(month: int, year: int) -> tuple[int, int]:
    if month == 1:
        return 12, year - 1
    return month - 1, year


def _user_label(user) -> str:
    name = f"{user.first_name} {user.last_name}".strip()
    return name or user.email


def _prior_payslip(user_id: int, month: int, year: int) -> Payslip | None:
    pm, py = _prev_month(month, year)
    return (
        Payslip.objects.filter(
            user_id=user_id,
            payroll_run__month=pm,
            payroll_run__year=py,
        )
        .select_related("payroll_run")
        .first()
    )


def scan_payroll_anomalies(payroll_run_id: int) -> list[dict[str, Any]]:
    """
    Scan all payslips in a completed PayrollRun and return anomaly flags.
    Each flag: { user_id, user_name, rule_id, severity, detail }
    severity: 'critical' | 'warning'
    """
    try:
        run = PayrollRun.objects.get(id=payroll_run_id)
    except PayrollRun.DoesNotExist:
        return []

    payslips = (
        Payslip.objects.filter(payroll_run=run)
        .select_related("user")
        .prefetch_related("components")
    )

    days_in_month = calendar.monthrange(run.year, run.month)[1]
    flags: list[dict[str, Any]] = []

    payslip_user_ids = set()

    for slip in payslips:
        user = slip.user
        payslip_user_ids.add(user.id)
        label = _user_label(user)
        prior = _prior_payslip(user.id, run.month, run.year)

        # ── HIGH_LOP ────────────────────────────────────────────────
        lop = float(slip.lop_days)
        if lop >= HIGH_LOP_ABS:
            flags.append({
                "user_id": user.id,
                "user_name": label,
                "rule_id": "HIGH_LOP",
                "severity": "warning",
                "detail": f"{lop:g} LOP days (threshold {HIGH_LOP_ABS})",
            })
        elif prior and (lop - float(prior.lop_days)) >= HIGH_LOP_JUMP:
            flags.append({
                "user_id": user.id,
                "user_name": label,
                "rule_id": "HIGH_LOP",
                "severity": "warning",
                "detail": (
                    f"LOP jumped {lop:g} vs prior {float(prior.lop_days):g} "
                    f"(+{lop - float(prior.lop_days):g})"
                ),
            })

        # ── ZERO_NET ────────────────────────────────────────────────
        if slip.net_pay <= 0:
            flags.append({
                "user_id": user.id,
                "user_name": label,
                "rule_id": "ZERO_NET",
                "severity": "critical",
                "detail": f"Net pay is {slip.net_pay}",
            })

        # ── NET_SWING ──────────────────────────────────────────────
        if prior and prior.net_pay and prior.net_pay > 0:
            delta = abs(slip.net_pay - prior.net_pay)
            pct = delta / prior.net_pay
            if pct >= NET_SWING_PCT:
                direction = "up" if slip.net_pay > prior.net_pay else "down"
                flags.append({
                    "user_id": user.id,
                    "user_name": label,
                    "rule_id": "NET_SWING",
                    "severity": "warning",
                    "detail": (
                        f"Net pay {direction} {pct * 100:.0f}%: "
                        f"{prior.net_pay} -> {slip.net_pay}"
                    ),
                })

        # ── DOUBLE_DEDUCTION ───────────────────────────────────────
        deduction_codes = [
            c.component_code
            for c in slip.components.all()
            if c.component_type == "deduction" and c.component_code not in ("ADJ", "ADV", "LOP")
        ]
        dupes = [code for code, cnt in Counter(deduction_codes).items() if cnt > 1]
        for code in dupes:
            flags.append({
                "user_id": user.id,
                "user_name": label,
                "rule_id": "DOUBLE_DEDUCTION",
                "severity": "critical",
                "detail": f"Component '{code}' deducted {Counter(deduction_codes)[code]} times",
            })

        # ── NEW_JOINER_PRORATA ─────────────────────────────────────
        joined = getattr(user, "date_joined", None)
        if joined:
            joined_date = joined.date() if hasattr(joined, "date") else joined
            if joined_date.year == run.year and joined_date.month == run.month:
                if float(slip.worked_days) < days_in_month and lop == 0:
                    flags.append({
                        "user_id": user.id,
                        "user_name": label,
                        "rule_id": "NEW_JOINER_PRORATA",
                        "severity": "warning",
                        "detail": (
                            f"Joined {joined_date}, worked {slip.worked_days}/{days_in_month} "
                            f"days but 0 LOP — check pro-rata"
                        ),
                    })

    # ── MISSING_STRUCTURE ──────────────────────────────────────────
    from django.contrib.auth import get_user_model
    User = get_user_model()
    org_employees = set(
        User.objects.filter(
            organization_id=run.organization_id,
            is_active=True,
            role="employee",
        ).values_list("id", flat=True)
    )
    active_structs = set(
        EmployeeSalaryStructure.objects.filter(
            user_id__in=org_employees,
            is_active=True,
        ).values_list("user_id", flat=True)
    )
    missing = org_employees - payslip_user_ids
    for uid in missing:
        if uid not in active_structs:
            try:
                u = User.objects.get(id=uid)
                label = _user_label(u)
            except User.DoesNotExist:
                label = f"User#{uid}"
            flags.append({
                "user_id": uid,
                "user_name": label,
                "rule_id": "MISSING_STRUCTURE",
                "severity": "warning",
                "detail": "Active employee with no salary structure — excluded from payroll",
            })

    return flags


def format_anomaly_digest(flags: list[dict[str, Any]], run: PayrollRun | None = None) -> str:
    """Format flags into a human-readable digest string."""
    if not flags:
        return "No payroll anomalies detected."

    header = "Payroll anomaly scan"
    if run:
        header += f" for {run.month}/{run.year}"

    critical = [f for f in flags if f["severity"] == "critical"]
    warnings = [f for f in flags if f["severity"] == "warning"]

    lines = [f"{header}: {len(flags)} issue(s) ({len(critical)} critical, {len(warnings)} warnings)"]
    for f in flags[:15]:
        tag = "!!" if f["severity"] == "critical" else " *"
        lines.append(f"{tag} [{f['rule_id']}] {f['user_name']}: {f['detail']}")
    if len(flags) > 15:
        lines.append(f"...and {len(flags) - 15} more.")

    return "\n".join(lines)
