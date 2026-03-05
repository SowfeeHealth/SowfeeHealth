import json
from django.db import models
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import CounselorStudentAssignment, ChatMessage


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]
        self.other_user_id = self.scope["url_route"]["kwargs"]["user_id"]

        # Reject unauthenticated users
        if not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # Verify a valid assignment exists between the two users
        self.assignment = await self.get_assignment(self.user.id, self.other_user_id)
        if not self.assignment:
            await self.close(code=4003)
            return

        self.room_group_name = f"chat_{self.assignment.id}"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        content = data.get("message", "").strip()

        if not content:
            return

        # Persist message to database
        message = await self.save_message(content)

        # Broadcast to everyone in the room
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": content,
                "sender_id": self.user.id,
                "sender_email": self.user.email,
                "timestamp": message.timestamp.isoformat(),
                "message_id": message.id,
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event["message"],
            "sender_id": event["sender_id"],
            "sender_email": event["sender_email"],
            "timestamp": event["timestamp"],
            "message_id": event["message_id"],
        }))

    @database_sync_to_async
    def get_assignment(self, user_id, other_user_id):
        try:
            return CounselorStudentAssignment.objects.get(
                models.Q(counselor_id=user_id, student_id=other_user_id) |
                models.Q(counselor_id=other_user_id, student_id=user_id),
                is_active=True
            )
        except CounselorStudentAssignment.DoesNotExist:
            return None

    @database_sync_to_async
    def save_message(self, content):
        return ChatMessage.objects.create(
            conversation=self.assignment.conversations,
            sender=self.user,
            content=content
        )