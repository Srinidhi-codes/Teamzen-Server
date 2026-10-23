import strawberry
from strawberry import auto
import strawberry.django
from typing import List, Optional
from feed.models import Post, Comment, PostLike, CommentLike, Poll, PollOption, PollVote
from users.graphql.types import UserType

@strawberry.django.type(PollOption)
class PollOptionType:
    id: auto
    text: auto
    votes_count: auto

    @strawberry.field
    def percentage(self) -> float:
        base = self.poll.total_voters() if self.poll.is_multiple_choice else self.poll.total_votes()
        if base == 0:
            return 0.0
        return round((self.votes_count / base) * 100, 1)

@strawberry.django.type(Poll)
class PollType:
    id: auto
    question: auto
    is_multiple_choice: auto
    created_at: auto
    expires_at: auto

    @strawberry.field
    def total_votes(self) -> int:
        return self.total_votes()

    @strawberry.field
    def total_voters(self) -> int:
        return self.total_voters()

    @strawberry.field
    def options(self) -> List[PollOptionType]:
        return list(self.options.all())

    @strawberry.field
    def user_voted_option_id(self, info) -> Optional[strawberry.ID]:
        user = info.context.request.user
        if not user.is_authenticated:
            return None
        vote = self.votes.filter(user=user).first()
        return strawberry.ID(str(vote.option_id)) if vote else None

    @strawberry.field
    def user_voted_option_ids(self, info) -> List[strawberry.ID]:
        user = info.context.request.user
        if not user.is_authenticated:
            return []
        return [strawberry.ID(str(v.option_id)) for v in self.votes.filter(user=user)]

    @strawberry.field
    def has_voted(self, info) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        return self.votes.filter(user=user).exists()

@strawberry.django.type(Post)
class PostType:
    id: auto
    title: auto
    content: auto
    media_urls: auto
    likes_count: auto
    comments_count: auto
    views_count: auto
    scheduled_for: auto
    created_at: auto
    updated_at: auto
    is_reported: auto
    report_reason: auto

    @strawberry.field
    def poll(self) -> Optional[PollType]:
        try:
            return self.poll
        except Exception:
            return None

    @strawberry.field
    def is_scheduled(self) -> bool:
        from django.utils import timezone
        return bool(self.scheduled_for and self.scheduled_for > timezone.now())
    
    @strawberry.field
    def author(self) -> UserType:
        return self.author

    @strawberry.field
    def reported_by(self) -> Optional[UserType]:
        return self.reported_by

    @strawberry.field
    def has_liked(self, info) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        annotated = getattr(self, 'user_has_liked', None)
        if annotated is not None:
            return bool(annotated)
        return PostLike.objects.filter(post=self, user=user).exists()

    @strawberry.field
    def comments(self, info, limit: int = 5, offset: int = 0) -> List['CommentType']:
        user = info.context.request.user
        from django.db.models import Exists, OuterRef
        qs = (
            self.comments.filter(parent=None)
            .select_related('author', 'reported_by')
            .order_by('-is_pinned', 'created_at')
        )
        if user.is_authenticated:
            qs = qs.annotate(
                user_has_liked=Exists(
                    CommentLike.objects.filter(comment=OuterRef('pk'), user=user)
                )
            )
        return list(qs[offset:offset+limit])

    @strawberry.field
    def top_level_comments_count(self) -> int:
        return self.comments.filter(parent=None).count()

    @strawberry.field
    def likers(self) -> List[UserType]:
        if hasattr(self, '_prefetched_objects_cache') and 'likes' in self._prefetched_objects_cache:
            return [like.user for like in self.likes.all()[:20]]
        return [like.user for like in self.likes.select_related('user').all().order_by('-created_at')[:20]]


@strawberry.django.type(Comment)
class CommentType:
    id: auto
    content: auto
    likes_count: auto
    is_pinned: auto
    is_reported: auto
    report_reason: auto
    created_at: auto
    updated_at: auto
    
    @strawberry.field
    def reported_by(self) -> Optional[UserType]:
        return self.reported_by

    @strawberry.field
    def author(self) -> UserType:
        return self.author
        
    @strawberry.field
    def post_id(self) -> str:
        return str(self.post_id)

    @strawberry.field
    def has_liked(self, info) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        annotated = getattr(self, 'user_has_liked', None)
        if annotated is not None:
            return bool(annotated)
        return CommentLike.objects.filter(comment=self, user=user).exists()

    @strawberry.field
    def replies(self, info) -> List['CommentType']:
        user = info.context.request.user
        from django.db.models import Exists, OuterRef
        qs = (
            self.replies.all()
            .select_related('author', 'reported_by')
            .order_by('created_at')
        )
        if user.is_authenticated:
            qs = qs.annotate(
                user_has_liked=Exists(
                    CommentLike.objects.filter(comment=OuterRef('pk'), user=user)
                )
            )
        return list(qs)

@strawberry.type
class PaginatedPostResponse:
    results: List[PostType]
    total: int
    page: int
    page_size: int

@strawberry.type
class PaginatedCommentResponse:
    results: List[CommentType]
    total: int
    page: int
    page_size: int

