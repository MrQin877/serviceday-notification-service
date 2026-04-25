import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.core.cache import cache


class NotificationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        query_string = self.scope.get("query_string", b"").decode()
        params = dict(p.split("=") for p in query_string.split("&") if "=" in p)
        self.user_id    = params.get("user_id", "anonymous")
        self.user_group = f"user_{self.user_id}"
        self.all_group  = "broadcast_all"

        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.channel_layer.group_add(self.all_group,  self.channel_name)
        await self.accept()

        print(f"[WS] user_{self.user_id} connected — checking pending...")
        await self.deliver_pending()

    async def deliver_pending(self):
        cache_key = f"pending_notif_{self.user_id}"
        pending   = await sync_to_async(cache.get)(cache_key) or []

        print(f"[WS] Pending notifications for user_{self.user_id}: {len(pending)}")

        for notif in pending:
            print(f"[WS] Delivering pending: {notif}")
            await self.send(text_data=json.dumps(notif))

        if pending:
            await sync_to_async(cache.delete)(cache_key)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.user_group, self.channel_name)
        await self.channel_layer.group_discard(self.all_group,  self.channel_name)

    async def send_notification(self, event):
        await self.send(text_data=json.dumps(event["message"]))