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
            
        from django.utils import timezone
        from django.db.models import Q, Exists, OuterRef, Prefetch
        from feed.models import PostLike

        now = timezone.now()
        queryset = (
            Post.objects.all()
            .select_related(
                'author',
                'author__department',
                'author__designation',
                'author__organization',
                'reported_by'
            )
            .prefetch_related(
                Prefetch(
                    'likes',
                    queryset=PostLike.objects.select_related('user').order_by('-created_at')
                )
            )
            .annotate(
                user_has_liked=Exists(
                    PostLike.objects.filter(post=OuterRef('pk'), user=user)
                )
            )
            .order_by('-created_at')
        )

        # Normal users see only published posts + their own scheduled posts
        if user.role not in ['admin', 'superadmin']:
            queryset = queryset.filter(
                Q(scheduled_for__isnull=True) | Q(scheduled_for__lte=now) | Q(author=user)
            )

        if author_id:
            queryset = queryset.filter(author_id=author_id)
            
        paginated = get_paginated_results(queryset, page, page_size)
        return PaginatedPostResponse(**paginated)

    @strawberry.field
    def post(self, info: Info, id: str) -> Optional[PostType]:
        user = info.context.request.user
        if not user.is_authenticated:
            return None
        from django.db.models import Exists, OuterRef, Prefetch
        from feed.models import PostLike
        return (
            Post.objects.filter(id=id)
            .select_related(
                'author',
                'author__department',
                'author__designation',
                'author__organization',
                'reported_by'
            )
            .prefetch_related(
                Prefetch(
                    'likes',
                    queryset=PostLike.objects.select_related('user').order_by('-created_at')
                )
            )
            .annotate(
                user_has_liked=Exists(
                    PostLike.objects.filter(post=OuterRef('pk'), user=user)
                )
            )
            .first()
        )

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
            
        queryset = (
            Post.objects.filter(is_reported=True)
            .select_related(
                'author',
                'author__department',
                'author__designation',
                'author__organization',
                'reported_by'
            )
            .order_by('-updated_at')
        )
        paginated = get_paginated_results(queryset, page, page_size)
        return PaginatedPostResponse(**paginated)
