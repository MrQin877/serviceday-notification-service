"""
Topic 10 — Asynchronous Processing & Task Scheduling.
10.1 Redis as message queue (CELERY_BROKER_URL in settings.py)
10.2 Background email broadcast + scheduled reminders
"""

import logging
from celery import shared_task

logger = logging.getLogger(__name__)


# ── Broadcast Emails (Topic 10.2) ─────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_broadcast_task(self, broadcast_id):
    """
    Topic 10.2 — Send broadcast emails in the background.
    Called from the API view so the browser responds instantly
    while emails are delivered asynchronously via Celery + Redis.

    Retry-safe: already-sent recipients are skipped on retry
    to prevent duplicate emails.
    """
    from django.core.mail import send_mail
    from django.conf import settings
    from notification.models import Broadcast, NotificationLog
    from notification.services.notification_service import NotificationService

    # ── 1. Fetch broadcast record ─────────────────────────────────────────────
    try:
        broadcast = Broadcast.objects.get(id=broadcast_id)
    except Broadcast.DoesNotExist:
        logger.warning(f"[Broadcast] ID {broadcast_id} not found — skipping task.")
        return

    # ── 2. Resolve recipient emails ───────────────────────────────────────────
    try:
        service = NotificationService()
        emails  = service.get_recipient_emails(broadcast.target)
    except Exception as exc:
        logger.error(f"[Broadcast] Failed to resolve recipients for ID {broadcast_id}: {exc}")
        raise self.retry(exc=exc)

    if not emails:
        logger.info(f"[Broadcast] No recipients found for ID {broadcast_id}.")
        return

    # ── 3. Skip already-sent recipients (retry-safe) ──────────────────────────
    already_sent = set(
        NotificationLog.objects.filter(
            broadcast=broadcast,
            is_success=True,
        ).values_list('recipient_email', flat=True)
    )

    # ── 4. Send emails ────────────────────────────────────────────────────────
    success_count = 0
    from_email    = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@serviceday.com')

    for email in emails:
        if email in already_sent:
            logger.debug(f"[Broadcast] Skipping {email} — already sent.")
            continue

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

    # ── 5. Update sent count ──────────────────────────────────────────────────
    broadcast.recipients = success_count
    broadcast.save(update_fields=['recipients'])

    logger.info(
        f"[Broadcast] ID {broadcast_id} completed: "
        f"{success_count}/{len(emails)} emails sent successfully."
    )


# ── Scheduled Reminder Emails (Topic 10.2) ────────────────────────────────────

@shared_task(name='notification.tasks.send_reminder_emails_task')
def send_reminder_emails_task():
    """
    Topic 10.2 — Scheduled daily reminder emails.
    Celery Beat triggers this every day at 08:00 (Asia/Kuala_Lumpur).
    Can also be triggered manually via:
        POST /api/v1/notifications/trigger-reminders/

    The explicit task name ensures the Celery Beat schedule
    continues to work even if the file is refactored.
    """
    from notification.services.notification_service import NotificationService

    logger.info("[Reminders] Starting scheduled reminder email task.")

    try:
        service = NotificationService()
        service.send_activity_reminders()
        logger.info("[Reminders] Reminder emails task completed successfully.")
    except Exception as exc:
        logger.error(f"[Reminders] Reminder emails task failed: {exc}")
        raise