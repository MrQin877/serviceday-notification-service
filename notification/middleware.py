import threading
import logging

_notification_storage = threading.local()
logger = logging.getLogger(__name__)


class NotificationMonitorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _notification_storage.sent_notifications = []

        response = self.get_response(request)

        for notif in getattr(_notification_storage, "sent_notifications", []):
            if notif.is_success:
                logger.info(f"Notification sent successfully to {notif.recipient_email}")
            else:
                logger.warning(
                    f"Notification FAILED to {notif.recipient_email}: "
                    f"{getattr(notif, 'fail_reason', 'Unknown')}"
                )

        _notification_storage.sent_notifications = []
        return response


def track_notification(notification_log):
    if not hasattr(_notification_storage, "sent_notifications"):
        _notification_storage.sent_notifications = []

    _notification_storage.sent_notifications.append(notification_log)



