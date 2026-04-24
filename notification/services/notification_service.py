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

    # ── Internal service-to-service auth header ───────

    def _internal_headers(self):

        token = getattr(settings, 'INTERNAL_SERVICE_TOKEN', '')
        return {'Authorization': f'Bearer {token}'} if token else {}

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
                from_email = settings.EMAIL_HOST_USER,
                recipient_list = [recipient_email],
                fail_silently  = False,
            )
        except Exception as e:
            success     = False
            fail_reason = str(e)
            logger.warning(f"[Email] Failed to send to {recipient_email}: {e}")

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

    # ── Verification Email ────────────────────────────

    def send_verification_email(self, recipient_email, recipient_name, verification_url):
        """
        Called by user-service after registration.
        POST /api/v1/notifications/send-verification/
        """
        subject = "Verify your ServiceDay account"
        body    = f"""Hi {recipient_name},

        Welcome to ServiceDay! Please verify your email address to activate your account.

        Click the link below to verify:
        {verification_url}

        This link expires in 1 hour.

        If you did not register, please ignore this email.

        — ServiceDay Team
        """
        return self._send_email(
            recipient_email = recipient_email,
            recipient_name  = recipient_name,
            subject         = subject,
            body            = body,
            notif_type      = 'verification',
        )

    # ── Reset Password Email ──────────────────────────

    def send_reset_password_email(self, recipient_email, recipient_name, reset_url):
        """
        Called by user-service after forgot-password is triggered.
        POST /api/v1/notifications/send-reset-password/
        """
        subject = "Reset your ServiceDay password"
        body    = f"""Hi {recipient_name},

We received a request to reset your ServiceDay account password.

Click the link below to set a new password:
{reset_url}

This link expires in 1 hour.

If you did not request a password reset, please ignore this email.
Your password will remain unchanged.

— ServiceDay Team
"""
        return self._send_email(
            recipient_email = recipient_email,
            recipient_name  = recipient_name,
            subject         = subject,
            body            = body,
            notif_type      = 'reset_password',
        )

    # ── Registration Confirmation Email ───────────────

    def send_confirmation_email(self, employee_id, ngo_id, registration_id):
        """
        Called by registration-service after successful registration.
        POST /api/v1/notifications/send-confirmation/
        Fetches employee and NGO details from respective services.
        """
        headers = self._internal_headers()

        # fetch employee details from user-service
        try:
            user_resp = requests.get(
                f"{settings.USER_SERVICE_URL}/api/v1/users/{employee_id}/",
                headers = headers,
                timeout = 10,
            )
            user_resp.raise_for_status()
            user = user_resp.json()
        except Exception as e:
            logger.error(f"[Confirmation] Failed to fetch user {employee_id}: {e}")
            return False

        # fetch NGO details from ngo-service
        try:
            ngo_resp = requests.get(
                f"{settings.NGO_SERVICE_URL}/api/v1/activities/{ngo_id}/",
                headers = headers,
                timeout = 10,
            )
            ngo_resp.raise_for_status()
            ngo = ngo_resp.json()
        except Exception as e:
            logger.error(f"[Confirmation] Failed to fetch NGO {ngo_id}: {e}")
            return False

        recipient_email = user.get('email', '')
        recipient_name  = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        ngo_name        = ngo.get('name', '')
        service_date    = ngo.get('service_date', '')
        start_time      = ngo.get('start_time', '')
        end_time        = ngo.get('end_time', '')
        location        = ngo.get('location', '')

        subject = f"Registration Confirmed — {ngo_name}"
        body    = f"""Hi {recipient_name},

Your registration has been confirmed!

Activity    : {ngo_name}
Date        : {service_date}
Time        : {start_time} – {end_time}
Location    : {location}
Reference   : #{registration_id}

See you there!

— ServiceDay Team
"""
        return self._send_email(
            recipient_email = recipient_email,
            recipient_name  = recipient_name,
            subject         = subject,
            body            = body,
            notif_type      = 'confirmation',
            ngo_id          = ngo_id,
            ngo_name        = ngo_name,
        )

    # ── Registration Cancellation Email ───────────────

    def send_cancellation_email(self, employee_id, ngo_id):
        """
        Called by registration-service after cancellation.
        POST /api/v1/notifications/send-cancellation/
        """
        headers = self._internal_headers()

        try:
            user_resp = requests.get(
                f"{settings.USER_SERVICE_URL}/api/v1/users/{employee_id}/",
                headers = headers,
                timeout = 10,
            )
            user_resp.raise_for_status()
            user = user_resp.json()
        except Exception as e:
            logger.error(f"[Cancellation] Failed to fetch user {employee_id}: {e}")
            return False

        try:
            ngo_resp = requests.get(
                f"{settings.NGO_SERVICE_URL}/api/v1/activities/{ngo_id}/",
                headers = headers,
                timeout = 10,
            )
            ngo_resp.raise_for_status()
            ngo = ngo_resp.json()
        except Exception as e:
            logger.error(f"[Cancellation] Failed to fetch NGO {ngo_id}: {e}")
            return False

        recipient_email = user.get('email', '')
        recipient_name  = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        ngo_name        = ngo.get('name', '')
        service_date    = ngo.get('service_date', '')

        subject = f"Registration Cancelled — {ngo_name}"
        body    = f"""Hi {recipient_name},

Your registration has been cancelled.

Activity : {ngo_name}
Date     : {service_date}

If this was a mistake, you may re-register while slots are still available.

— ServiceDay Team
"""
        return self._send_email(
            recipient_email = recipient_email,
            recipient_name  = recipient_name,
            subject         = subject,
            body            = body,
            notif_type      = 'cancellation',
            ngo_id          = ngo_id,
            ngo_name        = ngo_name,
        )

    # ── Registration Switch Email ─────────────────────

    def send_switch_email(self, employee_id, old_ngo_id, new_ngo_id):
        """
        Called by registration-service after activity switch.
        POST /api/v1/notifications/send-switch/
        """
        headers = self._internal_headers()

        try:
            user_resp = requests.get(
                f"{settings.USER_SERVICE_URL}/api/v1/users/{employee_id}/",
                headers = headers,
                timeout = 10,
            )
            user_resp.raise_for_status()
            user = user_resp.json()
        except Exception as e:
            logger.error(f"[Switch] Failed to fetch user {employee_id}: {e}")
            return False

        try:
            old_ngo_resp = requests.get(
                f"{settings.NGO_SERVICE_URL}/api/v1/activities/{old_ngo_id}/",
                headers = headers,
                timeout = 10,
            )
            old_ngo_resp.raise_for_status()
            old_ngo = old_ngo_resp.json()

            new_ngo_resp = requests.get(
                f"{settings.NGO_SERVICE_URL}/api/v1/activities/{new_ngo_id}/",
                headers = headers,
                timeout = 10,
            )
            new_ngo_resp.raise_for_status()
            new_ngo = new_ngo_resp.json()
        except Exception as e:
            logger.error(f"[Switch] Failed to fetch NGO details: {e}")
            return False

        recipient_email = user.get('email', '')
        recipient_name  = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        old_ngo_name    = old_ngo.get('name', '')
        new_ngo_name    = new_ngo.get('name', '')
        new_date        = new_ngo.get('service_date', '')
        new_start       = new_ngo.get('start_time', '')
        new_end         = new_ngo.get('end_time', '')
        new_location    = new_ngo.get('location', '')

        subject = f"Activity Switched — {new_ngo_name}"
        body    = f"""Hi {recipient_name},

Your activity registration has been switched successfully.

From : {old_ngo_name}
To   : {new_ngo_name}

New activity details:
Date     : {new_date}
Time     : {new_start} – {new_end}
Location : {new_location}

— ServiceDay Team
"""
        return self._send_email(
            recipient_email = recipient_email,
            recipient_name  = recipient_name,
            subject         = subject,
            body            = body,
            notif_type      = 'switch',
            ngo_id          = new_ngo_id,
            ngo_name        = new_ngo_name,
        )

    # ── Reminder Engine ───────────────────────────────
    # Topic 10.2 — called by Celery Beat every day at 08:00
    # calls registration-service API to get registrations
    # calls ngo-service API to get NGO details

    def send_activity_reminders(self):
        from notification.models import ReminderConfig

        today   = timezone.now().date()
        headers = self._internal_headers()

        for config in ReminderConfig.objects.filter(is_active=True):
            target_date = today + timedelta(days=config.interval_days)

            logger.info(f"[Reminders] Fetching registrations for {target_date} ({config.interval_days}-day reminder).")

            # call registration-service to get registrations for target date
            try:
                response = requests.get(
                    f"{settings.REGISTRATION_SERVICE_URL}/api/v1/registrations/",
                    params  = {'service_date': target_date.isoformat()},
                    headers = headers,   # ← authenticated with internal token
                    timeout = 10,
                )
                response.raise_for_status()
                registrations = response.json().get('results', [])
            except Exception as e:
                logger.error(f"[Reminders] Failed to fetch registrations for {target_date}: {e}")
                continue

            if not registrations:
                logger.info(f"[Reminders] No registrations found for {target_date}.")
                continue

            logger.info(f"[Reminders] Sending {len(registrations)} reminder(s) for {target_date}.")

            for reg in registrations:
                employee_email = reg.get('employee_email', '')
                employee_name  = reg.get('employee_name', '')
                ngo_name       = reg.get('ngo_name', '')
                ngo_id         = reg.get('ngo_id')
                service_date   = reg.get('service_date', '')
                start_time     = reg.get('start_time', '')
                end_time       = reg.get('end_time', '')
                location       = reg.get('location', '')

                if not employee_email:
                    logger.warning(f"[Reminders] Skipping registration with no email: {reg}")
                    continue

                subject = f"Reminder: {ngo_name} in {config.interval_days} day(s)"
                body    = f"""Hi {employee_name},

This is a reminder for your upcoming ServiceDay activity.

Activity : {ngo_name}
Date     : {service_date}
Time     : {start_time} – {end_time}
Location : {location}

We look forward to seeing you there!

— ServiceDay Team
"""
                self._send_email(
                    recipient_email = employee_email,
                    recipient_name  = employee_name,
                    subject         = subject,
                    body            = body,
                    notif_type      = 'reminder',
                    ngo_id          = ngo_id,
                    ngo_name        = ngo_name,
                )

    # ── Reminder Config Management ────────────────────

    def get_reminder_configs(self):
        from notification.models import ReminderConfig
        return ReminderConfig.objects.all()

    def save_reminder_config(self, interval_days, is_active=True):
        from notification.models import ReminderConfig
        config, created = ReminderConfig.objects.get_or_create(
            interval_days = interval_days,
            defaults      = {"is_active": is_active},
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

    # ── Broadcast History ─────────────────────────────

    def get_broadcast_history(self):
        from notification.models import Broadcast
        return Broadcast.objects.annotate(
            sent_count   = Count('logs', filter=Q(logs__is_success=True)),
            failed_count = Count('logs', filter=Q(logs__is_success=False)),
        ).order_by('-sent_at')

    # ── Log Queries ───────────────────────────────────

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

    # ── Recipient Resolution ──────────────────────────
    # calls user-service API to get all employee emails

    def get_recipient_emails(self, target, ngo_ids=None):
        headers = self._internal_headers()
        try:
            if target == "all":
                response = requests.get(
                    f"{settings.USER_SERVICE_URL}/api/v1/users/employees/emails/",
                    headers=headers,
                    timeout=10,
                )
                response.raise_for_status()
                data     = response.json()
                emails   = data.get('emails', [])
                user_map = data.get('user_map', {})  # ← get user map
                return emails, user_map               # ← return both

            if target == "activity" and ngo_ids:
                response = requests.get(
                    f"{settings.REGISTRATION_SERVICE_URL}/api/v1/registrations/emails/",
                    params={'ngo_ids': ngo_ids},
                    headers=headers,
                    timeout=10,
                )
                response.raise_for_status()
                data     = response.json()
                emails   = data.get('emails', [])
                user_map = data.get('user_map', {})
                return emails, user_map

        except Exception as e:
            logger.error(f"[Recipients] Failed: {e}")
        return [], {}

    # ── Active NGOs ───────────────────────────────────

    def get_active_ngos(self):
        """Calls ngo-service API to get active NGO list."""
        try:
            response = requests.get(
                f"{settings.NGO_SERVICE_URL}/api/v1/activities/",
                headers = self._internal_headers(),
                timeout = 10,
            )
            response.raise_for_status()
            return response.json().get('results', [])
        except Exception as e:
            logger.error(f"[NGOs] Failed to fetch active NGOs: {e}")
            return []
        
        