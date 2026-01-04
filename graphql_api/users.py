import strawberry
from users.models import CustomUser

@strawberry.type
class UserType:
    id: int
    email: str
    first_name: str
    last_name: str
    role: str
