from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import CounselorStudentAssignment, Conversation


@receiver(post_save, sender=CounselorStudentAssignment)
def create_conversation(sender, instance, created, **kwargs):
    """Auto-create a Conversation when a new assignment is created."""
    if created:
        Conversation.objects.create(assignment=instance)