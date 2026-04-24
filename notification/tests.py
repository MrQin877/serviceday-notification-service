"""
Tests for Notification Service (Topic 13)
=========================================
13.1  Unit Testing  — functions, serializers, service methods
13.2  API Testing   — endpoint behaviour (status codes, payloads)
13.3  Integration   — API + database together

Run with:
    python manage.py test notification.tests
"""

from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from notification.models import Broadcast, NotificationLog, ReminderConfig
from notification.serializers import (
    BroadcastSerializer,
    NotificationLogSerializer,
    ReminderConfigSerializer,
)
from notification.services.notification_service import NotificationService


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_admin_user():
    """Return a dict that satisfies IsAdminUser.has_permission."""
    return {'username': 'admin', 'groups': ['Administrator']}


def authed_client():
    """APIClient whose request.user is set to an admin dict."""
    client = APIClient()
    # Force authentication by monkey-patching via force_authenticate
    # (our IsAdminUser reads request.user as a dict, not a Django User)
    client.force_authenticate(user=make_admin_user())
    return client


# ─────────────────────────────────────────────────────────────────────────────
# 13.1  UNIT TESTS
# ─────────────────────────────────────────────────────────────────────────────

class ReminderConfigSerializerUnitTest(TestCase):
    """Unit tests for ReminderConfigSerializer validation logic."""

    def test_valid_interval_days_passes(self):
        data = {'interval_days': 7, 'is_active': True}
        s = ReminderConfigSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)

    def test_interval_days_zero_fails(self):
        data = {'interval_days': 0, 'is_active': True}
        s = ReminderConfigSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn('interval_days', s.errors)

    def test_interval_days_negative_fails(self):
        data = {'interval_days': -3, 'is_active': True}
        s = ReminderConfigSerializer(data=data)
        self.assertFalse(s.is_valid())

    def test_interval_days_over_365_fails(self):
        data = {'interval_days': 400, 'is_active': True}
        s = ReminderConfigSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn('interval_days', s.errors)

    def test_interval_days_exactly_365_passes(self):
        data = {'interval_days': 365, 'is_active': True}
        s = ReminderConfigSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)


class BroadcastSerializerUnitTest(TestCase):
    """Unit tests for BroadcastSerializer validation logic."""

    def test_valid_broadcast_passes(self):
        data = {'subject': 'Hello', 'body': 'World', 'target': 'all'}
        s = BroadcastSerializer(data=data)
        self.assertTrue(s.is_valid(), s.errors)

    def test_blank_subject_fails(self):
        data = {'subject': '   ', 'body': 'Body text', 'target': 'all'}
        s = BroadcastSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn('subject', s.errors)

    def test_blank_body_fails(self):
        data = {'subject': 'Subject', 'body': '', 'target': 'all'}
        s = BroadcastSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn('body', s.errors)

    def test_invalid_target_fails(self):
        data = {'subject': 'Sub', 'body': 'Body', 'target': 'unknown'}
        s = BroadcastSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn('target', s.errors)


