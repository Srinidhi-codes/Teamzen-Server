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
