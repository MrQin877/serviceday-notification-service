"""
Topic 8 — RESTful API for Use Case 5 (Send Notifications and Reminders).
Using @api_view decorator style.

Endpoints:
    GET/POST         /api/v1/notifications/reminders/
    GET/PATCH/DELETE /api/v1/notifications/reminders/<id>/
    GET/POST         /api/v1/notifications/broadcasts/
    GET              /api/v1/notifications/logs/
    POST             /api/v1/notifications/trigger-reminders/
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Q

from .models import Broadcast, NotificationLog, ReminderConfig
from .serializers import (
    BroadcastSerializer,
    NotificationLogSerializer,
    ReminderConfigSerializer,
)


class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        if not request.user:
            return False
        groups = request.user.get('groups', [])
        return 'Administrator' in groups

# ── Reminders ─────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def reminder_list(request):
    """
    GET  → list all reminder intervals
    POST → add new reminder interval
    """
    if request.method == 'GET':
        configs    = ReminderConfig.objects.all()
        serializer = ReminderConfigSerializer(configs, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        serializer = ReminderConfigSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAdminUser])
def reminder_detail(request, pk):
    """
    GET    → view single config
    PATCH  → update is_active
    DELETE → remove config
    """
    try:
        config = ReminderConfig.objects.get(pk=pk)
    except ReminderConfig.DoesNotExist:
        return Response(
            {'error': 'Reminder config not found.'},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == 'GET':
        serializer = ReminderConfigSerializer(config)
        return Response(serializer.data)

    elif request.method == 'PATCH':
        serializer = ReminderConfigSerializer(config, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        config.delete()
        return Response(
            {'message': 'Reminder config deleted.'},
            status=status.HTTP_204_NO_CONTENT
        )


# ── Broadcasts ────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAdminUser])
def broadcast_list(request):
    """
    GET  → list broadcast history
    POST → send a new broadcast (Topic 10 — queued via Celery)
    """
    if request.method == 'GET':
        broadcasts = Broadcast.objects.annotate(
            sent_count   = Count('logs', filter=Q(logs__is_success=True)),
            failed_count = Count('logs', filter=Q(logs__is_success=False)),
        ).order_by('-sent_at')
        serializer = BroadcastSerializer(broadcasts, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        serializer = BroadcastSerializer(data=request.data)
        if serializer.is_valid():
            sent_by = request.user.get('username', 'Admin') if isinstance(request.user, dict) else request.user.username
            broadcast = serializer.save(sent_by=sent_by)
            # Topic 10 — hand off to Celery background task
            from .tasks import send_broadcast_task
            send_broadcast_task.delay(broadcast.id)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── Notification Logs ─────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAdminUser])
def notification_logs(request):
    """
    GET /api/v1/notifications/logs/
    Optional filter: ?notification_type=reminder
    """
    qs          = NotificationLog.objects.order_by('-sent_at')
    filter_type = request.query_params.get('notification_type')
    if filter_type:
        qs = qs.filter(notification_type=filter_type)
    serializer = NotificationLogSerializer(qs, many=True)
    return Response(serializer.data)

# ── Verification Emails ───────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])   # user-service calls this, no JWT yet
def send_verification_email(request):
    """
    POST /api/v1/notifications/send-verification/
    Called by user-service right after registration.

    Expected payload:
    {
        "email":             "ali@mail.com",
        "name":              "Ali",
        "verification_url":  "http://gateway/verify-email/abc123/"
    }
    """
    email            = request.data.get('email', '').strip()
    name             = request.data.get('name', '').strip()
    verification_url = request.data.get('verification_url', '').strip()

    if not all([email, name, verification_url]):
        return Response(
            {'error': 'email, name and verification_url are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    from .services.notification_service import NotificationService
    service = NotificationService()
    success = service.send_verification_email(email, name, verification_url)

    if success:
        return Response({'message': 'Verification email sent.'})
    return Response(
        {'error': 'Failed to send verification email.'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )

# ── Reset Password Emails ─────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])   # user-service calls this, no JWT yet
def send_reset_password_email(request):
    """
    POST /api/v1/notifications/send-reset-password/
    Called by user-service when forgot-password is triggered.

    Expected payload:
    {
        "email":     "ali@mail.com",
        "name":      "Ali",
        "reset_url": "http://gateway/reset-password/abc123/"
    }
    """
    email     = request.data.get('email', '').strip()
    name      = request.data.get('name', '').strip()
    reset_url = request.data.get('reset_url', '').strip()

    if not all([email, name, reset_url]):
        return Response(
            {'error': 'email, name and reset_url are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    from .services.notification_service import NotificationService
    service = NotificationService()
    success = service.send_reset_password_email(email, name, reset_url)

    if success:
        return Response({'message': 'Password reset email sent.'})
    return Response(
        {'error': 'Failed to send password reset email.'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )

# ── Registration Confirmation Emails ───────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])  # internal service call, no JWT
def send_confirmation_email(request):
    employee_id     = request.data.get('employee_id')
    ngo_id          = request.data.get('ngo_id')
    registration_id = request.data.get('registration_id')

    if not all([employee_id, ngo_id, registration_id]):
        return Response({'error': 'Missing fields.'}, status=status.HTTP_400_BAD_REQUEST)

    from .services.notification_service import NotificationService
    service = NotificationService()
    success = service.send_confirmation_email(employee_id, ngo_id, registration_id)

    if success:
        return Response({'message': 'Confirmation email sent.'})
    return Response({'error': 'Failed.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ── Registration Cancellation Emails ─────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def send_cancellation_email(request):
    employee_id = request.data.get('employee_id')
    ngo_id      = request.data.get('ngo_id')

    if not all([employee_id, ngo_id]):
        return Response({'error': 'Missing fields.'}, status=status.HTTP_400_BAD_REQUEST)

    from .services.notification_service import NotificationService
    service = NotificationService()
    success = service.send_cancellation_email(employee_id, ngo_id)

    if success:
        return Response({'message': 'Cancellation email sent.'})
    return Response({'error': 'Failed.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ── Registration Switch Emails ─────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def send_switch_email(request):
    employee_id = request.data.get('employee_id')
    old_ngo_id  = request.data.get('old_ngo_id')
    new_ngo_id  = request.data.get('new_ngo_id')

    if not all([employee_id, old_ngo_id, new_ngo_id]):
        return Response({'error': 'Missing fields.'}, status=status.HTTP_400_BAD_REQUEST)

    from .services.notification_service import NotificationService
    service = NotificationService()
    success = service.send_switch_email(employee_id, old_ngo_id, new_ngo_id)

    if success:
        return Response({'message': 'Switch email sent.'})
    return Response({'error': 'Failed.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ── Manual Reminder Trigger ───────────────────────────

@api_view(['POST'])
@permission_classes([IsAdminUser])
def trigger_reminders(request):
    """
    POST /api/v1/notifications/trigger-reminders/
    Manually trigger reminder emails for testing.
    """
    from .tasks import send_reminder_emails_task
    send_reminder_emails_task.delay()
    return Response(
        {'detail': 'Reminder task queued successfully.'},
        status=status.HTTP_202_ACCEPTED
    )