import strawberry
from strawberry.types import Info
from strawberry.file_uploads import Upload
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
    has_seen_onboarding: bool | None = None
    has_seen_ai_onboarding: bool | None = None
    email_login_alerts: bool | None = None

@strawberry.input
class UserStatusInput:
    user_id: str
    is_active: bool

@strawberry.input
class CreateUserInput:
    email: str
    password: str
    first_name: str
    last_name: str
    role: str = "employee"
    organization_id: str | None = None
    department_id: str | None = None
    date_of_birth: str | None = None
    gender: str | None = None
    bank_account_number: str | None = None
    bank_ifsc_code: str | None = None
    pan_number: str | None = None
    aadhar_number: str | None = None
    uan_number: str | None = None
    phone_number: str | None = None
    designation_id: str | None = None
    office_location_id: str | None = None
    manager_id: str | None = None
    employment_type: str = "full_time"
    date_of_joining: str | None = None
    date_of_exit: str | None = None
    is_staff: bool = False
    is_verified: bool = False
    is_active: bool = True
    profile_picture: Upload | None = None

@strawberry.input
class UpdateUserInput:
    email: str
    first_name: str
    last_name: str
    role: str = "employee"
    organization_id: str | None = None
    department_id: str | None = None
    date_of_birth: str | None = None
    gender: str | None = None
    bank_account_number: str | None = None
    bank_ifsc_code: str | None = None
    pan_number: str | None = None
    aadhar_number: str | None = None
    uan_number: str | None = None
    phone_number: str | None = None
    designation_id: str | None = None
    office_location_id: str | None = None
    manager_id: str | None = None
    employment_type: str = "full_time"
    date_of_joining: str | None = None
    date_of_exit: str | None = None
    is_staff: bool = False
    is_verified: bool = False
    is_active: bool = True
    profile_picture: Upload | None = None

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
class EnrollFacePayload:
    success: bool = False
    error: str | None = None
    user: UserType | None = None

