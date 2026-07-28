import json
from channels.generic.websocket import AsyncWebsocketConsumer

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
            except Exception:
                pass

    # Receive message from group
    async def send_notification(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps(event["message"]))
