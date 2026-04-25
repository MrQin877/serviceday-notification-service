import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'notification_service.settings')

app = Celery('notification_service')
app.config_from_object('django.conf:settings', namespace='CELERY')

# explicitly tell Celery where to find tasks
app.autodiscover_tasks(['notification'])

app.conf.beat_schedule = {
    'daily-reminders': {
        'task':     'notification.tasks.send_reminder_emails_task',
        'schedule': crontab(hour=1, minute=0),
    },
}