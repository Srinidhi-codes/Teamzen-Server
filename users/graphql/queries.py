import strawberry
from strawberry.types import Info
from .types import UserType
from users.models import CustomUser

@strawberry.type
class UserQuery:
    @strawberry.field
    def me(self, info: Info) -> UserType | None:
        user = info.context.request.user
        if not user.is_authenticated:
            return None
        return user

    @strawberry.field
    def all_users(self, info: Info) -> list[UserType]:
        user = info.context.request.user
        if user.role not in ['admin','hr','manager']:
            raise Exception("Unauthorized")
        
        if user.role == 'admin':
            return CustomUser.objects.all()
        if user.role in ['hr','manager']:
            return CustomUser.objects.filter(organization=user.organization)
