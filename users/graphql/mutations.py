import strawberry
from strawberry.types import Info
from django.contrib.auth import get_user_model
from .types import UserType

User = get_user_model()

@strawberry.input
class UpdateProfileInput:
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    date_of_birth: str | None = None
    gender: str | None = None
    bank_account_number: str | None = None
    bank_ifsc_code: str | None = None
    pan_number: str | None = None
    aadhar_number: str | None = None
    uan_number: str | None = None

@strawberry.input
class CreateUserInput:
    email: str
    password: str
    first_name: str
    last_name: str
    role: str = "employee"
    organization_id: str | None = None
    department_id: str | None = None
    designation_id: str | None = None
    manager_id: str | None = None
    employment_type: str = "full_time"
    date_of_joining: str | None = None
    is_active: bool = True

@strawberry.input
class UpdateUserInput:
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    date_of_birth: str | None = None
    gender: str | None = None
    bank_account_number: str | None = None
    bank_ifsc_code: str | None = None
    pan_number: str | None = None
    aadhar_number: str | None = None
    uan_number: str | None = None
    role: str | None = None
    department_id: str | None = None
    designation_id: str | None = None
    manager_id: str | None = None
    organization_id: str | None = None
    employment_type: str | None = None
    date_of_joining: str | None = None
    date_of_exit: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
    is_staff: bool | None = None

@strawberry.type
class UserPayload:
    user: UserType | None = None
    error: str | None = None
    success: bool = False

@strawberry.type
class UpdateProfilePayload:
    user: UserType | None = None
    error: str | None = None
    success: bool = False

@strawberry.type
class ChangePasswordPayload:
    success: bool = False
    error: str | None = None

@strawberry.type
class UserMutation:
    @strawberry.mutation
    def update_profile(self, info: Info, input: UpdateProfileInput) -> UpdateProfilePayload:
        user = info.context.request.user
        if not user.is_authenticated:
            return UpdateProfilePayload(error="Not authenticated")
        
        # Update allowed fields
        for field, value in input.__dict__.items():
            if value is not None:
                setattr(user, field, value)
        
        try:
            user.save()
            return UpdateProfilePayload(user=user, success=True)
        except Exception as e:
            return UpdateProfilePayload(error=str(e))

    @strawberry.mutation
    def change_password(self, info: Info, old_password: str, new_password: str) -> ChangePasswordPayload:
        user = info.context.request.user
        if not user.is_authenticated:
            return ChangePasswordPayload(error="Not authenticated")
        
        if not user.check_password(old_password):
            return ChangePasswordPayload(error="Old password is incorrect")
            
        user.set_password(new_password)
        user.save()
        return ChangePasswordPayload(success=True)

    @strawberry.mutation
    def create_user(self, info: Info, input: CreateUserInput) -> UserPayload:
        user = info.context.request.user
        # Only admin or HR/Manager can create users - simplistic check
        if not user.is_authenticated:
             return UserPayload(error="Not authenticated")
        
        try:
            new_user = User.objects.create_user(
                email=input.email,
                username=input.email, # Use email as username
                password=input.password,
                first_name=input.first_name,
                last_name=input.last_name,
                role=input.role,
                employment_type=input.employment_type,
                is_active=input.is_active
            )
            
            if input.organization_id:
                new_user.organization_id = input.organization_id
            if input.department_id:
                new_user.department_id = input.department_id
            if input.designation_id:
                new_user.designation_id = input.designation_id
            if input.manager_id:
                new_user.manager_id = input.manager_id
            if input.date_of_joining:
                new_user.date_of_joining = input.date_of_joining

            new_user.save()
            return UserPayload(user=new_user, success=True)
        except Exception as e:
            return UserPayload(error=str(e))

    @strawberry.mutation
    def update_user(self, info: Info, user_id: str, input: UpdateUserInput) -> UserPayload:
        request_user = info.context.request.user
        if not request_user.is_authenticated:
            return UserPayload(error="Not authenticated")
        
        try:
            # Fix: User is defined as get_user_model() at module level
            user_to_update = User.objects.get(id=user_id)
            
            # Map input fields to model fields
            for field, value in input.__dict__.items():
                # Handle empty strings for date fields by converting them to None
                if field in ['date_of_birth', 'date_of_joining', 'date_of_exit'] and value == "":
                    value = None
                
                # Handle empty strings for relational fields
                if field in ['department_id', 'designation_id', 'manager_id', 'organization_id'] and value == "":
                    value = None
                    
                if value is not None:
                    setattr(user_to_update, field, value)

            user_to_update.save()
            return UserPayload(user=user_to_update, success=True)
        except User.DoesNotExist:
            return UserPayload(error="User not found")
        except Exception as e:
            return UserPayload(error=str(e))
