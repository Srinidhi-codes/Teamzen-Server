import strawberry
from typing import List, Optional
from strawberry.types import Info
from feed.models import Post, Comment
from .types import PostType, PaginatedPostResponse
from graphql_utils.pagination import get_paginated_results

@strawberry.type
class FeedQuery:
    @strawberry.field
    def posts(
        self,
        info: Info,
        page: int = 1,
        page_size: int = 10,
        author_id: Optional[str] = None
    ) -> PaginatedPostResponse:
        user = info.context.request.user
        if not user.is_authenticated:
            return PaginatedPostResponse(results=[], total=0, page=page, page_size=page_size)
            
        queryset = Post.objects.all().order_by('-created_at')
        if author_id:
            queryset = queryset.filter(author_id=author_id)
            
        paginated = get_paginated_results(queryset, page, page_size)
        return PaginatedPostResponse(**paginated)

    @strawberry.field
    def post(self, info: Info, id: str) -> Optional[PostType]:
        user = info.context.request.user
        if not user.is_authenticated:
            return None
        return Post.objects.filter(id=id).first()

    @strawberry.field
    def reported_posts(
        self,
        info: Info,
        page: int = 1,
        page_size: int = 10
    ) -> PaginatedPostResponse:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            return PaginatedPostResponse(results=[], total=0, page=page, page_size=page_size)
            
        queryset = Post.objects.filter(is_reported=True).order_by('-updated_at')
        paginated = get_paginated_results(queryset, page, page_size)
        return PaginatedPostResponse(**paginated)
