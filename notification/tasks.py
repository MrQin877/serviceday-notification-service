"""
Topic 10 — Asynchronous Processing & Task Scheduling.
10.1 Redis as message queue (CELERY_BROKER_URL in settings.py)
10.2 Background email broadcast + scheduled reminders
"""

from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_broadcast_task(self, broadcast_id):
    """
    Topic 10.2 — Send broadcast emails in background.
    Called from API view so browser responds instantly.
    """
    from notification.models import Broadcast, NotificationLog
    from django.core.mail import send_mail
    from django.conf import settings

    try:
        broadcast = Broadcast.objects.get(id=broadcast_id)
    except Broadcast.DoesNotExist:
        return

    try:
        from notification.services.notification_service import NotificationService
        service = NotificationService()
        emails  = service.get_recipient_emails(broadcast.target)

        success_count = 0
        for email in emails:
            ok          = True
            fail_reason = ''
            try:
                send_mail(
                    subject        = broadcast.subject,
                    message        = broadcast.body,
                    from_email     = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@serviceday.com'),
                    recipient_list = [email],
                    fail_silently  = False,
                )
            except Exception as exc:
                ok          = False
                fail_reason = str(exc)

            NotificationLog.objects.create(
                recipient_email   = email,
                recipient_name    = '',
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

    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def send_reminder_emails_task():
    """
    Topic 10.2 — Scheduled daily reminder emails.
    Celery Beat triggers this every day at 08:00.
    Can also be triggered manually via API.
    """
    from notification.services.notification_service import NotificationService
    service = NotificationService()
    service.send_activity_reminders()
    logger.info("Reminder emails task completed.")