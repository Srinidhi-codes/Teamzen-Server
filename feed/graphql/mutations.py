import strawberry
from typing import Optional, List
from strawberry.types import Info
from feed.models import Post, Comment, PostLike, CommentLike
from .types import PostType, CommentType
from users.models import CustomUser
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def broadcast_feed_update(action: str, target_id: str):
    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            async_to_sync(channel_layer.group_send)(
                "global_feed",
                {
                    "type": "send_notification",
                    "message": {
                        "level": "feed_update",
                        "action": action,
                        "target_id": target_id
                    }
                }
            )
        except Exception:
            pass

def notify_mentions(content: str, actor: CustomUser, target_type: str, target_id: str):
    import re
    from notifications.models import Notification
    
    # Extract IDs from format @[Name](id)
    mentioned_ids = re.findall(r"@\[[^\]]+\]\(([^)]+)\)", content)
    if not mentioned_ids:
        return
        
    for user_id in set(mentioned_ids):
        try:
            if str(user_id) == str(actor.id):
                continue # Don't notify self
                
            recipient = CustomUser.objects.filter(id=user_id).first()
            if recipient:
                Notification.objects.create(
                    recipient=recipient,
                    actor=actor,
                    verb=f"mentioned you in a {target_type}",
                    target_type=target_type.capitalize(),
                    target_id=target_id,
                    message=f"{actor.first_name} {actor.last_name} mentioned you in a {target_type}.",
                    level='personal'
                )
        except Exception as e:
            print(f"Error notifying mentioned user: {e}")

@strawberry.type
class FeedMutation:
    @strawberry.mutation
    def create_post(
        self,
        info: Info,
        content: str,
        title: str = "",
        media_b64: Optional[List[str]] = None
    ) -> PostType:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
            
        media_urls = []
        if media_b64:
            import base64
            import re
            import uuid
            import cloudinary.uploader
            
            for raw_b64 in media_b64:
                match = re.match(r"^data:image/(png|jpeg|jpg|webp|gif);base64,(.+)$", raw_b64, re.I | re.S)
                if match:
                    ext = "jpg" if match.group(1).lower() in ("jpeg", "jpg") else match.group(1).lower()
                    raw_data = match.group(2)
                else:
                    ext = "jpg"
                    raw_data = raw_b64
                    
                try:
                    data = base64.b64decode(raw_data)
                    public_id = f"post_{user.id}_{uuid.uuid4().hex[:8]}"
                    upload_result = cloudinary.uploader.upload(
                        data,
                        public_id=public_id,
                        folder="media/feed_posts",
                        resource_type="image",
                        overwrite=True,
                        format=ext,
                    )
                    if upload_result.get("secure_url"):
                        media_urls.append(upload_result.get("secure_url"))
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Cloudinary post upload failed: {e}")
            
        post = Post.objects.create(
            author=user,
            title=title,
            content=content,
            media_urls=media_urls
        )
        broadcast_feed_update("create_post", str(post.id))
        notify_mentions(content, user, "post", str(post.id))
        return post

    @strawberry.mutation
    def delete_post(self, info: Info, id: str) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
            
        post = Post.objects.filter(id=id, author=user).first()
        if post:
            post_id = str(post.id)
            post.delete()
            broadcast_feed_update("delete_post", post_id)
            return True
        return False

    @strawberry.mutation
    def update_post(self, info: Info, id: str, content: str, title: Optional[str] = None) -> PostType:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
            
        post = Post.objects.filter(id=id, author=user).first()
        if not post:
            raise Exception("Post not found or unauthorized")
            
        if title is not None:
            post.title = title
        post.content = content
        post.save(update_fields=['title', 'content', 'updated_at'])
        broadcast_feed_update("update_post", str(post.id))
        notify_mentions(content, user, "post", str(post.id))
        return post

    @strawberry.mutation
    def toggle_post_like(self, info: Info, post_id: str) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
            
        post = Post.objects.filter(id=post_id).first()
        if not post:
            return False
            
        like, created = PostLike.objects.get_or_create(post=post, user=user)
        if not created:
            like.delete()
            post.likes_count -= 1
            post.save(update_fields=['likes_count'])
            broadcast_feed_update("toggle_post_like", str(post.id))
            return False
        else:
            post.likes_count += 1
            post.save(update_fields=['likes_count'])
            if post.author != user:
                from notifications.models import Notification
                Notification.objects.create(
                    recipient=post.author,
                    actor=user,
                    verb="liked your post",
                    target_type="Post",
                    target_id=str(post.id),
                    message=f"{user.first_name} {user.last_name} liked your post.",
                    level='personal'
                )
            broadcast_feed_update("toggle_post_like", str(post.id))
            return True

    @strawberry.mutation
    def create_comment(
        self,
        info: Info,
        post_id: str,
        content: str,
        parent_id: Optional[str] = None
    ) -> CommentType:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
            
        post = Post.objects.filter(id=post_id).first()
        if not post:
            raise Exception("Post not found")
            
        parent = None
        if parent_id:
            parent = Comment.objects.filter(id=parent_id, post=post).first()
            if not parent:
                raise Exception("Parent comment not found")
                
        comment = Comment.objects.create(
            post=post,
            author=user,
            content=content,
            parent=parent
        )
        
        post.comments_count += 1
        post.save(update_fields=['comments_count'])
        
        if post.author != user:
            from notifications.models import Notification
            short_comment = (content[:50] + '...') if len(content) > 50 else content
            Notification.objects.create(
                recipient=post.author,
                actor=user,
                verb="commented on your post",
                target_type="Post",
                target_id=str(post.id),
                message=f"{user.first_name} {user.last_name} commented: '{short_comment}'",
                level='personal'
            )
        
        broadcast_feed_update("create_comment", str(post.id))
        notify_mentions(content, user, "comment", str(post.id))
        return comment

    @strawberry.mutation
    def delete_comment(self, info: Info, id: str) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
            
        comment = Comment.objects.filter(id=id, author=user).first()
        if comment:
            post = comment.post
            post_id = str(post.id)
            comment.delete()
            post.comments_count = max(0, post.comments_count - 1)
            post.save(update_fields=['comments_count'])
            broadcast_feed_update("delete_comment", post_id)
            return True
        return False

    @strawberry.mutation
    def update_comment(self, info: Info, id: str, content: str) -> CommentType:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
            
        comment = Comment.objects.filter(id=id, author=user).first()
        if not comment:
            raise Exception("Comment not found or unauthorized")
            
        comment.content = content
        comment.save(update_fields=['content', 'updated_at'])
        broadcast_feed_update("update_comment", str(comment.post.id))
        notify_mentions(content, user, "comment", str(comment.post.id))
        return comment

    @strawberry.mutation
    def toggle_comment_like(self, info: Info, comment_id: str) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
            
        comment = Comment.objects.filter(id=comment_id).first()
        if not comment:
            return False
            
        like, created = CommentLike.objects.get_or_create(comment=comment, user=user)
        if not created:
            like.delete()
            comment.likes_count -= 1
            comment.save(update_fields=['likes_count'])
            broadcast_feed_update("toggle_comment_like", str(comment.post.id))
            return False
        else:
            comment.likes_count += 1
            comment.save(update_fields=['likes_count'])
            broadcast_feed_update("toggle_comment_like", str(comment.post.id))
            return True

    @strawberry.mutation
    def view_post(self, info: Info, post_id: str) -> bool:
        post = Post.objects.filter(id=post_id).first()
        if not post:
            return False
        post.views_count += 1
        post.save(update_fields=['views_count'])
        return True