class NotificationServiceUnitTest(TestCase):
    """Unit tests for NotificationService helper methods."""

    def setUp(self):
        self.service = NotificationService()

    # ── _send_email stores a NotificationLog ─────────────────────────────────

    @patch('notification.services.notification_service.send_mail')
    @patch('notification.services.notification_service.track_notification')
    def test_send_email_creates_log_on_success(self, mock_track, mock_mail):
        mock_mail.return_value = 1
        result = self.service._send_email(
            recipient_email='user@test.com',
            recipient_name='Test User',
            subject='Test Subject',
            body='Test body',
            notif_type='verification',
        )
        self.assertTrue(result)
        log = NotificationLog.objects.get(recipient_email='user@test.com')
        self.assertTrue(log.is_success)
        self.assertEqual(log.notification_type, 'verification')

    @patch('notification.services.notification_service.send_mail', side_effect=Exception('SMTP error'))
    @patch('notification.services.notification_service.track_notification')
    def test_send_email_creates_log_on_failure(self, mock_track, mock_mail):
        result = self.service._send_email(
            recipient_email='fail@test.com',
            recipient_name='Fail User',
            subject='Subject',
            body='Body',
            notif_type='confirmation',
        )
        self.assertFalse(result)
        log = NotificationLog.objects.get(recipient_email='fail@test.com')
        self.assertFalse(log.is_success)
        self.assertIn('SMTP error', log.fail_reason)

    # ── save_reminder_config get_or_create logic ──────────────────────────────

    def test_save_reminder_config_creates_new(self):
        config = self.service.save_reminder_config(interval_days=5)
        self.assertEqual(config.interval_days, 5)
        self.assertTrue(config.is_active)

    def test_save_reminder_config_updates_existing(self):
        ReminderConfig.objects.create(interval_days=5, is_active=True)
        config = self.service.save_reminder_config(interval_days=5, is_active=False)
        self.assertFalse(config.is_active)

    # ── toggle_reminder_config flips is_active ────────────────────────────────

    def test_toggle_reminder_config(self):
        config = ReminderConfig.objects.create(interval_days=3, is_active=True)
        updated = self.service.toggle_reminder_config(config.pk)
        self.assertFalse(updated.is_active)
        # toggle again → back to True
        updated2 = self.service.toggle_reminder_config(config.pk)
        self.assertTrue(updated2.is_active)

    # ── delete_reminder_config ────────────────────────────────────────────────

    def test_delete_reminder_config_returns_true(self):
        config = ReminderConfig.objects.create(interval_days=10, is_active=True)
        result = self.service.delete_reminder_config(config.pk)
        self.assertTrue(result)
        self.assertFalse(ReminderConfig.objects.filter(pk=10).exists())

    def test_delete_nonexistent_config_returns_false(self):
        result = self.service.delete_reminder_config(9999)
        self.assertFalse(result)

    # ── get_stats aggregation ─────────────────────────────────────────────────

    def test_get_stats_counts_correctly(self):
        NotificationLog.objects.create(
            recipient_email='a@test.com', recipient_name='A',
            notification_type='verification', subject='S', body='B',
            is_success=True,
        )
        NotificationLog.objects.create(
            recipient_email='b@test.com', recipient_name='B',
            notification_type='confirmation', subject='S', body='B',
            is_success=False,
        )
        stats = self.service.get_stats()
        self.assertEqual(stats['total_sent'], 1)
        self.assertEqual(stats['failed'], 1)

    # ── send_verification_email missing fields ────────────────────────────────

    @patch('notification.services.notification_service.send_mail')
    @patch('notification.services.notification_service.track_notification')
    def test_send_verification_email_uses_correct_type(self, mock_track, mock_mail):
        mock_mail.return_value = 1
        self.service.send_verification_email(
            'verify@test.com', 'Ali', 'http://verify.url'
        )
        log = NotificationLog.objects.get(recipient_email='verify@test.com')
        self.assertEqual(log.notification_type, 'verification')
        self.assertIn('Verify', log.subject)

    # ── send_reset_password_email ─────────────────────────────────────────────

    @patch('notification.services.notification_service.send_mail')
    @patch('notification.services.notification_service.track_notification')
    def test_send_reset_password_email_uses_correct_type(self, mock_track, mock_mail):
        mock_mail.return_value = 1
        self.service.send_reset_password_email(
            'reset@test.com', 'Siti', 'http://reset.url'
        )
        log = NotificationLog.objects.get(recipient_email='reset@test.com')
        self.assertEqual(log.notification_type, 'reset_password')


# ─────────────────────────────────────────────────────────────────────────────
# 13.2  API TESTS
# ─────────────────────────────────────────────────────────────────────────────

