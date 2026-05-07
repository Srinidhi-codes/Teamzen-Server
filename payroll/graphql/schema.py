import strawberry
from .queries import PayrollQuery
from .mutations import PayrollMutation

@strawberry.type
class Query(PayrollQuery):
    pass

@strawberry.type
class Mutation(PayrollMutation):
    pass

schema = strawberry.Schema(query=Query, mutation=Mutation)
