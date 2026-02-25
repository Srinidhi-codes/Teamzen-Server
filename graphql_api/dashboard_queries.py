import strawberry
from datetime import date, timedelta
from django.db.models import Count, Q
from django.utils import timezone
from typing import List, Optional
from users.models import CustomUser
from leaves.models import LeaveRequest, LeaveBalance
from attendance.models import AttendanceRecord
from organizations.models import Department
from notifications.models import Notification

@strawberry.type
class MonthlyStat:
    month: str
    value: int

@strawberry.type
class LeaveFluxStat:
    month: str
    approved: int
    rejected: int
    pending: int

@strawberry.type
class DepartmentStat:
    name: str
    value: int
    color: str

@strawberry.type
class ActivityStat:
    id: strawberry.ID
    user: str
    action: str
    time: str

@strawberry.type
class AdminDashboardStats:
    total_employees: int
    active_employees: int
    pending_leave_approvals: int
    today_attendance_rate: float
    employee_growth: List[MonthlyStat]
    department_distribution: List[DepartmentStat]
    leave_flux: List[LeaveFluxStat]
    recent_activities: List[ActivityStat]

@strawberry.type
class UserLeaveBalance:
    leave_type: str
    balance: float

@strawberry.type
class DayStatus:
    date: str
    day_str: str
    status: str

@strawberry.type
class UserDashboardStats:
    attendance_rate: float
    leave_balances: List[UserLeaveBalance]
    pending_requests_count: int
    days_present: int
    recent_activities: List[ActivityStat]
    last_7_days: List[DayStatus]
    attendance_trend: List[MonthlyStat]

