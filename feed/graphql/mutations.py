import strawberry
from typing import Optional, List
from strawberry.types import Info
from feed.models import Post, Comment, PostLike, CommentLike
from .types import PostType, CommentType
from users.models import CustomUser
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def serialize_user(user) -> Optional[dict]:
    if not user:
        return None
    profile_pic = None
    if hasattr(user, 'profile_picture') and user.profile_picture:
        try:
            profile_pic = user.profile_picture.url
        except Exception:
            profile_pic = str(user.profile_picture)
    return {
        "id": str(user.id),
        "firstName": user.first_name,
        "lastName": user.last_name,
        "email": user.email,
        "profilePictureUrl": profile_pic,
    }

def serialize_post(post, viewer=None) -> dict:
    from django.utils import timezone
    is_scheduled = bool(post.scheduled_for and post.scheduled_for > timezone.now())
    has_liked = False
    if viewer and viewer.is_authenticated:
        has_liked = getattr(post, 'user_has_liked', None)
        if has_liked is None:
            has_liked = PostLike.objects.filter(post=post, user=viewer).exists()
    return {
        "id": str(post.id),
        "title": post.title or "",
        "content": post.content or "",
        "mediaUrls": post.media_urls or [],
        "likesCount": post.likes_count,
        "commentsCount": post.comments_count,
        "viewsCount": post.views_count,
        "scheduledFor": post.scheduled_for.isoformat() if post.scheduled_for else None,
        "isScheduled": is_scheduled,
        "createdAt": post.created_at.isoformat() if post.created_at else None,
        "updatedAt": post.updated_at.isoformat() if post.updated_at else None,
        "hasLiked": has_liked,
        "likers": [],
        "author": serialize_user(post.author),
    }

def serialize_comment(comment, viewer=None) -> dict:
    has_liked = False
    if viewer and viewer.is_authenticated:
        has_liked = CommentLike.objects.filter(comment=comment, user=viewer).exists()
    return {
        "id": str(comment.id),
        "content": comment.content or "",
        "likesCount": comment.likes_count,
        "createdAt": comment.created_at.isoformat() if comment.created_at else None,
        "updatedAt": comment.updated_at.isoformat() if comment.updated_at else None,
        "hasLiked": has_liked,
        "postId": str(comment.post_id),
        "parentId": str(comment.parent_id) if comment.parent_id else None,
        "author": serialize_user(comment.author),
        "replies": [],
    }

