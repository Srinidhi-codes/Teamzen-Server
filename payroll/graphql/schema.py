import strawberry
from typing import List

from users.graphql.queries import UserQuery
from users.graphql.mutations import UserMutation

@strawberry.type
class Salary:
    id: int
    employee_name: str
    amount: float

@strawberry.type
class Query(UserQuery):
    @strawberry.field
    def salaries(self) -> List[Salary]:
        return [
            Salary(id=1, employee_name="John", amount=50000),
        ]

@strawberry.type
class Mutation(UserMutation):
    pass

schema = strawberry.Schema(query=Query, mutation=Mutation)
