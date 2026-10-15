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
            # If not authenticated, close AFTER accepting (standard practice to avoid hanging handshakes)
            await self.close()

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

    # Receive message from group
    async def send_notification(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps(event["message"]))
