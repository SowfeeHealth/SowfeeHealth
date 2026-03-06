from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q,F
from django.shortcuts import get_object_or_404
from .serializers import AssignmentSerializer
from surveys.models import User
from .models import CounselorStudentAssignment, AuditLog, ChatMessage
from .utils import log_audit
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from surveys.serializers import UserSerializer

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def assignments(request):
    """
    GET  - List assignments
           Superuser: all assignments
           Institution admin: only their institution's assignments
           Counselor/Student: only their own
    POST - Create assignment (superuser or institution admin only)
           body: {"counselor": 1, "student": 2}
    """
    if request.method == 'GET':
        if request.user.is_superuser:
            return Response({'error': 'Superuser does not have access to assignments'}, status=status.HTTP_403_FORBIDDEN)
        elif request.user.role == User.Role.INSTITUTION_ADMIN:
            qs = CounselorStudentAssignment.objects.select_related('counselor', 'student').filter(
                Q(counselor__institution_details=request.user.institution_details) |
                Q(student__institution_details=request.user.institution_details)
            )
        else:
            qs = CounselorStudentAssignment.objects.select_related('counselor', 'student').filter(
                Q(counselor=request.user) | Q(student=request.user)
            )
        serializer = AssignmentSerializer(qs, many=True)
        log_audit(request, AuditLog.Action.ACCESS, request.user, 
                  {"resource": "assignments", "count": qs.count()})
        return Response(serializer.data)

    if request.method == 'POST':
        if request.user.role != User.Role.INSTITUTION_ADMIN:
            return Response({'error': 'Institution admin only'}, status=status.HTTP_403_FORBIDDEN)

        serializer = AssignmentSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save()
        log_audit(request, AuditLog.Action.CREATE, assignment, {
            "counselor_id": assignment.counselor_id,
            "student_id": assignment.student_id,
        })
        return Response(serializer.data, status=status.HTTP_201_CREATED)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def chat_messages(request, userId):
    """
    GET - List chat messages between user and current user
    """
    assignment = CounselorStudentAssignment.objects.filter(
        Q(counselor = request.user, student_id = userId) |
        Q(student = request.user, counselor_id = userId),
        is_active = True
    ).first()
    if not assignment:
        return Response({'error': 'No active assignment'}, status = status.HTTP_404_NOT_FOUND)
    try:
        conversation = assignment.conversations
    except Exception:
        return Response({'error': 'No conversation found'}, status=status.HTTP_404_NOT_FOUND)
    messages = ChatMessage.objects.filter(
        conversation = conversation
    ).order_by('server_seq').values(
        'id', 'sender__email', 'sender_id', 'content',
        'timestamp', 'server_seq', 'client_message_id', 'is_read'
    )
    return Response(list(messages))

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def counselors(request):
    if request.user.role != User.Role.INSTITUTION_ADMIN:
        return Response({'error': 'Admin only'}, status=status.HTTP_403_FORBIDDEN)
    
    qs = User.objects.filter(
        role=User.Role.COUNSELOR,
        institution_details=request.user.institution_details
    )
    serializer = UserSerializer(qs, many=True)
    return Response(serializer.data)

@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def assignment_detail(request, pk):
    """
    PATCH  - Deactivate/reactivate assignment
             body: {"is_active": false}
    DELETE - Remove assignment
    Superuser or institution admin only.
    """
    if request.user.role != User.Role.INSTITUTION_ADMIN:
        return Response({'error': 'Institution admin only'}, status=status.HTTP_403_FORBIDDEN)

    assignment = get_object_or_404(CounselorStudentAssignment, pk=pk)

    # Institution admin can only modify their own institution's assignments
    if (assignment.counselor.institution_details != request.user.institution_details and
            assignment.student.institution_details != request.user.institution_details):
        return Response({'error': 'Not your institution'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'PATCH':
        # Optimistic locking: client must send the version they read
        client_version = request.data.get('version')
        if client_version is not None and int(client_version) != assignment.version:
            return Response(
                {'error': 'Assignment was modified by another user. Please refresh and try again.'},
                status=status.HTTP_409_CONFLICT
            )
        
        # Capture old values for audit
        old_values = {field: getattr(assignment, field) for field in request.data if hasattr(assignment, field)}

        serializer = AssignmentSerializer(assignment, data=request.data, partial=True)
        if not serializer.is_valid():
            print(f"[ASSIGNMENT] patch validation error: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        assignment.version = F('version') + 1
        serializer.save()
        assignment.refresh_from_db()
        # Build changes diff
        changes = {}
        for field, old_val in old_values.items():
            new_val = getattr(assignment, field)
            if str(old_val) != str(new_val):
                changes[field] = {"old": str(old_val), "new": str(new_val)}

        log_audit(request, AuditLog.Action.UPDATE, assignment, changes)

        # Consent revocation: if assignment deactivated, kick WebSocket users
        if not assignment.is_active:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"chat_{assignment.id}",
                {"type": "force_disconnect"}
            )

        return Response(AssignmentSerializer(assignment).data)

    if request.method == 'DELETE':
        # Kick WebSocket users before deleting
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"chat_{assignment.id}",
            {"type": "force_disconnect"}
        )

        log_audit(request, AuditLog.Action.DELETE, assignment, {
            "counselor_id": assignment.counselor_id,
            "student_id": assignment.student_id,
        })
        assignment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)