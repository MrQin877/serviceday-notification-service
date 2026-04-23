from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch, MagicMock
from datetime import timedelta

from notification.models import NotificationLog, Broadcast, ReminderConfig
from notification.services.notification_service import NotificationService


FAKE_USER = {
    'email': 'john@example.com',
    'first_name': 'John',
    'last_name': 'Doe',
}

FAKE_NGO = {
    'name': 'Tree Planting',
    'service_date': '2026-06-01',
    'start_time': '09:00',
    'end_time': '17:00',
    'location': 'Kuala Lumpur',
}

FAKE_OLD_NGO = {
    'name': 'Old Activity',
    'service_date': '2026-05-01',
    'start_time': '08:00',
    'end_time': '12:00',
    'location': 'Penang',
}


def make_mock_response(json_data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    return mock


class NotificationUnitTest(TestCase):

    def setUp(self):
        self.service = NotificationService()

    # ── _send_email ─────────────────────
    @patch('notification.services.notification_service.send_mail')
    def test_send_email_success(self, mock_send_mail):
        mock_send_mail.return_value = 1

        result = self.service._send_email(
            'test@example.com', 'Test', 'Hello', 'Body', 'confirmation'
        )

        self.assertTrue(result)
        self.assertEqual(NotificationLog.objects.count(), 1)

    @patch('notification.services.notification_service.send_mail')
    def test_send_email_failure(self, mock_send_mail):
        mock_send_mail.side_effect = Exception('fail')

        result = self.service._send_email(
            'fail@test.com', 'Fail', 'Sub', 'Body', 'confirmation'
        )

        self.assertFalse(result)

    # ── Verification ─────────────────────
    @patch('notification.services.notification_service.send_mail')
    def test_verification_email(self, mock_send_mail):
        mock_send_mail.return_value = 1

        self.service.send_verification_email(
            'verify@test.com', 'User', 'http://link'
        )

        log = NotificationLog.objects.first()
        self.assertEqual(log.notification_type, 'verification')

    # ── Reset Password ───────────────────
    @patch('notification.services.notification_service.send_mail')
    def test_reset_email(self, mock_send_mail):
        mock_send_mail.return_value = 1

        self.service.send_reset_password_email(
            'reset@test.com', 'User', 'http://reset'
        )

        log = NotificationLog.objects.first()
        self.assertEqual(log.notification_type, 'reset_password')

    # ── Confirmation ─────────────────────
    @patch('notification.services.notification_service.send_mail')
    @patch('notification.services.notification_service.requests.get')
    def test_confirmation_success(self, mock_get, mock_send_mail):
        mock_send_mail.return_value = 1
        mock_get.side_effect = [
            make_mock_response(FAKE_USER),
            make_mock_response(FAKE_NGO),
        ]

        result = self.service.send_confirmation_email(1, 10, 99)
        self.assertTrue(result)

    # ── Cancellation ─────────────────────
    @patch('notification.services.notification_service.requests.get')
    def test_cancellation_fail(self, mock_get):
        mock_get.side_effect = Exception()

        result = self.service.send_cancellation_email(1, 10)
        self.assertFalse(result)

    # ── Switch ───────────────────────────
    @patch('notification.services.notification_service.requests.get')
    def test_switch_fail(self, mock_get):
        mock_get.side_effect = Exception()

        result = self.service.send_switch_email(1, 1, 2)
        self.assertFalse(result)

    # ── Broadcast ────────────────────────
    @patch('notification.services.notification_service.send_mail')
    def test_broadcast(self, mock_send_mail):
        mock_send_mail.return_value = 1

        count = self.service.send_broadcast(
            'Test', 'Body', ['a@test.com', 'b@test.com']
        )

        self.assertEqual(count, 2)

    # ── Reminder ─────────────────────────
    @patch('notification.services.notification_service.requests.get')
    def test_reminder_no_data(self, mock_get):
        mock_get.return_value = make_mock_response({'results': []})

        self.service.send_activity_reminders()
        self.assertEqual(NotificationLog.objects.count(), 0)

    # ── Reminder Config ──────────────────
    def test_save_config(self):
        config = self.service.save_reminder_config(3)
        self.assertEqual(config.interval_days, 3)

    # ── Logs & Stats ─────────────────────
    def test_get_stats(self):
        NotificationLog.objects.create(
            recipient_email='a@test.com',
            recipient_name='A',
            notification_type='test',
            subject='s',
            body='b',
            is_success=True
        )

        stats = self.service.get_stats()
        self.assertEqual(stats['total_sent'], 1)

    # ── Recipient Emails ─────────────────
    @patch('notification.services.notification_service.requests.get')
    def test_get_emails(self, mock_get):
        mock_get.return_value = make_mock_response({'emails': ['a@test.com']})

        emails = self.service.get_recipient_emails('all')
        self.assertEqual(emails, ['a@test.com'])

    # ── Active NGOs ──────────────────────
    @patch('notification.services.notification_service.requests.get')
    def test_get_ngos(self, mock_get):
        mock_get.return_value = make_mock_response({'results': [FAKE_NGO]})

        ngos = self.service.get_active_ngos()
        self.assertEqual(len(ngos), 1)