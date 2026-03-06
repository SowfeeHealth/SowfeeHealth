from django.db import models
from surveys.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class CounselorStudentAssignment(models.Model):
    counselor = models.ForeignKey(User, related_name='assigned_students', on_delete=models.CASCADE)
    student = models.OneToOneField(User, related_name='assigned_counselor', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    version = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.counselor.email} <-> {self.student.email}"

class Conversation(models.Model):
    assignment = models.OneToOneField(CounselorStudentAssignment, on_delete=models.CASCADE, related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"Conversation: {self.assignment}"

class ChatMessage(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    server_seq = models.IntegerField()                         
    client_message_id = models.CharField(max_length=64, null=True, unique=True) 

    class Meta:
        ordering = ['server_seq']

    def __str__(self):
        return f"{self.sender.email}: {self.content[:50]}"

class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = 'create', 'Create'
        UPDATE = 'update', 'Update'
        DELETE = 'delete', 'Delete'
        ACCESS = 'access', 'Access'
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=255, choices = Action.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    # What object was affected (generic — works with any model)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey('content_type', 'object_id')

    # What changed
    changes = models.JSONField(default=dict, blank=True)
    # e.g. {"is_active": {"old": true, "new": false}}

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['content_type', 'object_id']),
        ]
    
    def __str__(self):
        return f"{self.user} {self.action} {self.content_type.model}#{self.object_id} at {self.timestamp}"