@strawberry.type
class DashboardQuery:
    @strawberry.field
    def admin_dashboard_stats(self, info) -> AdminDashboardStats:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'hr', 'manager']:
            raise Exception("Unauthorized")

        # 1. Basic Stats
        total_employees = CustomUser.objects.filter(organization=user.organization).count()
        active_employees = CustomUser.objects.filter(organization=user.organization, is_active=True).count()
        pending_leaves = LeaveRequest.objects.filter(user__organization=user.organization, _status='pending').count()
        
        today = date.today()
        attendance_statuses = ['present', 'late_login', 'early_logout', 'half_day']
        present_today = AttendanceRecord.objects.filter(
            attendance_date=today, 
            status__in=attendance_statuses,
            user__organization=user.organization
        ).count()
        
        attendance_rate = (present_today / active_employees * 100) if active_employees > 0 else 0

        # 2. Employee Growth (Last 6 months)
        growth = []
        for i in range(5, -1, -1):
            target_date = today - timedelta(days=i*30)
            month_name = target_date.strftime("%b")
            count = CustomUser.objects.filter(
                organization=user.organization,
                created_at__lte=timezone.datetime(target_date.year, target_date.month, 28)
            ).count()
            growth.append(MonthlyStat(month=month_name, value=count))

        # 3. Department Distribution
        dept_dist = []
        colors = ["#4F46E5", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#06B6D4"]
        departments = Department.objects.filter(organization=user.organization)
        for i, dept in enumerate(departments):
            count = CustomUser.objects.filter(department=dept).count()
            dept_dist.append(DepartmentStat(
                name=dept.name, 
                value=count, 
                color=colors[i % len(colors)]
            ))

        # 4. Leave Flux
        flux = []
        for i in range(5, -1, -1):
            target_date = today - timedelta(days=i*30)
            month_name = target_date.strftime("%b")
            month_qs = LeaveRequest.objects.filter(
                user__organization=user.organization,
                from_date__month=target_date.month,
                from_date__year=target_date.year
            )
            flux.append(LeaveFluxStat(
                month=month_name,
                approved=month_qs.filter(_status='approved').count(),
                rejected=month_qs.filter(_status='rejected').count(),
                pending=month_qs.filter(_status='pending').count()
            ))

        # 5. Recent Activities
        activities = []
        # Combine recent leaves and user joins
        recent_leaves = LeaveRequest.objects.filter(user__organization=user.organization).order_by('-created_at')[:5]
        for l in recent_leaves:
            activities.append(ActivityStat(
                id=strawberry.ID(f"leave-{l.id}"),
                user=f"{l.user.first_name} {l.user.last_name}",
                action=f"requested {l.leave_type.name} leave",
                time=l.created_at.isoformat()
            ))

        return AdminDashboardStats(
            total_employees=total_employees,
            active_employees=active_employees,
            pending_leave_approvals=pending_leaves,
            today_attendance_rate=round(attendance_rate, 1),
            employee_growth=growth,
            department_distribution=dept_dist,
            leave_flux=flux,
            recent_activities=sorted(activities, key=lambda x: x.time, reverse=True)[:5]
        )

    @strawberry.field
    def user_dashboard_stats(self, info) -> UserDashboardStats:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Unauthorized")

        # 1. Attendance Rate (Last 30 records)
        attendance_statuses = ['present', 'late_login', 'early_logout', 'half_day']
        total_records = AttendanceRecord.objects.filter(user=user).count()
        present_records = AttendanceRecord.objects.filter(user=user, status__in=attendance_statuses).count()
        attendance_rate = (present_records / total_records * 100) if total_records > 0 else 0

        # 2. Leave Balances
        balances = []
        user_balances = LeaveBalance.objects.filter(user=user, year=date.today().year)
        for b in user_balances:
            balances.append(UserLeaveBalance(
                leave_type=b.leave_type.name,
                balance=float(b.get_available_balance())
            ))
        
        # 3. Pending Requests
        pending_count = LeaveRequest.objects.filter(user=user, _status='pending').count()

        # 4. Recent Activity (Attendance + Notifications)
        activities = []

        recent_attendance = AttendanceRecord.objects.filter(user=user)\
            .order_by('-attendance_date', '-login_time')[:5]

        for a in recent_attendance:
            dt = timezone.make_aware(
                timezone.datetime.combine(
                a.attendance_date,
                a.login_time or timezone.datetime.min.time()
            )
        )

        activities.append({
            "id": strawberry.ID(f"att-{a.id}"),
            "user": "You",
            "action": f"checked in at {a.login_time}" if a.login_time else "marked present",
            "time": dt
        })


        recent_notifs = Notification.objects.filter(recipient=user)\
            .order_by('-created_at')[:5]

        for n in recent_notifs:
            activities.append({
                "id": strawberry.ID(f"notif-{n.id}"),
                "user": n.actor.first_name if n.actor else "System",
                "action": n.message,
                "time": n.created_at
            })


        # ✅ Sort by datetime (newest first)
        activities.sort(key=lambda x: x["time"], reverse=True)

        # ✅ Take latest 5 & convert time to ISO string
        activities = [
            ActivityStat(
                id=item["id"],
                user=item["user"],
                action=item["action"],
                time=item["time"].isoformat()
            )
            for item in activities[:5]
        ]


        # 5. Last 7 Days Status
        last_7_days = []
        today = date.today()
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            day_str = d.strftime("%a")
            date_num = str(d.day)
            
            # 1. Base status
            status = 'absent'
            if d.weekday() >= 5: # Saturday/Sunday
                status = 'weekend'
            
            # 2. Check Record
            record = AttendanceRecord.objects.filter(user=user, attendance_date=d).first()
            if record:
                if record.status in ['present', 'late_login', 'early_logout', 'half_day']:
                    status = 'present'
                elif record.status == 'leave':
                    status = 'leave'
            else:
                # If it's today and no record yet, don't show as absent
                if d == today:
                    status = 'not_started'

            # 3. Check for Pending Corrections (Overrides absent/not_started)
            if status in ['absent', 'not_started']:
                from attendance.models import AttendanceCorrection
                has_pending = AttendanceCorrection.objects.filter(
                    attendance_record__user=user,
                    attendance_record__attendance_date=d,
                    _status='pending'
                ).exists()
                if has_pending:
                    status = 'pending'
            
            # 4. Check for Approved Leaves (Alternative)
            if status != 'present':
                on_leave = LeaveRequest.objects.filter(
                    user=user, 
                    _status='approved',
                    from_date__lte=d,
                    to_date__gte=d
                ).exists()
                if on_leave:
                    status = 'leave'
                
            last_7_days.append(DayStatus(
                date=date_num,
                day_str=day_str,
                status=status
            ))

        # 6. Attendance Trend (Last 6 Months)
        trend = []
        today = date.today()
        for i in range(5, -1, -1):
            # Calculate month and year for i months ago
            m = today.month - i
            y = today.year
            while m <= 0:
                m += 12
                y -= 1
            
            month_start = date(y, m, 1)
            # End of month: first day of next month minus one day
            next_m = m + 1
            next_y = y
            if next_m > 12:
                next_m = 1
                next_y += 1
            month_end = date(next_y, next_m, 1) - timedelta(days=1)
            
            # If current month, end at today
            if y == today.year and m == today.month:
                month_end = today

            month_name = month_start.strftime("%b")
            
            records = AttendanceRecord.objects.filter(
                user=user,
                attendance_date__range=[month_start, month_end]
            )
            total_days = (month_end - month_start).days + 1
            present_days = records.filter(status__in=attendance_statuses).count()
            
            rate = (present_days / total_days * 100) if total_days > 0 else 0
            trend.append(MonthlyStat(month=month_name, value=round(rate)))

        return UserDashboardStats(
            attendance_rate=round(attendance_rate, 1),
            leave_balances=balances,
            pending_requests_count=pending_count,
            days_present=present_records,
            recent_activities=activities,
            last_7_days=last_7_days,
            attendance_trend=trend
        )
