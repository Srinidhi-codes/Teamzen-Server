import strawberry
from typing import Optional, List
from datetime import date, timedelta
from collections import defaultdict
from django.db.models import Count, Q, Sum, Avg
from django.db.models.functions import TruncMonth, TruncDate

from reports.auth import require_reports_access, resolve_report_org
from reports.services import clamp_range, month_starts, month_label
from reports.graphql.types import (
    ReportFilterInput,
    ReportKpiType,
    ReportSeriesPointType,
    ReportNamedValueType,
    WorkforceEmployeeRowType,
    WorkforceReportType,
    AttendanceEmployeeRowType,
    AttendanceReportType,
    LeaveRequestRowType,
    LeaveReportType,
    PayrollRunRowType,
    PayrollReportType,
)

DEPT_COLORS = [
    "oklch(0.55 0.14 250)",
    "oklch(0.6 0.14 150)",
    "oklch(0.7 0.15 70)",
    "oklch(0.55 0.2 25)",
    "oklch(0.55 0.12 280)",
    "oklch(0.6 0.1 220)",
    "oklch(0.65 0.12 320)",
]


def _users_qs(org, department_id=None):
    from users.models import CustomUser

    qs = CustomUser.objects.filter(organization=org).select_related(
        "department", "designation"
    )
    if department_id:
        qs = qs.filter(department_id=department_id)
    return qs


def _was_employed_on(user, day: date) -> bool:
    joined = user.date_of_joining
    if joined and joined > day:
        return False
    exited = user.date_of_exit
    if exited and exited < day:
        return False
    return True


