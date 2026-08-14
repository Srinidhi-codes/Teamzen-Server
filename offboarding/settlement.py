"""F&F settlement calculation helpers."""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone


TWOPLACES = Decimal("0.01")


def _q(value) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def get_monthly_ctc(user) -> Decimal:
    from payroll.models import EmployeeSalaryStructure

    structure = (
        EmployeeSalaryStructure.objects.filter(user=user, is_active=True)
        .order_by("-effective_from", "-id")
        .first()
    )
    if not structure or not structure.annual_ctc:
        return Decimal("0")
    return _q(Decimal(structure.annual_ctc) / Decimal(12))


def compute_pro_rata_salary(user, last_working_day: date | None) -> dict:
    """Pro-rata monthly CTC for days worked in the exit month through LWD."""
    monthly = get_monthly_ctc(user)
    if not last_working_day or monthly <= 0:
        return {
            "amount": Decimal("0"),
            "monthly_ctc": float(monthly),
            "days_worked": 0,
            "days_in_month": 0,
        }

    year, month = last_working_day.year, last_working_day.month
    days_in_month = monthrange(year, month)[1]
    # Count from 1st of month through LWD (inclusive)
    days_worked = last_working_day.day
    amount = _q(monthly * Decimal(days_worked) / Decimal(days_in_month))
    return {
        "amount": amount,
        "monthly_ctc": float(monthly),
        "days_worked": days_worked,
        "days_in_month": days_in_month,
    }


def compute_leave_encashment(user, as_of: date | None = None) -> dict:
    """Sum encashable leave balances for the current year."""
    from leaves.models import LeaveBalance

    year = (as_of or timezone.localdate()).year
    balances = (
        LeaveBalance.objects.filter(user=user, year=year, is_active=True)
        .select_related("leave_type")
    )
    monthly = get_monthly_ctc(user)
    daily = _q(monthly / Decimal(30)) if monthly > 0 else Decimal("0")

    lines = []
    total = Decimal("0")
    for bal in balances:
        lt = bal.leave_type
        if not lt.allow_encashment:
            continue
        available = Decimal(bal.get_available_balance())
        if available <= 0:
            continue
        if lt.encashment_rate is not None:
            rate = Decimal(lt.encashment_rate)
        else:
            rate = daily
        amount = _q(available * rate)
        total += amount
        lines.append(
            {
                "leave_type": lt.name,
                "days": float(available),
                "rate": float(rate),
                "amount": float(amount),
            }
        )
    return {"amount": _q(total), "lines": lines, "daily_rate": float(daily)}


def build_settlement_draft(
    offboarding,
    *,
    bonus_gratuity: Decimal | None = None,
    recoveries: Decimal | None = None,
    other_additions: Decimal | None = None,
    other_deductions: Decimal | None = None,
) -> dict:
    lwd = offboarding.last_working_day or offboarding.exit_date
    pro = compute_pro_rata_salary(offboarding.user, lwd)
    leave = compute_leave_encashment(offboarding.user, lwd)

    bonus = _q(bonus_gratuity if bonus_gratuity is not None else 0)
    rec = _q(recoveries if recoveries is not None else 0)
    add = _q(other_additions if other_additions is not None else 0)
    ded = _q(other_deductions if other_deductions is not None else 0)

    net = (
        pro["amount"]
        + leave["amount"]
        + bonus
        + add
        - rec
        - ded
    )
    return {
        "pro_rata_salary": pro["amount"],
        "leave_encashment": leave["amount"],
        "bonus_gratuity": bonus,
        "other_additions": add,
        "recoveries": rec,
        "other_deductions": ded,
        "net_payable": _q(net),
        "snapshot": {
            "pro_rata": {k: (float(v) if isinstance(v, Decimal) else v) for k, v in pro.items()},
            "leave_encashment": {
                "amount": float(leave["amount"]),
                "lines": leave["lines"],
                "daily_rate": leave["daily_rate"],
            },
            "last_working_day": lwd.isoformat() if lwd else None,
            "computed_at": timezone.now().isoformat(),
        },
    }