def broadcast_feed_update(action: str, target_id: str, payload: Optional[dict] = None):
    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            msg = {
                "level": "feed_update",
                "action": action,
                "target_id": str(target_id),
            }
            if payload:
                msg.update(payload)
                msg["data"] = payload

            async_to_sync(channel_layer.group_send)(
                "global_feed",
                {
                    "type": "send_notification",
                    "message": msg
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
        media_b64: Optional[List[str]] = None,
        scheduled_for: Optional[str] = None
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
                match = re.match(r"^data:([^;]+);base64,(.+)$", raw_b64, re.I | re.S)
                if match:
                    mime = match.group(1).lower()
                    raw_data = match.group(2)
                else:
                    mime = "image/jpeg"
                    raw_data = raw_b64
                    
                try:
                    data = base64.b64decode(raw_data)
                    uid = uuid.uuid4().hex[:8]
                    if "pdf" in mime:
                        public_id = f"post_{user.id}_{uid}.pdf"
                        upload_result = cloudinary.uploader.upload(
                            data,
                            public_id=public_id,
                            folder="media/feed_posts",
                            resource_type="raw",
                            overwrite=True,
                        )
                    else:
                        ext = mime.split("/")[-1].lower() if "/" in mime else "jpg"
                        if ext in ("jpeg", "jpg"):
                            ext = "jpg"
                        public_id = f"post_{user.id}_{uid}"
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
                    elif upload_result.get("url"):
                        media_urls.append(upload_result.get("url"))
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Cloudinary post upload failed: {e}", exc_info=True)
            
        parsed_scheduled_for = None
        if scheduled_for:
            import datetime
            try:
                parsed_scheduled_for = datetime.datetime.fromisoformat(scheduled_for.replace('Z', '+00:00'))
            except Exception as e:
                print(f"Error parsing scheduled_for timestamp: {e}")

        post = Post.objects.create(
            author=user,
            title=title,
            content=content,
            media_urls=media_urls,
            scheduled_for=parsed_scheduled_for
        )
        from django.utils import timezone
        is_future_scheduled = bool(parsed_scheduled_for and parsed_scheduled_for > timezone.now())
        if not is_future_scheduled:
            broadcast_feed_update("create_post", str(post.id), {
                "action": "post_created",
                "post": serialize_post(post, viewer=user)
            })
            notify_mentions(content, user, "post", str(post.id))
        return post

    @strawberry.mutation
    def delete_post(self, info: Info, id: str) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
            
        if user.role in ['admin', 'superadmin']:
            post = Post.objects.filter(id=id).first()
        else:
            post = Post.objects.filter(id=id, author=user).first()
            
        if post:
            post_id = str(post.id)
            post.delete()
            broadcast_feed_update("delete_post", post_id, {
                "action": "post_deleted",
                "post_id": post_id
            })
            return True
        return False

    @strawberry.mutation
    def update_post(
        self,
        info: Info,
        id: str,
        content: str,
        title: Optional[str] = None,
        media_urls: Optional[List[str]] = None
    ) -> PostType:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
            
        post = Post.objects.filter(id=id, author=user).first()
        if not post:
            raise Exception("Post not found or unauthorized")
            
        update_fields = ['content', 'updated_at']
        if title is not None:
            post.title = title
            update_fields.append('title')
        if media_urls is not None:
            post.media_urls = media_urls
            update_fields.append('media_urls')
            
        post.save(update_fields=update_fields)
        broadcast_feed_update("update_post", str(post.id), {
            "action": "post_updated",
            "post": serialize_post(post, viewer=user)
        })
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
            post.likes_count = max(0, post.likes_count - 1)
            post.save(update_fields=['likes_count'])
            broadcast_feed_update("toggle_post_like", str(post.id), {
                "action": "post_liked",
                "post_id": str(post.id),
                "likes_count": post.likes_count,
                "actor_id": str(user.id),
                "has_liked": False
            })
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
            broadcast_feed_update("toggle_post_like", str(post.id), {
                "action": "post_liked",
                "post_id": str(post.id),
                "likes_count": post.likes_count,
                "actor_id": str(user.id),
                "has_liked": True
            })
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
        
        broadcast_feed_update("create_comment", str(post.id), {
            "action": "comment_created",
            "post_id": str(post.id),
            "parent_id": str(parent.id) if parent else None,
            "comments_count": post.comments_count,
            "comment": serialize_comment(comment, viewer=user)
        })
        notify_mentions(content, user, "comment", str(post.id))
        return comment

    @strawberry.mutation
    def delete_comment(self, info: Info, id: str) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            return False
            
        if user.role in ['admin', 'superadmin']:
            comment = Comment.objects.filter(id=id).first()
        else:
            comment = Comment.objects.filter(id=id, author=user).first()
            
        if comment:
            post = comment.post
            post_id = str(post.id)
            comment_id = str(comment.id)
            comment.delete()
            post.comments_count = max(0, post.comments_count - 1)
            post.save(update_fields=['comments_count'])
            broadcast_feed_update("delete_comment", post_id, {
                "action": "comment_deleted",
                "post_id": post_id,
                "comment_id": comment_id,
                "comments_count": post.comments_count
            })
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
        broadcast_feed_update("update_comment", str(comment.post.id), {
            "action": "comment_updated",
            "post_id": str(comment.post.id),
            "comment": serialize_comment(comment, viewer=user)
        })
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
            comment.likes_count = max(0, comment.likes_count - 1)
            comment.save(update_fields=['likes_count'])
            broadcast_feed_update("toggle_comment_like", str(comment.post.id), {
                "action": "comment_liked",
                "post_id": str(comment.post.id),
                "comment_id": str(comment.id),
                "likes_count": comment.likes_count,
                "actor_id": str(user.id),
                "has_liked": False
            })
            return False
        else:
            comment.likes_count += 1
            comment.save(update_fields=['likes_count'])
            broadcast_feed_update("toggle_comment_like", str(comment.post.id), {
                "action": "comment_liked",
                "post_id": str(comment.post.id),
                "comment_id": str(comment.id),
                "likes_count": comment.likes_count,
                "actor_id": str(user.id),
                "has_liked": True
            })
            return True

    @strawberry.mutation
    def view_post(self, info: Info, post_id: str) -> bool:
        post = Post.objects.filter(id=post_id).first()
        if not post:
            return False
        post.views_count += 1
        post.save(update_fields=['views_count'])
        return True

    @strawberry.mutation
    def report_post(self, info: Info, post_id: str, reason: str) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        post = Post.objects.filter(id=post_id).first()
        if not post:
            return False
        
        post.is_reported = True
        post.report_reason = reason
        post.reported_by = user
        post.save(update_fields=['is_reported', 'report_reason', 'reported_by'])
        return True

    @strawberry.mutation
    def dismiss_report(self, info: Info, post_id: str) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
        post = Post.objects.filter(id=post_id).first()
        if not post:
            return False
            
        post.is_reported = False
        post.report_reason = None
        post.reported_by = None
        post.save(update_fields=['is_reported', 'report_reason', 'reported_by'])
        return True

    @strawberry.mutation
    def report_comment(self, info: Info, comment_id: str, reason: str) -> bool:
        user = info.context.request.user
        if not user.is_authenticated:
            raise Exception("Authentication required")
        comment = Comment.objects.filter(id=comment_id).first()
        if not comment:
            return False
        
        comment.is_reported = True
        comment.report_reason = reason
        comment.reported_by = user
        comment.save(update_fields=['is_reported', 'report_reason', 'reported_by'])
        return True

    @strawberry.mutation
    def dismiss_comment_report(self, info: Info, comment_id: str) -> bool:
        user = info.context.request.user
        if not user.is_authenticated or user.role not in ['admin', 'superadmin']:
            raise Exception("Unauthorized")
        comment = Comment.objects.filter(id=comment_id).first()
        if not comment:
            return False
            
        comment.is_reported = False
        comment.report_reason = None
        comment.reported_by = None
        comment.save(update_fields=['is_reported', 'report_reason', 'reported_by'])
        return True

