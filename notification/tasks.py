"""
Topic 10 — Asynchronous Processing & Task Scheduling.
10.1 Redis as message queue (CELERY_BROKER_URL in settings.py)
10.2 Background email broadcast + scheduled reminders
"""

import logging
from celery import shared_task

from notification.services.notification_service import NotificationService
from notification.realtime import push_to_user, push_to_all
logger = logging.getLogger(__name__)


# ── Broadcast Emails (Topic 10.2) ─────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_broadcast_task(self, broadcast_id):
    from django.core.mail import send_mail
    from django.conf import settings
    from notification.models import Broadcast, NotificationLog
    from notification.services.notification_service import NotificationService

    try:
        broadcast = Broadcast.objects.get(id=broadcast_id)
    except Broadcast.DoesNotExist:
        logger.warning(f"[Broadcast] ID {broadcast_id} not found.")
        return

    try:
        service          = NotificationService()
        emails, user_map, user_id_map = service.get_recipient_emails(  # ← unpack tuple
            broadcast.target,
            ngo_ids=broadcast.ngo_ids
        )
    except Exception as exc:
        logger.error(f"[Broadcast] Failed to resolve recipients: {exc}")
        raise self.retry(exc=exc)

    if not emails:
        logger.info(f"[Broadcast] No recipients found for ID {broadcast_id}.")
        return
    
    already_sent = set(
        NotificationLog.objects.filter(
            broadcast=broadcast,
            is_success=True,
        ).values_list('recipient_email', flat=True)
    )

    success_count = 0
    from_email    = settings.EMAIL_HOST_USER

    for email in emails:
        if email in already_sent:
            continue

        name        = user_map.get(email, email.split('@')[0])  # ← get name
        ok          = True
        fail_reason = ''
        try:
            send_mail(
                subject        = broadcast.subject,
                message        = broadcast.body,
                from_email     = from_email,
                recipient_list = [email],
                fail_silently  = False,
            )
        except Exception as exc:
            ok          = False
            fail_reason = str(exc)
            logger.warning(f"[Broadcast] Failed to send to {email}: {exc}")

        NotificationLog.objects.create(
            recipient_email   = email,
            recipient_name    = name,   # ← use name
            notification_type = 'broadcast',
            subject           = broadcast.subject,
            body              = broadcast.body,
            is_success        = ok,
            fail_reason       = fail_reason,
            broadcast         = broadcast,
        )
        if ok:
            success_count += 1

    broadcast.recipients = success_count
    broadcast.save(update_fields=['recipients'])

    if broadcast.target == "all":
        # Only use push_to_all when truly broadcasting to everyone
        push_to_all(
            message    = f"📢 {broadcast.subject}",
            notif_type = "broadcast",
            event      = "broadcast",
        )
    else:
        # Push only to specific recipients using their user_id
        for email in emails:          # ← loops through ALL recipient emails
            uid = user_id_map.get(email)
            push_to_user(
                user_id    = uid,
                message    = f"📢 {broadcast.subject}",
                notif_type = "broadcast",
                event      = "broadcast",
            )
    logger.info(f"[Broadcast] ID {broadcast_id}: {success_count}/{len(emails)} sent.")


# ── Scheduled Reminder Emails (Topic 10.2) ────────────────────────────────────

@shared_task(name='notification.tasks.send_reminder_emails_task')
def send_reminder_emails_task():
    
    from notification.services.notification_service import NotificationService

    logger.info("[Reminders] Starting scheduled reminder email task.")

    try:
        service = NotificationService()
        service.send_activity_reminders()
        logger.info("[Reminders] Reminder emails task completed successfully.")
    except Exception as exc:
        logger.error(f"[Reminders] Reminder emails task failed: {exc}")
        raise