from typing import Optional, List
import strawberry
from strawberry import auto
import strawberry.django
from strawberry.types import Info
from users.models import CustomUser, UserLoginHistory
from organizations.models import Department, Designation, OfficeLocation
from organizations.graphql.types import OfficeLocationType, OrganizationType, DepartmentType, DesignationType

@strawberry.type
class SalaryStructureSummaryType:
    id: strawberry.ID
    name: str

@strawberry.type
class SalarySummaryType:
    id: strawberry.ID
    annual_ctc: float
    effective_from: str
    is_active: bool
    salary_structure: SalaryStructureSummaryType

@strawberry.django.type(UserLoginHistory)
class UserLoginHistoryType:
    id: auto
    login_time: auto = strawberry.field(name="loginTime")
    ip_address: auto = strawberry.field(name="ipAddress")
    user_agent: auto = strawberry.field(name="userAgent")
    location: auto = strawberry.field(name="location")
    latitude: auto = strawberry.field(name="latitude")
    longitude: auto = strawberry.field(name="longitude")
    status: auto = strawberry.field(name="status")
    user: 'UserType' = strawberry.field(name="user")

@strawberry.django.type(CustomUser)
class UserType:
    id: strawberry.ID
    email: auto
    username: auto
    first_name: auto
    last_name: auto
    phone_number: auto
    role: auto
    is_active: auto
    is_verified: auto
    date_of_joining: str | None
    date_of_birth: str | None
    gender: auto
    profile_picture: auto
    
    employee_id: auto
    employment_type: auto
    manager: Optional['UserType']
    subordinates: List['UserType']
    organization: Optional['OrganizationType']
    
    # Relationships
    department: Optional['DepartmentType']
    designation: Optional['DesignationType']
    office_location: Optional['OfficeLocationType']
    
    # Financial
    bank_account_number: auto
    bank_ifsc_code: auto
    pan_number: auto
    aadhar_number: auto
    uan_number: auto
    
    @strawberry.field
    def salary_details(self) -> Optional[SalarySummaryType]:
        struct = self.salary_structures.filter(is_active=True).first()
        if not struct:
            return None
        return SalarySummaryType(
            id=str(struct.id),
            annual_ctc=float(struct.annual_ctc),
            effective_from=str(struct.effective_from),
            is_active=struct.is_active,
            salary_structure=SalaryStructureSummaryType(
                id=str(struct.salary_structure.id),
                name=struct.salary_structure.name
            )
        )

    has_seen_onboarding: auto
    has_seen_ai_onboarding: auto

    created_at: auto
    updated_at: auto

    @strawberry.field(name="loginHistory")
    def login_history(self, info: Info, limit: int = 10) -> List[UserLoginHistoryType]:
        user = info.context.request.user
        # Admins can see history for any user, others can only see their own
        if user.role not in ['admin', 'superadmin', 'hr'] and str(self.id) != str(user.id):
            return []
        
        return self.login_history.all()[:limit]

    @strawberry.field
    def attendance_rate(self) -> float:
        from attendance.models import AttendanceRecord
        total = AttendanceRecord.objects.filter(user=self).count()
        if total == 0:
            return 0.0
        
        present_count = AttendanceRecord.objects.filter(
            user=self, 
            status__in=['present', 'late_login', 'early_logout']
        ).count()
        half_days = AttendanceRecord.objects.filter(user=self, status='half_day').count()
        
        effective_present = present_count + (half_days * 0.5)
        return round((effective_present / total) * 100, 2)

    @strawberry.field
    def leave_balance(self) -> float:
        from leaves.models import LeaveBalance
        import datetime
        balances = LeaveBalance.objects.filter(user=self, year=datetime.date.today().year)
        total_available = sum(b.get_available_balance() for b in balances)
        return float(total_available)
        
    @strawberry.field
    def total_leave_entitlement(self) -> float:
        from leaves.models import LeaveBalance
        import datetime
        balances = LeaveBalance.objects.filter(user=self, year=datetime.date.today().year)
        total = sum(b.total_entitled + b.carried_forward for b in balances)
        return float(total)

    @strawberry.field
    def tenure_display(self) -> str:
        if not self.date_of_joining:
            return "N/A"
        from datetime import date
        today = date.today()
        joining = self.date_of_joining
        
        # Joining is a date object from models
        try:
            years = today.year - joining.year
            months = today.month - joining.month
            
            if months < 0:
                years -= 1
                months += 12
                
            if years > 0:
                return f"{years}y {months}m"
            return f"{months} months"
        except Exception:
            return "N/A"

    @strawberry.field
    def profile_picture_url(self) -> str | None:
        if self.profile_picture:
            return self.profile_picture.url
        return None
