from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
import strawberry

@strawberry.type
class AuthPayload:
    access: str
    refresh: str

@strawberry.type
class Mutation:
    @strawberry.mutation
    def login(self, info, email: str, password: str) -> AuthPayload:
        user = authenticate(username=email, password=password)
        if not user:
            raise Exception("Invalid credentials")

        refresh = RefreshToken.for_user(user)
        return AuthPayload(
            access=str(refresh.access_token),
            refresh=str(refresh),
        )
