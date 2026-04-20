from django.urls import path
from . import views

urlpatterns = [
    path('notifications/reminders/',            views.reminder_list,     name='api-reminders-list'),
    path('notifications/reminders/<int:pk>/',   views.reminder_detail,   name='api-reminders-detail'),
    path('notifications/broadcasts/',           views.broadcast_list,    name='api-broadcasts-list'),
    path('notifications/logs/',                 views.notification_logs, name='api-notif-logs'),
    path('notifications/trigger-reminders/',    views.trigger_reminders, name='api-trigger-reminders'),
]