@strawberry.type
class ReportsQuery:
    @strawberry.field
    def workforce_report(
        self, info, filters: Optional[ReportFilterInput] = None
    ) -> WorkforceReportType:
        user = info.context.request.user
        require_reports_access(user)
        f = filters or ReportFilterInput()
        org = resolve_report_org(user, f.organization_id)
        start, end = clamp_range(f.date_from, f.date_to, 180)

        qs = _users_qs(org, f.department_id)
        users = list(qs)

        active = [u for u in users if u.is_active]
        inactive = [u for u in users if not u.is_active]
        hires = [u for u in users if u.date_of_joining and start <= u.date_of_joining <= end]
        exits = [
            u
            for u in users
            if u.date_of_exit and start <= u.date_of_exit <= end
        ]

        # Monthly headcount at month end
        series = []
        headcounts = []
        for m in month_starts(start, end):
            # last day of month or end of range
            if m.month == 12:
                month_end = date(m.year, 12, 31)
            else:
                month_end = date(m.year, m.month + 1, 1) - timedelta(days=1)
            day = min(month_end, end)
            if day < start:
                continue
            count = sum(1 for u in users if _was_employed_on(u, day) and (u.is_active or (u.date_of_exit and u.date_of_exit >= day)))
            # Simpler: employed on day = joined <= day and (no exit or exit >= day)
            count = sum(1 for u in users if _was_employed_on(u, day))
            headcounts.append(count)
            m_hires = sum(
                1
                for u in users
                if u.date_of_joining
                and u.date_of_joining.year == m.year
                and u.date_of_joining.month == m.month
                and start <= u.date_of_joining <= end
            )
            m_exits = sum(
                1
                for u in users
                if u.date_of_exit
                and u.date_of_exit.year == m.year
                and u.date_of_exit.month == m.month
                and start <= u.date_of_exit <= end
            )
            series.append(
                ReportSeriesPointType(
                    label=month_label(m),
                    value=float(count),
                    secondary=float(m_hires),
                    tertiary=float(m_exits),
                )
            )

        avg_hc = (sum(headcounts) / len(headcounts)) if headcounts else 0
        turnover = round((len(exits) / avg_hc) * 100, 1) if avg_hc else 0.0

        dept_counts = defaultdict(int)
        for u in active:
            name = u.department.name if u.department_id else "Unassigned"
            dept_counts[name] += 1
        dept_breakdown = [
            ReportNamedValueType(name=n, value=float(v), color=DEPT_COLORS[i % len(DEPT_COLORS)])
            for i, (n, v) in enumerate(sorted(dept_counts.items(), key=lambda x: -x[1]))
        ]

        emp_type_counts = defaultdict(int)
        for u in active:
            emp_type_counts[u.employment_type or "unknown"] += 1
        emp_type_breakdown = [
            ReportNamedValueType(name=n.replace("_", " ").title(), value=float(v))
            for n, v in sorted(emp_type_counts.items(), key=lambda x: -x[1])
        ]

        employees = [
            WorkforceEmployeeRowType(
                id=str(u.id),
                name=f"{u.first_name} {u.last_name}".strip() or u.email,
                email=u.email,
                department=u.department.name if u.department_id else None,
                designation=u.designation.name if u.designation_id else None,
                employment_type=u.employment_type,
                date_of_joining=str(u.date_of_joining) if u.date_of_joining else None,
                date_of_exit=str(u.date_of_exit) if u.date_of_exit else None,
                is_active=u.is_active,
            )
            for u in sorted(users, key=lambda x: (not x.is_active, x.first_name or ""))
        ]

        kpis = [
            ReportKpiType(label="Active employees", value=str(len(active)), hint="Currently active"),
            ReportKpiType(label="Hires", value=str(len(hires)), hint="In selected range"),
            ReportKpiType(label="Exits", value=str(len(exits)), hint="In selected range"),
            ReportKpiType(
                label="Turnover rate",
                value=f"{turnover}%",
                hint="Exits ÷ avg headcount",
                trend="down" if turnover < 10 else "up",
            ),
        ]

        return WorkforceReportType(
            kpis=kpis,
            headcount_series=series,
            department_breakdown=dept_breakdown,
            employment_type_breakdown=emp_type_breakdown,
            employees=employees,
            hires=len(hires),
            exits=len(exits),
            turnover_rate=turnover,
            active_count=len(active),
            inactive_count=len(inactive),
        )

    @strawberry.field
    def attendance_report(
        self, info, filters: Optional[ReportFilterInput] = None
    ) -> AttendanceReportType:
        from attendance.models import AttendanceRecord

        user = info.context.request.user
        require_reports_access(user)
        f = filters or ReportFilterInput()
        org = resolve_report_org(user, f.organization_id)
        start, end = clamp_range(f.date_from, f.date_to, 30)

        users = _users_qs(org, f.department_id).filter(is_active=True)
        user_ids = list(users.values_list("id", flat=True))

        qs = AttendanceRecord.objects.filter(
            user_id__in=user_ids,
            attendance_date__gte=start,
            attendance_date__lte=end,
        ).select_related("user", "user__department", "office_location")
        if f.office_location_id:
            qs = qs.filter(office_location_id=f.office_location_id)

        records = list(qs)
        total = len(records) or 1
        present_statuses = {"present", "late_login", "early_logout"}
        present = sum(1 for r in records if r.status in present_statuses)
        late = sum(1 for r in records if r.status == "late_login")
        absent = sum(1 for r in records if r.status == "absent")
        leave = sum(1 for r in records if r.status == "leave")
        half = sum(1 for r in records if r.status == "half_day")

        # Daily series
        by_day = defaultdict(lambda: {"present": 0, "absent": 0, "late": 0})
        for r in records:
            key = r.attendance_date.isoformat()
            if r.status in present_statuses:
                by_day[key]["present"] += 1
            if r.status == "absent":
                by_day[key]["absent"] += 1
            if r.status == "late_login":
                by_day[key]["late"] += 1
        daily = [
            ReportSeriesPointType(
                label=k[5:],  # MM-DD
                value=float(v["present"]),
                secondary=float(v["absent"]),
                tertiary=float(v["late"]),
            )
            for k, v in sorted(by_day.items())
        ]

        status_breakdown = [
            ReportNamedValueType(name="Present", value=float(present), color=DEPT_COLORS[1]),
            ReportNamedValueType(name="Late", value=float(late), color=DEPT_COLORS[2]),
            ReportNamedValueType(name="Absent", value=float(absent), color=DEPT_COLORS[3]),
            ReportNamedValueType(name="Leave", value=float(leave), color=DEPT_COLORS[4]),
            ReportNamedValueType(name="Half day", value=float(half), color=DEPT_COLORS[0]),
        ]

        office_counts = defaultdict(int)
        for r in records:
            if r.status in present_statuses:
                name = r.office_location.name if r.office_location_id else "Unknown"
                office_counts[name] += 1
        office_breakdown = [
            ReportNamedValueType(name=n, value=float(v))
            for n, v in sorted(office_counts.items(), key=lambda x: -x[1])
        ]

        # Per-employee rollup
        per_user = defaultdict(lambda: {"present": 0, "late": 0, "absent": 0, "leave": 0, "half": 0, "total": 0, "user": None})
        for r in records:
            row = per_user[r.user_id]
            row["user"] = r.user
            row["total"] += 1
            if r.status in present_statuses:
                row["present"] += 1
            if r.status == "late_login":
                row["late"] += 1
            if r.status == "absent":
                row["absent"] += 1
            if r.status == "leave":
                row["leave"] += 1
            if r.status == "half_day":
                row["half"] += 1

        employees = []
        for uid, row in per_user.items():
            u = row["user"]
            t = row["total"] or 1
            rate = round((row["present"] + row["half"] * 0.5) / t * 100, 1)
            employees.append(
                AttendanceEmployeeRowType(
                    id=str(uid),
                    name=f"{u.first_name} {u.last_name}".strip() or u.email,
                    email=u.email,
                    department=u.department.name if u.department_id else None,
                    present_days=row["present"],
                    late_days=row["late"],
                    absent_days=row["absent"],
                    leave_days=row["leave"],
                    half_days=row["half"],
                    attendance_rate=rate,
                )
            )
        employees.sort(key=lambda e: e.attendance_rate)

        attendance_rate = round((present + half * 0.5) / total * 100, 1)
        kpis = [
            ReportKpiType(label="Attendance rate", value=f"{attendance_rate}%", hint="Present + half-day credit"),
            ReportKpiType(label="Late logins", value=str(late)),
            ReportKpiType(label="Absences", value=str(absent)),
            ReportKpiType(label="On leave", value=str(leave)),
        ]

        return AttendanceReportType(
            kpis=kpis,
            daily_series=daily,
            status_breakdown=status_breakdown,
            office_breakdown=office_breakdown,
            employees=employees,
        )

    @strawberry.field
    def leave_report(
        self, info, filters: Optional[ReportFilterInput] = None
    ) -> LeaveReportType:
        from leaves.models import LeaveRequest, LeaveBalance, LeaveType

        user = info.context.request.user
        require_reports_access(user)
        f = filters or ReportFilterInput()
        org = resolve_report_org(user, f.organization_id)
        start, end = clamp_range(f.date_from, f.date_to, 180)

        req_qs = LeaveRequest.objects.filter(
            user__organization=org,
            from_date__lte=end,
            to_date__gte=start,
        ).select_related("user", "user__department", "leave_type")
        if f.department_id:
            req_qs = req_qs.filter(user__department_id=f.department_id)

        requests = list(req_qs)
        by_status = defaultdict(int)
        by_type = defaultdict(float)
        for r in requests:
            by_status[r._status] += 1
            by_type[r.leave_type.name if r.leave_type_id else "Unknown"] += float(r.duration_days or 0)

        # Monthly flux
        flux = defaultdict(lambda: {"approved": 0, "rejected": 0, "pending": 0})
        for r in requests:
            key = month_label(date(r.from_date.year, r.from_date.month, 1))
            if r._status in ("approved", "rejected", "pending"):
                flux[key][r._status] += 1
        monthly_flux = [
            ReportSeriesPointType(
                label=lab,
                value=float(v["approved"]),
                secondary=float(v["rejected"]),
                tertiary=float(v["pending"]),
            )
            for lab, v in sorted(flux.items(), key=lambda x: x[0])
        ]

        type_breakdown = [
            ReportNamedValueType(name=n, value=v, color=DEPT_COLORS[i % len(DEPT_COLORS)])
            for i, (n, v) in enumerate(sorted(by_type.items(), key=lambda x: -x[1]))
        ]

        # Utilization from balances (current year)
        year = end.year
        bal_qs = LeaveBalance.objects.filter(
            user__organization=org, year=year
        ).select_related("leave_type")
        if f.department_id:
            bal_qs = bal_qs.filter(user__department_id=f.department_id)
        util_map = defaultdict(lambda: {"used": 0.0, "entitled": 0.0})
        for b in bal_qs:
            name = b.leave_type.name if b.leave_type_id else "Unknown"
            util_map[name]["used"] += float(b.used or 0)
            util_map[name]["entitled"] += float((b.total_entitled or 0) + (b.carried_forward or 0))
        utilization = [
            ReportNamedValueType(
                name=n,
                value=round((v["used"] / v["entitled"]) * 100, 1) if v["entitled"] else 0.0,
            )
            for n, v in sorted(util_map.items())
        ]

        def row(r):
            return LeaveRequestRowType(
                id=str(r.id),
                employee=f"{r.user.first_name} {r.user.last_name}".strip() or r.user.email,
                leave_type=r.leave_type.name if r.leave_type_id else "—",
                from_date=str(r.from_date),
                to_date=str(r.to_date),
                duration_days=float(r.duration_days or 0),
                status=r._status,
                department=r.user.department.name if r.user.department_id else None,
            )

        request_rows = [row(r) for r in sorted(requests, key=lambda x: x.from_date, reverse=True)[:200]]
        upcoming = [
            row(r)
            for r in requests
            if r._status == "approved" and r.to_date >= date.today()
        ]
        upcoming.sort(key=lambda x: x.from_date)

        total_days = sum(by_type.values())
        kpis = [
            ReportKpiType(label="Requests", value=str(len(requests))),
            ReportKpiType(label="Approved", value=str(by_status.get("approved", 0))),
            ReportKpiType(label="Pending", value=str(by_status.get("pending", 0))),
            ReportKpiType(label="Leave days", value=str(round(total_days, 1)), hint="Approved + pending volume"),
        ]

        return LeaveReportType(
            kpis=kpis,
            type_breakdown=type_breakdown,
            monthly_flux=monthly_flux,
            utilization=utilization,
            requests=request_rows,
            upcoming=upcoming[:50],
        )

    @strawberry.field
    def payroll_report(
        self, info, filters: Optional[ReportFilterInput] = None
    ) -> PayrollReportType:
        from payroll.models import PayrollRun, Payslip, SalaryAdvance

        user = info.context.request.user
        require_reports_access(user)
        f = filters or ReportFilterInput()
        org = resolve_report_org(user, f.organization_id)
        start, end = clamp_range(f.date_from, f.date_to, 365)

        runs = list(
            PayrollRun.objects.filter(organization=org)
            .order_by("year", "month")
        )
        # Filter by month falling in range (approx: first of month)
        filtered = []
        for r in runs:
            d = date(r.year, r.month, 1)
            if start.replace(day=1) <= d <= end:
                filtered.append(r)

        series = [
            ReportSeriesPointType(
                label=f"{r.month:02d}/{r.year}",
                value=float(r.total_gross or 0),
                secondary=float(r.total_deduction or 0),
                tertiary=float(r.total_net_pay or 0),
            )
            for r in filtered
        ]

        run_rows = [
            PayrollRunRowType(
                id=str(r.id),
                month=r.month,
                year=r.year,
                status=r.status,
                total_gross=float(r.total_gross or 0),
                total_deduction=float(r.total_deduction or 0),
                total_net_pay=float(r.total_net_pay or 0),
                label=date(r.year, r.month, 1).strftime("%b %Y"),
            )
            for r in reversed(filtered)
        ]

        # Dept cost from latest completed run payslips
        dept_cost = []
        latest = next((r for r in reversed(filtered) if r.status in ("completed", "published", "paid")), None)
        if not latest and filtered:
            latest = filtered[-1]
        if latest:
            slips = Payslip.objects.filter(payroll_run=latest).select_related("user", "user__department")
            costs = defaultdict(float)
            for s in slips:
                name = s.user.department.name if s.user.department_id else (s.department or "Unassigned")
                costs[name] += float(s.net_pay or 0)
            dept_cost = [
                ReportNamedValueType(name=n, value=round(v, 2), color=DEPT_COLORS[i % len(DEPT_COLORS)])
                for i, (n, v) in enumerate(sorted(costs.items(), key=lambda x: -x[1]))
            ]

        advances = SalaryAdvance.objects.filter(organization=org, status="active")
        adv_total = float(advances.aggregate(s=Sum("remaining_balance"))["s"] or 0)
        adv_count = advances.count()

        total_net = sum(float(r.total_net_pay or 0) for r in filtered)
        avg_net = round(total_net / len(filtered), 2) if filtered else 0
        emp_count = _users_qs(org, f.department_id).filter(is_active=True).count() or 1
        latest_net = float(latest.total_net_pay or 0) if latest else 0
        avg_per_emp = round(latest_net / emp_count, 2) if latest else 0

        kpis = [
            ReportKpiType(label="Payroll runs", value=str(len(filtered))),
            ReportKpiType(label="Latest net pay", value=f"₹{latest_net:,.0f}"),
            ReportKpiType(label="Avg cost / employee", value=f"₹{avg_per_emp:,.0f}"),
            ReportKpiType(label="Advances outstanding", value=f"₹{adv_total:,.0f}", hint=f"{adv_count} active"),
        ]

        return PayrollReportType(
            kpis=kpis,
            monthly_series=series,
            department_cost=dept_cost,
            runs=run_rows,
            advances_outstanding=adv_total,
            advances_count=adv_count,
        )
