import strawberry
from datetime import date, timedelta
from django.db.models import Count, Q
from django.utils import timezone
from typing import List, Optional
from users.models import CustomUser
from leaves.models import LeaveRequest, LeaveBalance, CompanyHoliday
from attendance.models import AttendanceRecord, AttendanceCorrection
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
class UpcomingEvent:
    id: str
    user: str
    profile_picture: Optional[str]
    type: str # 'birthday' or 'anniversary'
    date: str
    days_until: int

@strawberry.type
class UpcomingLeave:
    id: strawberry.ID
    user: str
    profile_picture: Optional[str]
    leave_type: str
    from_date: str
    to_date: str
    duration: float
    status: str

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
    upcoming_events: List[UpcomingEvent]
    upcoming_leaves: List[UpcomingLeave]
    wish_message: Optional[str]

@strawberry.type
class UserLeaveBalance:
    name: str
    leave_type: str
    balance: float
    total: float

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
    upcoming_events: List[UpcomingEvent]
    wish_message: Optional[str]

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
        # Ensure we use timezone aware datetimes for comparisons
        now = timezone.now()
        
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
            
            # Create an aware datetime for the pivot point
            pivot_dt = timezone.make_aware(timezone.datetime(target_date.year, target_date.month, 1))
            # Move to next month's start for simpler logic or just use end of month
            
            count = CustomUser.objects.filter(
                organization=user.organization,
                created_at__lte=pivot_dt + timedelta(days=30) # Roughly end of that month
            ).count()
            growth.append(MonthlyStat(month=month_name, value=count))

        # 3. Department Distribution
        dept_dist = []
        colors = ["#4F46E5", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#06B6D4"]
        departments = Department.objects.filter(organization=user.organization)
        for i, dept in enumerate(departments):
            count = CustomUser.objects.filter(department=dept, organization=user.organization).count()
            if count > 0: # Only show departments with employees
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
        # Join New Users
        recent_users = CustomUser.objects.filter(organization=user.organization).order_by('-created_at')[:5]
        for u in recent_users:
            activities.append(ActivityStat(
                id=strawberry.ID(f"user-{u.id}"),
                user=f"{u.first_name} {u.last_name}",
                action="joined the organization",
                time=u.created_at.isoformat()
            ))

        # Combine recent leaves
        recent_leaves = LeaveRequest.objects.filter(user__organization=user.organization).order_by('-created_at')[:5]
        for l in recent_leaves:
            activities.append(ActivityStat(
                id=strawberry.ID(f"leave-{l.id}"),
                user=f"{l.user.first_name} {l.user.last_name}",
                action=f"requested {l.leave_type.name} leave",
                time=l.created_at.isoformat()
            ))

        # Recent Attendance Corrections
        recent_corrections = AttendanceCorrection.objects.filter(
            attendance_record__user__organization=user.organization
        ).order_by('-created_at')[:5]
        for c in recent_corrections:
            formatted_date = c.attendance_record.attendance_date.strftime("%b %d, %Y")
            activities.append(ActivityStat(
                id=strawberry.ID(f"corr-{c.id}"),
                user=f"{c.requested_by.first_name} {c.requested_by.last_name}",
                action=f"requested attendance correction for {formatted_date}",
                time=c.created_at.isoformat()
            ))

        # 6. Upcoming Events (Birthdays & Anniversaries)
        upcoming_events = []
        today = date.today()
        
        # We look for events in the next 30 days
        all_users = CustomUser.objects.filter(organization=user.organization, is_active=True)
        for u in all_users:
            if u.date_of_birth:
                # Calculate next birthday
                try:
                    bday_this_year = u.date_of_birth.replace(year=today.year)
                except ValueError: # Leap year case
                    bday_this_year = u.date_of_birth.replace(year=today.year, day=28)
                
                if bday_this_year < today:
                    bday_next = bday_this_year.replace(year=today.year + 1)
                else:
                    bday_next = bday_this_year
                
                days_until = (bday_next - today).days
                if 0 <= days_until <= 30:
                    upcoming_events.append(UpcomingEvent(
                        id=f"bday-{u.id}",
                        user=f"{u.first_name} {u.last_name}",
                        profile_picture=u.profile_picture.url if u.profile_picture else None,
                        type="birthday",
                        date=bday_next.isoformat(),
                        days_until=days_until
                    ))
            
            if u.date_of_joining:
                # Calculate next anniversary
                try:
                    anniv_this_year = u.date_of_joining.replace(year=today.year)
                except ValueError: # Leap year case
                    anniv_this_year = u.date_of_joining.replace(year=today.year, day=28)
                
                if anniv_this_year < today:
                    anniv_next = anniv_this_year.replace(year=today.year + 1)
                else:
                    anniv_next = anniv_this_year
                
                days_until = (anniv_next - today).days
                # Don't show anniversary for users who joined this year
                if 0 <= days_until <= 30 and u.date_of_joining.year < today.year:
                    years = anniv_next.year - u.date_of_joining.year
                    upcoming_events.append(UpcomingEvent(
                        id=f"anniv-{u.id}",
                        user=f"{u.first_name} {u.last_name}",
                        profile_picture=u.profile_picture.url if u.profile_picture else None,
                        type="anniversary",
                        date=anniv_next.isoformat(),
                        days_until=days_until
                    ))

        # Holidays in next 30 days
        holidays = CompanyHoliday.objects.filter(
            organization=user.organization,
            holiday_date__range=[today, today + timedelta(days=30)]
        )
        for h in holidays:
            days_until = (h.holiday_date - today).days
            upcoming_events.append(UpcomingEvent(
                id=f"holiday-{h.id}",
                user=h.name,
                profile_picture=None,
                type="holiday",
                date=h.holiday_date.isoformat(),
                days_until=days_until
            ))

        # 7. Add anniversaries to activities
        for u in all_users:
            if u.date_of_joining and u.date_of_joining.month == today.month and u.date_of_joining.day == today.day and u.date_of_joining.year < today.year:
                years = today.year - u.date_of_joining.year
                activities.append(ActivityStat(
                    id=strawberry.ID(f"act-anniv-{u.id}"),
                    user=f"{u.first_name} {u.last_name}",
                    action=f"celebrates {years} year{'s' if years > 1 else ''} with the team!",
                    time=timezone.now().isoformat()
                ))

        # 8. Upcoming Leaves (Approved and Pending)
        upcoming_leaves = []
        leaves_qs = LeaveRequest.objects.filter(
            user__organization=user.organization,
            _status__in=['approved', 'pending'],
            to_date__gte=today
        ).select_related('user', 'leave_type').order_by('from_date')[:5]
        
        for l in leaves_qs:
            upcoming_leaves.append(UpcomingLeave(
                id=strawberry.ID(str(l.id)),
                user=f"{l.user.first_name} {l.user.last_name}",
                profile_picture=l.user.profile_picture.url if l.user.profile_picture else None,
                leave_type=l.leave_type.name,
                from_date=l.from_date.isoformat(),
                to_date=l.to_date.isoformat(),
                duration=float(l.duration_days),
                status=l._status
            ))

        return AdminDashboardStats(
            total_employees=total_employees,
            active_employees=active_employees,
            pending_leave_approvals=pending_leaves,
            today_attendance_rate=round(attendance_rate, 1),
            employee_growth=growth,
            department_distribution=dept_dist,
            leave_flux=flux,
            recent_activities=sorted(activities, key=lambda x: x.time, reverse=True)[:5],
            upcoming_events=sorted(upcoming_events, key=lambda x: x.days_until),
            upcoming_leaves=upcoming_leaves,
            wish_message=None # Admins get a generic dashboard, or we could add a greeting here too
        )

    @strawberry.field
    def user_dashboard_stats(self, info) -> UserDashboardStats:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Unauthorized")

        today = date.today()
        wish_message = None
        
        # Check for user's own birthday/anniversary
        if user.date_of_birth and user.date_of_birth.month == today.month and user.date_of_birth.day == today.day:
            wish_message = f"Happy Birthday, {user.first_name}! Wishing you a fantastic day ahead!"
        elif user.date_of_joining and user.date_of_joining.month == today.month and user.date_of_joining.day == today.day and user.date_of_joining.year < today.year:
            years = today.year - user.date_of_joining.year
            wish_message = f"Happy {years} Year Anniversary, {user.first_name}! Thank you for being an amazing part of our team!"

        # Upcoming Events for User Dashboard (Team mates)
        upcoming_events = []
        team_members = CustomUser.objects.filter(organization=user.organization, is_active=True).exclude(id=user.id)
        for u in team_members:
            # Birthday logic
            if u.date_of_birth:
                try:
                    bday_this_year = u.date_of_birth.replace(year=today.year)
                except ValueError: bday_this_year = u.date_of_birth.replace(year=today.year, day=28)
                
                if bday_this_year < today:
                    bday_next = bday_this_year.replace(year=today.year + 1)
                else:
                    bday_next = bday_this_year
                
                days_until = (bday_next - today).days
                if 0 <= days_until <= 30:
                    upcoming_events.append(UpcomingEvent(
                        id=f"bday-{u.id}",
                        user=f"{u.first_name} {u.last_name}",
                        profile_picture=u.profile_picture.url if u.profile_picture else None,
                        type="birthday",
                        date=bday_next.isoformat(),
                        days_until=days_until
                    ))
            
            # Joining logic
            if u.date_of_joining:
                try:
                    anniv_this_year = u.date_of_joining.replace(year=today.year)
                except ValueError: anniv_this_year = u.date_of_joining.replace(year=today.year, day=28)
                
                if anniv_this_year < today:
                    anniv_next = anniv_this_year.replace(year=today.year + 1)
                else:
                    anniv_next = anniv_this_year
                
                days_until = (anniv_next - today).days
                if 0 <= days_until <= 30 and u.date_of_joining.year < today.year:
                    upcoming_events.append(UpcomingEvent(
                        id=f"anniv-{u.id}",
                        user=f"{u.first_name} {u.last_name}",
                        profile_picture=u.profile_picture.url if u.profile_picture else None,
                        type="anniversary",
                        date=anniv_next.isoformat(),
                        days_until=days_until
                    ))

        # Holidays in next 30 days
        holidays = CompanyHoliday.objects.filter(
            organization=user.organization,
            holiday_date__range=[today, today + timedelta(days=30)]
        )
        for h in holidays:
            days_until = (h.holiday_date - today).days
            upcoming_events.append(UpcomingEvent(
                id=f"holiday-{h.id}",
                user=h.name,
                profile_picture=None,
                type="holiday",
                date=h.holiday_date.isoformat(),
                days_until=days_until
            ))

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
                name=b.leave_type.name,
                leave_type=b.leave_type.name,
                balance=float(b.get_available_balance()),
                total=float(b.total_entitled)
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
            formatted_date = a.attendance_date.strftime("%b %d, %Y")
            activities.append({
                "id": strawberry.ID(f"att-{a.id}"),
                "user": "You",
                "action": f"checked in at {a.login_time} on {formatted_date}" if a.login_time else f"marked present on {formatted_date}",
                "time": dt
            })


        # Recent Attendance Correction Requests (Proactive user action)
        recent_corrections = AttendanceCorrection.objects.filter(attendance_record__user=user)\
            .order_by('-created_at')[:5]
        for c in recent_corrections:
            formatted_date = c.attendance_record.attendance_date.strftime("%b %d, %Y")
            activities.append({
                "id": strawberry.ID(f"corr-{c.id}"),
                "user": "You",
                "action": f"requested attendance correction for {formatted_date}",
                "time": c.created_at
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
            if d.weekday() == 6: # Sunday only
                status = 'weekend'
            
            # 2. Check Record
            record = AttendanceRecord.objects.filter(user=user, attendance_date=d).first()
            if record:
                if record.status in ['present', 'late_login', 'early_logout', 'half_day']:
                    status = 'present'
                elif record.status == 'leave':
                    status = 'leave'
            else:
                # 2.5 Check for Holiday
                on_holiday = CompanyHoliday.objects.filter(
                    organization=user.organization,
                    holiday_date=d
                ).exists()
                if on_holiday:
                    status = 'leave'
                
                # If it's today and no record yet, don't show as absent
                elif d == today:
                    status = 'not_started'

            # 3. Check for Pending Corrections (Overrides absent/not_started/holiday??)
            # Actually, if they requested correction, they want it shown as pending.
            if status in ['absent', 'not_started', 'leave']:
                has_pending = AttendanceCorrection.objects.filter(
                    attendance_record__user=user,
                    attendance_record__attendance_date=d,
                    _status='pending'
                ).exists()
                if has_pending:
                    status = 'pending'
            
            # 4. Check for Approved Leaves (Alternative)
            if status not in ['present', 'pending']:
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
            attendance_trend=trend,
            upcoming_events=sorted(upcoming_events, key=lambda x: x.days_until),
            wish_message=wish_message
        )

    @strawberry.field
    def user_activities(self, info) -> List[ActivityStat]:
        user = info.context.request.user
        if not user.is_authenticated:
            return []

        activities = []
        # 1. Attendance Records
        recent_attendance = AttendanceRecord.objects.filter(user=user).order_by('-attendance_date', '-login_time')[:20]
        for a in recent_attendance:
            dt = timezone.make_aware(
                timezone.datetime.combine(
                    a.attendance_date,
                    a.login_time or timezone.datetime.min.time()
                )
            )
            formatted_date = a.attendance_date.strftime("%b %d, %Y")
            activities.append({
                "id": strawberry.ID(f"att-{a.id}"),
                "user": "You",
                "action": f"checked in at {a.login_time} on {formatted_date}" if a.login_time else f"marked present on {formatted_date}",
                "time": dt
            })

        # 2. Attendance Correction Requests
        recent_corrections = AttendanceCorrection.objects.filter(attendance_record__user=user)\
            .order_by('-created_at')[:20]
        for c in recent_corrections:
            formatted_date = c.attendance_record.attendance_date.strftime("%b %d, %Y")
            activities.append({
                "id": strawberry.ID(f"corr-{c.id}"),
                "user": "You",
                "action": f"requested attendance correction for {formatted_date}",
                "time": c.created_at
            })
        
        # 3. Leave Requests
        recent_leaves = LeaveRequest.objects.filter(user=user).order_by('-created_at')[:20]
        for l in recent_leaves:
            formatted_date = l.from_date.strftime("%b %d, %Y")
            activities.append({
                "id": strawberry.ID(f"leave-{l.id}"),
                "user": "You",
                "action": f"requested {l.leave_type.name} leave starting {formatted_date}",
                "time": l.created_at
            })

        # Sort and return
        activities.sort(key=lambda x: x["time"], reverse=True)
        return [
            ActivityStat(
                id=item["id"],
                user=item["user"],
                action=item["action"],
                time=item["time"].isoformat()
            )
            for item in activities[:50]
        ]
