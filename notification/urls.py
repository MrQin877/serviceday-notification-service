from django.urls import path
from . import views

urlpatterns = [
    path('notifications/reminders/',                                views.reminder_list,                name='api-reminders-list'),
    path('notifications/reminders/<int:pk>/',                       views.reminder_detail,              name='api-reminders-detail'),
    path('notifications/broadcasts/',                               views.broadcast_list,               name='api-broadcasts-list'),
    path('notifications/broadcasts/<int:broadcast_id>/progress/',   views.broadcast_progress,           name='api-broadcast-progress'),
    path('notifications/logs/',                                     views.notification_logs,            name='api-notif-logs'),
    path('notifications/trigger-reminders/',                        views.trigger_reminders,            name='api-trigger-reminders'),
    path('notifications/send-verification/',                        views.send_verification_email,      name='api-send-verification'),
    path('notifications/send-reset-password/',                      views.send_reset_password_email,    name='api-send-reset-password'),
    path('notifications/confirmation/',                             views.send_confirmation_email,      name='api-send-confirmation'),
    path('notifications/cancellation/',                             views.send_cancellation_email,      name='api-send-cancellation'),
    path('notifications/switch/',                                   views.send_switch_email,            name='api-send-switch'),
]