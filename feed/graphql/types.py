import strawberry
from strawberry import auto
import strawberry.django
from typing import List, Optional
from feed.models import Post, Comment, PostLike, CommentLike
from users.graphql.types import UserType

@strawberry.django.type(Post)
class PostType:
    id: auto
    title: auto
    content: auto
    media_urls: auto
    likes_count: auto
    comments_count: auto
    created_at: auto
    updated_at: auto
    
    @strawberry.field
    def author(self) -> UserType:
        return self.author

    @strawberry.field
    def has_liked(self, info) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
        return PostLike.objects.filter(post=self, user=user).exists()

    @strawberry.field
    def comments(self, limit: int = 5, offset: int = 0) -> List['CommentType']:
        return self.comments.filter(parent=None).order_by('created_at')[offset:offset+limit]

    @strawberry.field
    def top_level_comments_count(self) -> int:
        return self.comments.filter(parent=None).count()

    @strawberry.field
    def likers(self) -> List[UserType]:
        return [like.user for like in self.likes.all().order_by('-created_at')[:20]]


@strawberry.django.type(Comment)
class CommentType:
    id: auto
    content: auto
    likes_count: auto
    created_at: auto
    updated_at: auto
    
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
        return CommentLike.objects.filter(comment=self, user=user).exists()

    @strawberry.field
    def replies(self) -> List['CommentType']:
        return self.replies.all().order_by('created_at')

@strawberry.type
class PaginatedPostResponse:
    results: List[PostType]
    total: int
    page: int
    page_size: int
