import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]

        # Accept the connection first to finalize the handshake and prevent timeouts
        await self.accept()

        if self.user.is_authenticated:
            self.group_name = f"user_{self.user.id}"

            try:
                await self.channel_layer.group_add(
                    self.group_name,
                    self.channel_name
                )
                await self.channel_layer.group_add(
                    'global_feed',
                    self.channel_name
                )
            except Exception as e:
                # Don't tear down the socket if Redis/channel layer is down
                print(f"[notifications] channel layer unavailable: {e}")
        else:
            # If not authenticated, close with application code 4401 (Unauthorized)
            # so clients know NOT to retry with the same rejected token in a tight loop.
            await self.close(code=4401)

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            try:
                await self.channel_layer.group_discard(
                    self.group_name,
                    self.channel_name
                )
                await self.channel_layer.group_discard(
                    'global_feed',
                    self.channel_name
                )
            except Exception:
                pass

    # Handle incoming messages from WebSocket clients
    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            data = json.loads(text_data)
            action = data.get("action") or data.get("type")
            if action == "view_post":
                post_id = data.get("post_id") or data.get("target_id")
                if post_id:
                    new_views = await self.increment_post_view(str(post_id))
                    if new_views is not None and hasattr(self, 'channel_layer') and self.channel_layer:
                        try:
                            await self.channel_layer.group_send(
                                "global_feed",
                                {
                                    "type": "send_notification",
                                    "message": {
                                        "level": "feed_update",
                                        "action": "post_viewed",
                                        "target_id": str(post_id),
                                        "views_count": new_views
                                    }
                                }
                            )
                        except Exception:
                            pass

            elif action == "draft_sync" and self.user.is_authenticated:
                scope = data.get("scope", "post")
                draft = data.get("draft") or {}
                await self.set_cached_draft(self.user.id, scope, draft)
                if hasattr(self, 'channel_layer') and self.channel_layer and hasattr(self, 'group_name'):
                    try:
                        await self.channel_layer.group_send(
                            self.group_name,
                            {
                                "type": "send_notification",
                                "message": {
                                    "level": "draft_sync",
                                    "action": "draft_updated",
                                    "scope": scope,
                                    "draft": draft,
                                    "sender_channel": self.channel_name
                                }
                            }
                        )
                    except Exception:
                        pass

            elif action == "get_draft" and self.user.is_authenticated:
                scope = data.get("scope", "post")
                cached = await self.get_cached_draft(self.user.id, scope)
                await self.send(text_data=json.dumps({
                    "level": "draft_sync",
                    "action": "draft_loaded",
                    "scope": scope,
                    "draft": cached
                }))

            elif action == "draft_clear" and self.user.is_authenticated:
                scope = data.get("scope", "post")
                await self.clear_cached_draft(self.user.id, scope)
                if hasattr(self, 'channel_layer') and self.channel_layer and hasattr(self, 'group_name'):
                    try:
                        await self.channel_layer.group_send(
                            self.group_name,
                            {
                                "type": "send_notification",
                                "message": {
                                    "level": "draft_sync",
                                    "action": "draft_cleared",
                                    "scope": scope,
                                    "sender_channel": self.channel_name
                                }
                            }
                        )
                    except Exception:
                        pass

        except Exception as e:
            print(f"[notifications] receive error: {e}")

    @database_sync_to_async
    def increment_post_view(self, post_id: str):
        from feed.models import Post
        from django.db.models import F
        try:
            post = Post.objects.filter(id=post_id).first()
            if post:
                post.views_count = F('views_count') + 1
                post.save(update_fields=['views_count'])
                post.refresh_from_db(fields=['views_count'])
                return post.views_count
        except Exception as e:
            print(f"[notifications] increment_post_view error: {e}")
        return None

    @database_sync_to_async
    def set_cached_draft(self, user_id: int, scope: str, draft: dict):
        from django.core.cache import cache
        key = f"teamzen_draft:{user_id}:{scope}"
        cache.set(key, draft, timeout=86400)

    @database_sync_to_async
    def get_cached_draft(self, user_id: int, scope: str):
        from django.core.cache import cache
        key = f"teamzen_draft:{user_id}:{scope}"
        return cache.get(key)

    @database_sync_to_async
    def clear_cached_draft(self, user_id: int, scope: str):
        from django.core.cache import cache
        key = f"teamzen_draft:{user_id}:{scope}"
        cache.delete(key)

    # Receive message from group
    async def send_notification(self, event):
        # Ignore echoing back to the exact sender socket for draft synchronization
        if event.get("message", {}).get("sender_channel") == self.channel_name:
            return
        await self.send(text_data=json.dumps(event["message"]))
