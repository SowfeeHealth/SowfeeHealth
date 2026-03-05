from django.contrib.contenttypes.models import ContentType
from .models import AuditLog


def get_client_ip(request):
    """Extract real IP, handling proxies."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_audit(request, action, obj, changes=None):
    """
    Create an audit log entry.

    Usage:
        log_audit(request, AuditLog.Action.CREATE, assignment)
        log_audit(request, AuditLog.Action.UPDATE, assignment, {"is_active": {"old": True, "new": False}})
    """
    AuditLog.objects.create(
        user=request.user,
        action=action,
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.pk,
        ip_address=get_client_ip(request),
        changes=changes or {},
    )