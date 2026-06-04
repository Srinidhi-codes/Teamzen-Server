from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
import strawberry

@strawberry.type
class AuthPayload:
    access: str | None = None
    refresh: str | None = None
    totp_required: bool = False
    temp_token: str | None = None

@strawberry.type
class Mutation:
    @strawberry.mutation
    def login(self, info, email: str, password: str) -> AuthPayload:
        user = authenticate(username=email, password=password)
        if not user:
            raise Exception("Invalid credentials")

        if user.is_totp_enabled:
            import uuid
            from django.core.cache import cache
            temp_token = str(uuid.uuid4())
            cache.set(f"temp_totp_session_{temp_token}", user.id, timeout=300)
            return AuthPayload(
                totp_required=True,
                temp_token=temp_token
            )

        refresh = RefreshToken.for_user(user)
        return AuthPayload(
            access=str(refresh.access_token),
            refresh=str(refresh),
        )
