import strawberry
from .auth import Mutation
from .users import UserType

@strawberry.type
class Query:
    @strawberry.field
    def me(self, info) -> UserType:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Not authenticated")
        return user

schema = strawberry.Schema(query=Query, mutation=Mutation)
