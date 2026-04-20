"""
Notification Service — microservice version.
Key difference from monolithic:
- No direct FK to NGO or Registration models
- Calls ngo-service and registration-service APIs instead
- Stores ngo_id + ngo_name as plain fields in NotificationLog
"""

from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from notification.middleware import track_notification
from django.db.models import Count, Q
import requests
import logging

logger = logging.getLogger(__name__)


class NotificationService:

    # ── Core email sender ─────────────────────────────

    def _send_email(
        self,
        recipient_email,
        recipient_name,
        subject,
        body,
        notif_type,
        ngo_id=None,
        ngo_name='',
        broadcast=None,
    ):
        from notification.models import NotificationLog

        success     = True
        fail_reason = ''

        try:
            send_mail(
                subject        = subject,
                message        = body,
                from_email     = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@serviceday.com'),
                recipient_list = [recipient_email],
                fail_silently  = False,
            )
        except Exception as e:
            success     = False
            fail_reason = str(e)

        log = NotificationLog.objects.create(
            recipient_email   = recipient_email,
            recipient_name    = recipient_name,
            notification_type = notif_type,
            subject           = subject,
            body              = body,
            is_success        = success,
            fail_reason       = fail_reason,
            ngo_id            = ngo_id,
            ngo_name          = ngo_name,
            broadcast         = broadcast,
        )

        track_notification(log)
        return success

    # ── Broadcast ─────────────────────────────────────

    def send_broadcast(self, subject, body, recipient_emails, sent_by="Admin", target="all"):
        from notification.models import Broadcast

        broadcast = Broadcast.objects.create(
            subject    = subject,
            body       = body,
            target     = target,
            sent_by    = sent_by,
            recipients = 0,
        )

        success_count = 0
        for email in recipient_emails:
            if self._send_email(
                email, "", subject, body, "broadcast",
                broadcast=broadcast,
            ):
                success_count += 1

        broadcast.recipients = success_count
        broadcast.save(update_fields=['recipients'])
        return success_count

    # ── Reminder engine ───────────────────────────────
    # calls registration-service API to get registrations
    # calls ngo-service API to get NGO details

    def send_activity_reminders(self):
        from notification.models import ReminderConfig

        today = timezone.now().date()

        for config in ReminderConfig.objects.filter(is_active=True):
            target_date = today + timedelta(days=config.interval_days)

            # call registration-service to get registrations for target date
            try:
                response = requests.get(
                    f"{settings.REGISTRATION_SERVICE_URL}/api/v1/registrations/",
                    params={'service_date': target_date.isoformat()},
                )
                registrations = response.json().get('results', [])
            except Exception as e:
                logger.error(f"Failed to fetch registrations: {e}")
                continue

            for reg in registrations:
                employee_email = reg.get('employee_email', '')
                employee_name  = reg.get('employee_name', '')
                ngo_name       = reg.get('ngo_name', '')
                ngo_id         = reg.get('ngo_id')
                service_date   = reg.get('service_date', '')
                start_time     = reg.get('start_time', '')
                end_time       = reg.get('end_time', '')

                subject = f"Reminder: {ngo_name} in {config.interval_days} day(s)"
                body    = f"""Hi {employee_name},

Reminder for upcoming activity:

Activity : {ngo_name}
Date     : {service_date}
Time     : {start_time} – {end_time}

— ServiceDay Team
"""
                self._send_email(
                    employee_email,
                    employee_name,
                    subject,
                    body,
                    "reminder",
                    ngo_id   = ngo_id,
                    ngo_name = ngo_name,
                )

    # ── Reminder config management ────────────────────

    def get_reminder_configs(self):
        from notification.models import ReminderConfig
        return ReminderConfig.objects.all()

    def save_reminder_config(self, interval_days, is_active=True):
        from notification.models import ReminderConfig
        config, created = ReminderConfig.objects.get_or_create(
            interval_days=interval_days,
            defaults={"is_active": is_active},
        )
        if not created:
            config.is_active = is_active
            config.save()
        return config

    def delete_reminder_config(self, config_id):
        from notification.models import ReminderConfig
        deleted, _ = ReminderConfig.objects.filter(pk=config_id).delete()
        return deleted > 0

    def toggle_reminder_config(self, config_id):
        from notification.models import ReminderConfig
        config = ReminderConfig.objects.filter(pk=config_id).first()
        if config:
            config.is_active = not config.is_active
            config.save()
        return config

    # ── Broadcast history ─────────────────────────────

    def get_broadcast_history(self):
        from notification.models import Broadcast
        return Broadcast.objects.annotate(
            sent_count   = Count('logs', filter=Q(logs__is_success=True)),
            failed_count = Count('logs', filter=Q(logs__is_success=False)),
        ).order_by('-sent_at')

    # ── Log queries ───────────────────────────────────

    def get_logs(self, filter_type=None):
        from notification.models import NotificationLog
        qs = NotificationLog.objects.select_related('broadcast')
        if filter_type:
            qs = qs.filter(notification_type=filter_type)
        return qs

    def get_stats(self):
        from notification.models import NotificationLog
        last_7_days = timezone.now() - timedelta(days=7)
        return NotificationLog.objects.aggregate(
            total_sent  = Count('id', filter=Q(is_success=True)),
            recent_sent = Count('id', filter=Q(is_success=True, sent_at__gte=last_7_days)),
            failed      = Count('id', filter=Q(is_success=False)),
        )

    # ── Recipient resolution ──────────────────────────
    # calls user-service API to get all employee emails

    def get_recipient_emails(self, target, ngo_ids=None):
        try:
            if target == "all":
                response = requests.get(
                    f"{settings.USER_SERVICE_URL}/api/v1/users/employees/",
                )
                return response.json().get('emails', [])

            if target == "activity" and ngo_ids:
                response = requests.get(
                    f"{settings.REGISTRATION_SERVICE_URL}/api/v1/registrations/emails/",
                    params={'ngo_ids': ngo_ids},
                )
                return response.json().get('emails', [])
        except Exception as e:
            logger.error(f"Failed to fetch recipient emails: {e}")

        return []

    def get_active_ngos(self):
        # calls ngo-service API
        try:
            response = requests.get(
                f"{settings.NGO_SERVICE_URL}/api/v1/activities/",
            )
            return response.json().get('results', [])
        except Exception as e:
            logger.error(f"Failed to fetch NGOs: {e}")
            return []