class ReminderConfigAPITest(TestCase):
    """
    API tests for:
        GET/POST  /api/v1/notifications/reminders/
        GET/PATCH/DELETE /api/v1/notifications/reminders/<pk>/
    """

    def setUp(self):
        self.client = authed_client()
        self.list_url   = reverse('api-reminders-list')
        self.config     = ReminderConfig.objects.create(interval_days=7, is_active=True)
        self.detail_url = reverse('api-reminders-detail', kwargs={'pk': self.config.pk})

    # ── GET list ──────────────────────────────────────────────────────────────

    def test_get_reminders_returns_200(self):
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_get_reminders_returns_list(self):
        resp = self.client.get(self.list_url)
        self.assertIsInstance(resp.data, list)
        self.assertEqual(len(resp.data), 1)

    # ── POST create ───────────────────────────────────────────────────────────

    def test_post_reminder_creates_config(self):
        resp = self.client.post(self.list_url, {'interval_days': 3, 'is_active': True})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(ReminderConfig.objects.filter(interval_days=3).exists())

    def test_post_reminder_invalid_interval_returns_400(self):
        resp = self.client.post(self.list_url, {'interval_days': 0})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_reminder_interval_over_365_returns_400(self):
        resp = self.client.post(self.list_url, {'interval_days': 999})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ── GET detail ────────────────────────────────────────────────────────────

    def test_get_reminder_detail_returns_200(self):
        resp = self.client.get(self.detail_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['interval_days'], 7)

    def test_get_nonexistent_reminder_returns_404(self):
        resp = self.client.get(reverse('api-reminders-detail', kwargs={'pk': 9999}))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ── PATCH update ─────────────────────────────────────────────────────────

    def test_patch_reminder_updates_is_active(self):
        resp = self.client.patch(self.detail_url, {'is_active': False})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data['is_active'])

    # ── DELETE ────────────────────────────────────────────────────────────────

    def test_delete_reminder_returns_204(self):
        resp = self.client.delete(self.detail_url)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ReminderConfig.objects.filter(pk=self.config.pk).exists())


