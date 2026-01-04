import strawberry
from strawberry.types import Info
from .types import UserType

@strawberry.type
class UserQuery:
    @strawberry.field
    def me(self, info: Info) -> UserType | None:
        user = info.context.request.user
        if not user.is_authenticated:
            return None
        return user
