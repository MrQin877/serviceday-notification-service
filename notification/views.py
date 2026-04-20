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
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Q

from .models import Broadcast, NotificationLog, ReminderConfig
from .serializers import (
    BroadcastSerializer,
    NotificationLogSerializer,
    ReminderConfigSerializer,
)


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
            broadcast = serializer.save(sent_by=request.user.username)
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