import json
from django.db import models, transaction
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django_tenants.utils import schema_context
from .models import CounselorStudentAssignment, ChatMessage, Conversation

class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]
        self.other_user_id = self.scope["url_route"]["kwargs"]["user_id"]

        if not self.user.is_authenticated:
            await self.close(code=4001)
            return

        # Resolve tenant schema from session (set during login)
        self.schema_name = self.scope.get("session", {}).get("_tenant_schema", "public")

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
        client_message_id = data.get("client_message_id")
        if not content:
            return
        
        # Per-message permission check: re-verify assignment is still active
        is_active = await self.check_assignment_active()
        if not is_active:
            await self.send(text_data=json.dumps({
                "error": "Assignment has been deactivated. You can no longer send messages."
            }))
            await self.close(code=4003)
            return

        # Persist message to database
        message = await self.save_message(content, client_message_id)
        if message is None:
            return

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
                "client_message_id": client_message_id,
                "server_seq": message.server_seq,
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event["message"],
            "sender_id": event["sender_id"],
            "sender_email": event["sender_email"],
            "timestamp": event["timestamp"],
            "message_id": event["message_id"],
            "server_seq": event["server_seq"],
            "client_message_id": event.get("client_message_id"),
        }))
    
    async def force_disconnect(self, event):
        await self.send(text_data=json.dumps({
            "error": "Consent revoked. This conversation has been deactivated."
        }))
        await self.close(code=4003)

    @database_sync_to_async
    def get_assignment(self, user_id, other_user_id):
        with schema_context(self.schema_name):
            try:
                return CounselorStudentAssignment.objects.get(
                    models.Q(counselor_id=user_id, student_id=other_user_id) |
                    models.Q(counselor_id=other_user_id, student_id=user_id),
                    is_active=True
                )
            except CounselorStudentAssignment.DoesNotExist:
                return None

    @database_sync_to_async
    def save_message(self, content, client_message_id=None):
        with schema_context(self.schema_name):
            if client_message_id:
                existing = ChatMessage.objects.filter(
                    client_message_id=client_message_id
                ).first()
                if existing:
                    return None
            with transaction.atomic():
                conversation = Conversation.objects.select_for_update().get(
                    pk=self.assignment.conversations.pk
                )
                last_seq = ChatMessage.objects.filter(
                    conversation=conversation
                ).order_by('-server_seq').values_list('server_seq', flat=True).first() or 0

                return ChatMessage.objects.create(
                    conversation=conversation,
                    sender=self.user,
                    content=content,
                    server_seq=last_seq + 1,
                    client_message_id=client_message_id,
                )

    @database_sync_to_async
    def check_assignment_active(self):
        with schema_context(self.schema_name):
            return CounselorStudentAssignment.objects.filter(
                pk=self.assignment.id, is_active=True
            ).exists()