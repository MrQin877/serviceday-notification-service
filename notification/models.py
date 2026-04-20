from django.db import models


class ReminderConfig(models.Model):
    interval_days = models.PositiveIntegerField(
        primary_key=True,
        help_text="Days before activity to send reminder (e.g. 7, 3, 1)"
    )
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering       = ['interval_days']
        verbose_name   = "Reminder Configuration"
        verbose_name_plural = "Reminder Configurations"

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.interval_days}-day reminder ({status})"


class Broadcast(models.Model):
    TARGET_CHOICES = [
        ('all',      'All Employees'),
        ('activity', 'Specific Activity'),
    ]
    subject    = models.CharField(max_length=200)
    body       = models.TextField()
    target     = models.CharField(max_length=20, choices=TARGET_CHOICES, default='all')
    sent_at    = models.DateTimeField(auto_now_add=True)
    sent_by    = models.CharField(max_length=100, default='Admin')
    recipients = models.PositiveIntegerField(default=0)

    class Meta:
        ordering       = ['-sent_at']
        verbose_name   = "Broadcast Message"
        verbose_name_plural = "Broadcast Messages"

    def __str__(self):
        return f"Broadcast: {self.subject} → {self.target} ({self.sent_at:%Y-%m-%d})"

    def delete_with_logs(self):
        self.logs.all().delete()
        self.delete()


class NotificationLog(models.Model):
    NOTIFICATION_TYPES = [
        ('confirmation', 'Registration Confirmation'),
        ('reminder',     'Activity Reminder'),
        ('update',       'Activity Update'),
        ('cancellation', 'Cancellation'),
        ('broadcast',    'Admin Broadcast'),
    ]
    recipient_email   = models.EmailField()
    recipient_name    = models.CharField(max_length=100, blank=True)
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    subject           = models.CharField(max_length=200)
    body              = models.TextField()
    sent_at           = models.DateTimeField(auto_now_add=True)
    is_success        = models.BooleanField(default=True)
    fail_reason       = models.TextField(blank=True, default='')

    # ── microservice change ───────────────────────────────────────────────────
    # In monolithic: ngo = ForeignKey('ngo.NGO') — can't do this in microservice
    # NGO lives in ngo-service, not here
    # Solution: store ngo_id as plain integer instead of FK
    ngo_id   = models.IntegerField(null=True, blank=True)   # just store the ID
    ngo_name = models.CharField(max_length=100, blank=True) # store name for display

    broadcast = models.ForeignKey(
        Broadcast,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='logs',
    )

    class Meta:
        ordering       = ['-sent_at']
        verbose_name   = "Notification Log"
        verbose_name_plural = "Notification Logs"

    def __str__(self):
        return f"[{self.notification_type}] → {self.recipient_email} at {self.sent_at:%Y-%m-%d %H:%M}"