@strawberry.input
class EnrollFaceInput:
    descriptor: list[float]
    # Optional base64 data URL or raw base64 JPEG/PNG (without data: prefix ok)
    image_base64: str | None = None

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
    def enroll_face(self, info: Info, input: EnrollFaceInput) -> EnrollFacePayload:
        """Store client-computed face descriptor (+ optional enrollment selfie) for the current user."""
        import base64
        import re
        from django.core.files.base import ContentFile
        from django.utils import timezone

        user = info.context.request.user
        if not user.is_authenticated:
            return EnrollFacePayload(error="Not authenticated")

        if not input.descriptor or len(input.descriptor) < 32:
            return EnrollFacePayload(error="Invalid face descriptor. Please retry enrollment.")

        try:
            user.face_descriptor = [float(x) for x in input.descriptor]
            user.face_enrolled_at = timezone.now()

            if input.image_base64:
                raw = input.image_base64
                match = re.match(r"^data:image/(png|jpeg|jpg|webp);base64,(.+)$", raw, re.I | re.S)
                if match:
                    ext = "jpg" if match.group(1).lower() in ("jpeg", "jpg") else match.group(1).lower()
                    raw = match.group(2)
                else:
                    ext = "jpg"
                data = base64.b64decode(raw)
                filename = f"face_{user.id}.{ext}"
                user.face_enrollment_image.save(filename, ContentFile(data), save=False)

            user.save()
            return EnrollFacePayload(success=True, user=user)
        except Exception as e:
            return EnrollFacePayload(error=str(e))

    @strawberry.mutation
    def clear_face_enrollment(self, info: Info, user_id: str | None = None) -> EnrollFacePayload:
        """Clear own enrollment, or another user's if admin/HR."""
        from django.utils import timezone

        actor = info.context.request.user
        if not actor.is_authenticated:
            return EnrollFacePayload(error="Not authenticated")

        target = actor
        if user_id and str(user_id) != str(actor.id):
            if actor.role not in ["superadmin", "admin", "hr"]:
                return EnrollFacePayload(error="Not authorized")
            try:
                target = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return EnrollFacePayload(error="User not found")

        target.face_descriptor = None
        target.face_enrolled_at = None
        if target.face_enrollment_image:
            target.face_enrollment_image.delete(save=False)
            target.face_enrollment_image = None
        target.save()
        return EnrollFacePayload(success=True, user=target)

    @strawberry.mutation
    def create_user(self, info: Info, input: CreateUserInput) -> UserPayload:
        user = info.context.request.user
        # Only superadmin, admin, HR, or Manager can create users
        if not user.is_authenticated or user.role not in ["superadmin", "admin", "hr", "manager"]:
             return UserPayload(error="Not authorized")
        
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
            if input.office_location_id:
                new_user.office_location_id = input.office_location_id
            if input.manager_id:
                new_user.manager_id = input.manager_id
            if input.date_of_joining:
                new_user.date_of_joining = input.date_of_joining or None
            if input.date_of_exit:
                new_user.date_of_exit = input.date_of_exit or None
            if input.date_of_birth:
                new_user.date_of_birth = input.date_of_birth or None
            if input.phone_number:
                new_user.phone_number = input.phone_number
            if input.gender:
                new_user.gender = input.gender
            if input.bank_account_number:
                new_user.bank_account_number = input.bank_account_number
            if input.bank_ifsc_code:
                new_user.bank_ifsc_code = input.bank_ifsc_code
            if input.pan_number:
                new_user.pan_number = input.pan_number
            if input.aadhar_number:
                new_user.aadhar_number = input.aadhar_number
            if input.uan_number:
                new_user.uan_number = input.uan_number
            new_user.is_staff = bool(input.is_staff)
            new_user.is_verified = bool(input.is_verified)

            new_user.save()

            # Welcome email with temporary credentials (password not stored in notification row)
            try:
                from notifications.utils import notify_user

                manager_name = ""
                if new_user.manager_id:
                    mgr = User.objects.filter(id=new_user.manager_id).first()
                    if mgr:
                        manager_name = f"{mgr.first_name} {mgr.last_name}".strip()

                notify_user(
                    recipient_id=new_user.id,
                    verb="Welcome to Teamzen",
                    message=(
                        f"Your Teamzen account has been created. "
                        f"Sign in with {new_user.email} and the temporary password "
                        f"shared in this email."
                    ),
                    actor_id=user.id,
                    target_type="Welcome",
                    target_id=str(new_user.id),
                    level="personal",
                    notification_type="BOTH",
                    extra_context={
                        "temp_password": input.password,
                        "manager_name": manager_name,
                    },
                )
            except Exception:
                # User creation must succeed even if email delivery fails
                import logging
                logging.getLogger(__name__).exception(
                    "Welcome email failed for user_id=%s", new_user.id
                )

            return UserPayload(user=new_user, success=True)
        except Exception as e:
            return UserPayload(error=str(e))

    @strawberry.mutation
    def update_user(self, info: Info, user_id: str, input: UpdateUserInput) -> UserPayload:
        request_user = info.context.request.user
        if not request_user.is_authenticated or request_user.role not in ["superadmin", "admin", "hr", "manager"]:
            return UserPayload(error="Not authorized")
        
        try:
            # Fix: User is defined as get_user_model() at module level
            user_to_update = User.objects.get(id=user_id)
            
            # Map input fields to model fields
            for field, value in input.__dict__.items():
                # Handle empty strings for date fields by converting them to None
                if field in ['date_of_birth', 'date_of_joining', 'date_of_exit'] and value == "":
                    value = None
                
                # Handle empty strings for relational fields
                if field in ['department_id', 'designation_id', 'office_location_id', 'manager_id', 'organization_id'] and value == "":
                    value = None
                    
                if value is not None:
                    setattr(user_to_update, field, value)

            user_to_update.save()
            return UserPayload(user=user_to_update, success=True)
        except User.DoesNotExist:
            return UserPayload(error="User not found")
        except Exception as e:
            return UserPayload(error=str(e))

    @strawberry.mutation
    def user_status(self, info: Info, input: UserStatusInput) -> UserType:
        request_user = info.context.request.user
        if not request_user.is_authenticated or request_user.role not in ["superadmin", "admin", "hr", "manager"]:
            raise Exception("Not authorized")
        
        user_to_update = User.objects.get(id=input.user_id)
        user_to_update.is_active = input.is_active
        user_to_update.save(update_fields=['is_active'])
        return user_to_update
    @strawberry.mutation
    def update_login_location(self, info: Info, latitude: float, longitude: float) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        
        from users.models import UserLoginHistory
        from users.views import get_location_from_ip
        
        # Get the most recent login record for this user that lacks location
        latest_log = UserLoginHistory.objects.filter(user=user).order_by('-login_time').first()
        
        if latest_log:
            latest_log.latitude = latitude
            latest_log.longitude = longitude
            latest_log.location = get_location_from_ip(None, lat=latitude, lon=longitude)
            latest_log.save()
            return True
        return False