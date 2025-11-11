import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async

# notifications/consumers.py - UPDATE WITH THESE METHODS
class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if user.is_anonymous:
            await self.close()
        else:
            # Join user-specific room for personal notifications
            await self.channel_layer.group_add(f"user_{user.id}", self.channel_name)
            # Join general notifications room
            await self.channel_layer.group_add("notifications", self.channel_name)
            await self.accept()

    async def disconnect(self, close_code):
        user = self.scope["user"]
        if not user.is_anonymous:
            await self.channel_layer.group_discard(f"user_{user.id}", self.channel_name)
            await self.channel_layer.group_discard("notifications", self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'mark_read':
            # Handle marking notifications as read via WebSocket
            await self.mark_notification_read(data.get('notification_id'))
    
    async def mark_notification_read(self, notification_id):
        from .models import Notification
        notification = await sync_to_async(Notification.objects.get)(id=notification_id)
        if notification.user == self.scope["user"]:
            await sync_to_async(notification.mark_as_read)()
    
    async def low_stock_alert(self, event):
        await self.send(text_data=json.dumps({
            "type": "low_stock",
            "data": event["notification"]
        }))
    
    async def new_ticket(self, event):
        # Only send to assigned user or department manager
        if (self.scope["user"].id == event["user_id"] or 
            self.scope["user"].is_superuser):
            await self.send(text_data=json.dumps({
                "type": "new_ticket",
                "data": event["ticket"]
            }))
    
    async def new_message(self, event):
        # Send to message recipient
        if self.scope["user"].id == event["recipient_id"]:
            await self.send(text_data=json.dumps({
                "type": "new_message", 
                "data": event["message"]
            }))