class BroadcastAPITest(TestCase):
    """
    API tests for:
        GET/POST /api/v1/notifications/broadcasts/
        GET      /api/v1/notifications/broadcasts/<id>/progress/
    """

    def setUp(self):
        self.client   = authed_client()
        self.list_url = reverse('api-broadcasts-list')

    # The task is imported INSIDE the view function body, so patch it at its
    # real location in the tasks module, not on notification.views.
    @patch('notification.views.send_broadcast_task.delay')
    def test_post_broadcast_queues_task(self, mock_delay):
        resp = self.client.post(self.list_url, {
            'subject': 'Test Subject',
            'body': 'Test body text',
            'target': 'all',
        })

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        mock_delay.assert_called_once()

    @patch('notification.tasks.send_broadcast_task')
    def test_post_broadcast_blank_subject_returns_400(self, mock_task):
        resp = self.client.post(self.list_url, {
            'subject': '   ',
            'body':    'Body',
            'target':  'all',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('notification.tasks.send_broadcast_task')
    def test_post_broadcast_blank_body_returns_400(self, mock_task):
        resp = self.client.post(self.list_url, {
            'subject': 'Subject',
            'body':    '',
            'target':  'all',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_broadcasts_returns_200(self):
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_broadcast_progress_returns_correct_counts(self):
        broadcast = Broadcast.objects.create(
            subject='Sub', body='Body', target='all', sent_by='admin', recipients=2
        )
        NotificationLog.objects.create(
            recipient_email='a@test.com', recipient_name='A',
            notification_type='broadcast', subject='Sub', body='Body',
            is_success=True, broadcast=broadcast,
        )
        NotificationLog.objects.create(
            recipient_email='b@test.com', recipient_name='B',
            notification_type='broadcast', subject='Sub', body='Body',
            is_success=False, broadcast=broadcast,
        )
        url  = reverse('api-broadcast-progress', kwargs={'broadcast_id': broadcast.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['sent'],   1)
        self.assertEqual(resp.data['failed'], 1)
        self.assertEqual(resp.data['total'],  2)

    def test_broadcast_progress_nonexistent_returns_404(self):
        url  = reverse('api-broadcast-progress', kwargs={'broadcast_id': 9999})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class NotificationLogsAPITest(TestCase):
    """API tests for GET /api/v1/notifications/logs/"""

    def setUp(self):
        self.client = authed_client()
        self.url    = reverse('api-notif-logs')
        for i in range(3):
            NotificationLog.objects.create(
                recipient_email=f'user{i}@test.com',
                recipient_name=f'User {i}',
                notification_type='verification',
                subject='Sub', body='Body',
                is_success=True,
            )
        NotificationLog.objects.create(
            recipient_email='r@test.com', recipient_name='R',
            notification_type='reminder', subject='Sub', body='Body',
            is_success=True,
        )

    def test_logs_returns_200(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_logs_returns_paginated_structure(self):
        resp = self.client.get(self.url)
        self.assertIn('results', resp.data)
        self.assertIn('count',   resp.data)

    def test_logs_filter_by_notification_type(self):
        resp = self.client.get(self.url, {'notification_type': 'reminder'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for item in resp.data['results']:
            self.assertEqual(item['notification_type'], 'reminder')

    def test_logs_filter_returns_only_matching_type(self):
        resp = self.client.get(self.url, {'notification_type': 'verification'})
        self.assertEqual(resp.data['count'], 3)


class SendVerificationEmailAPITest(TestCase):
    """API tests for POST /api/v1/notifications/send-verification/"""

    def setUp(self):
        self.client = APIClient()   # no auth needed (AllowAny)
        self.url    = reverse('api-send-verification')

    @patch('notification.views.NotificationService')
    def test_valid_payload_returns_200(self, MockService):
        MockService.return_value.send_verification_email.return_value = True
        resp = self.client.post(self.url, {
            'email':            'ali@test.com',
            'name':             'Ali',
            'verification_url': 'http://verify/abc123/',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('message', resp.data)

    @patch('notification.views.NotificationService')
    def test_missing_email_returns_400(self, MockService):
        resp = self.client.post(self.url, {
            'name':             'Ali',
            'verification_url': 'http://verify/abc123/',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('notification.views.NotificationService')
    def test_missing_verification_url_returns_400(self, MockService):
        resp = self.client.post(self.url, {
            'email': 'ali@test.com',
            'name':  'Ali',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('notification.views.NotificationService')
    def test_service_failure_returns_500(self, MockService):
        MockService.return_value.send_verification_email.return_value = False
        resp = self.client.post(self.url, {
            'email':            'ali@test.com',
            'name':             'Ali',
            'verification_url': 'http://verify/abc123/',
        })
        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class SendResetPasswordAPITest(TestCase):
    """API tests for POST /api/v1/notifications/send-reset-password/"""

    def setUp(self):
        self.client = APIClient()
        self.url    = reverse('api-send-reset-password')

    @patch('notification.views.NotificationService')
    def test_valid_payload_returns_200(self, MockService):
        MockService.return_value.send_reset_password_email.return_value = True
        resp = self.client.post(self.url, {
            'email':     'siti@test.com',
            'name':      'Siti',
            'reset_url': 'http://reset/xyz456/',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @patch('notification.views.NotificationService')
    def test_missing_reset_url_returns_400(self, MockService):
        resp = self.client.post(self.url, {
            'email': 'siti@test.com',
            'name':  'Siti',
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class SendConfirmationEmailAPITest(TestCase):
    """API tests for POST /api/v1/notifications/confirmation/"""

    def setUp(self):
        self.client = APIClient()
        self.url    = reverse('api-send-confirmation')

    @patch('notification.views.NotificationService')
    def test_valid_payload_returns_200(self, MockService):
        MockService.return_value.send_confirmation_email.return_value = True
        resp = self.client.post(self.url, {
            'employee_id':     1,
            'ngo_id':          2,
            'registration_id': 3,
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @patch('notification.views.NotificationService')
    def test_missing_fields_returns_400(self, MockService):
        resp = self.client.post(self.url, {'employee_id': 1})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class SendCancellationEmailAPITest(TestCase):
    """API tests for POST /api/v1/notifications/cancellation/"""

    def setUp(self):
        self.client = APIClient()
        self.url    = reverse('api-send-cancellation')

    @patch('notification.views.NotificationService')
    def test_valid_payload_returns_200(self, MockService):
        MockService.return_value.send_cancellation_email.return_value = True
        resp = self.client.post(self.url, {'employee_id': 1, 'ngo_id': 2})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @patch('notification.views.NotificationService')
    def test_missing_ngo_id_returns_400(self, MockService):
        resp = self.client.post(self.url, {'employee_id': 1})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class SendSwitchEmailAPITest(TestCase):
    """API tests for POST /api/v1/notifications/switch/"""

    def setUp(self):
        self.client = APIClient()
        self.url    = reverse('api-send-switch')

    @patch('notification.views.NotificationService')
    def test_valid_payload_returns_200(self, MockService):
        MockService.return_value.send_switch_email.return_value = True
        resp = self.client.post(self.url, {
            'employee_id': 1,
            'old_ngo_id':  2,
            'new_ngo_id':  3,
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @patch('notification.views.NotificationService')
    def test_missing_new_ngo_id_returns_400(self, MockService):
        resp = self.client.post(self.url, {
            'employee_id': 1,
            'old_ngo_id':  2,
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class TriggerRemindersAPITest(TestCase):
    """API test for POST /api/v1/notifications/trigger-reminders/"""

    def setUp(self):
        self.client = authed_client()
        self.url    = reverse('api-trigger-reminders')

    @patch('notification.views.send_reminder_emails_task')
    def test_trigger_reminders_returns_202(self, mock_task):
        mock_task.delay = MagicMock()
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        mock_task.delay.assert_called_once()

    def test_trigger_reminders_unauthenticated_returns_403(self):
        resp = APIClient().post(self.url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ─────────────────────────────────────────────────────────────────────────────
# 13.3  INTEGRATION TESTS  (API → Database)
# ─────────────────────────────────────────────────────────────────────────────

class ReminderConfigIntegrationTest(TestCase):
    """
    Integration: POST creates a ReminderConfig row in the DB.
    PATCH persists the change. DELETE removes it.
    """

    def setUp(self):
        self.client   = authed_client()
        self.list_url = reverse('api-reminders-list')

    def test_create_reminder_persists_to_db(self):
        self.client.post(self.list_url, {'interval_days': 14, 'is_active': True})
        self.assertTrue(ReminderConfig.objects.filter(interval_days=14).exists())
        config = ReminderConfig.objects.get(interval_days=14)
        self.assertTrue(config.is_active)

    def test_patch_reminder_persists_to_db(self):
        config = ReminderConfig.objects.create(interval_days=5, is_active=True)
        url    = reverse('api-reminders-detail', kwargs={'pk': config.pk})
        self.client.patch(url, {'is_active': False})
        config.refresh_from_db()
        self.assertFalse(config.is_active)

    def test_delete_reminder_removes_from_db(self):
        config = ReminderConfig.objects.create(interval_days=5, is_active=True)
        url    = reverse('api-reminders-detail', kwargs={'pk': config.pk})
        self.client.delete(url)
        self.assertFalse(ReminderConfig.objects.filter(pk=config.pk).exists())


class BroadcastIntegrationTest(TestCase):
    """
    Integration: POST to broadcasts/ → Broadcast row created in DB
                 NotificationLogs written → progress endpoint reflects them.
    """

    def setUp(self):
        self.client   = authed_client()
        self.list_url = reverse('api-broadcasts-list')

    @patch('notification.views.send_broadcast_task')
    def test_post_broadcast_creates_db_row(self, mock_task):
        mock_task.delay = MagicMock()
        self.client.post(self.list_url, {
            'subject': 'Integration Test',
            'body':    'Integration body',
            'target':  'all',
        })
        self.assertTrue(Broadcast.objects.filter(subject='Integration Test').exists())

    @patch('notification.views.send_broadcast_task')
    def test_broadcast_progress_reflects_db_logs(self, mock_task):
        mock_task.delay = MagicMock()
        # Create broadcast via API
        self.client.post(self.list_url, {
            'subject': 'Prog Test',
            'body':    'Body',
            'target':  'all',
        })
        broadcast = Broadcast.objects.get(subject='Prog Test')

        # Simulate task writing logs directly to DB
        NotificationLog.objects.create(
            recipient_email='x@test.com', recipient_name='X',
            notification_type='broadcast', subject='Prog Test', body='Body',
            is_success=True, broadcast=broadcast,
        )

        url  = reverse('api-broadcast-progress', kwargs={'broadcast_id': broadcast.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['sent'], 1)
        self.assertEqual(resp.data['failed'], 0)


class NotificationLogIntegrationTest(TestCase):
    """
    Integration: _send_email() writes a NotificationLog to the DB;
    the /logs/ endpoint returns it with the correct type and filter.
    """

    def setUp(self):
        self.client  = authed_client()
        self.log_url = reverse('api-notif-logs')
        self.service = NotificationService()

    @patch('notification.services.notification_service.send_mail')
    @patch('notification.services.notification_service.track_notification')
    def test_send_email_log_appears_in_api(self, mock_track, mock_mail):
        mock_mail.return_value = 1
        self.service._send_email(
            recipient_email='integration@test.com',
            recipient_name='Int User',
            subject='Integration Subject',
            body='Integration Body',
            notif_type='confirmation',
        )
        resp = self.client.get(self.log_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        emails = [r['recipient_email'] for r in resp.data['results']]
        self.assertIn('integration@test.com', emails)

    @patch('notification.services.notification_service.send_mail')
    @patch('notification.services.notification_service.track_notification')
    def test_log_filter_isolates_type_in_db(self, mock_track, mock_mail):
        mock_mail.return_value = 1
        # Write two different types
        self.service._send_email('a@t.com', 'A', 'Sub', 'Body', 'confirmation')
        self.service._send_email('b@t.com', 'B', 'Sub', 'Body', 'reminder')

        resp = self.client.get(self.log_url, {'notification_type': 'confirmation'})
        types = [r['notification_type'] for r in resp.data['results']]
        self.assertTrue(all(t == 'confirmation' for t in types))
        self.assertNotIn('reminder', types)

    @patch('notification.services.notification_service.send_mail')
    @patch('notification.services.notification_service.track_notification')
    def test_failed_email_log_stored_with_fail_reason(self, mock_track, mock_mail):
        mock_mail.side_effect = Exception('Connection refused')
        self.service._send_email('fail@t.com', 'F', 'Sub', 'Body', 'verification')

        log = NotificationLog.objects.get(recipient_email='fail@t.com')
        self.assertFalse(log.is_success)
        self.assertIn('Connection refused', log.fail_reason)

        resp = self.client.get(self.log_url)
        emails = [r['recipient_email'] for r in resp.data['results']]
        self.assertIn('fail@t.com', emails)


class VerificationEmailIntegrationTest(TestCase):
    """
    Integration: POST /send-verification/ → NotificationLog written to DB.
    """

    def setUp(self):
        self.client = APIClient()
        self.url    = reverse('api-send-verification')

    @patch('notification.services.notification_service.send_mail')
    @patch('notification.services.notification_service.track_notification')
    def test_verification_endpoint_writes_log_to_db(self, mock_track, mock_mail):
        mock_mail.return_value = 1
        resp = self.client.post(self.url, {
            'email':            'newuser@test.com',
            'name':             'New User',
            'verification_url': 'http://verify/token123/',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            NotificationLog.objects.filter(
                recipient_email='newuser@test.com',
                notification_type='verification',
                is_success=True,
            ).exists()
        )