from rest_framework import serializers
from notification.models import Broadcast, NotificationLog, ReminderConfig


class ReminderConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ReminderConfig
        fields = ['interval_days', 'is_active', 'created_at']

    def validate_interval_days(self, value):
        if value < 1:
            raise serializers.ValidationError("interval_days must be 1 or more.")
        if value > 365:
            raise serializers.ValidationError("interval_days cannot exceed 365.")
        return value


class BroadcastSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Broadcast
        fields = ['id', 'subject', 'body', 'target', 'sent_by', 'sent_at', 'recipients']
        read_only_fields = ['sent_by', 'sent_at', 'recipients']

    def validate_subject(self, value):
        if not value.strip():
            raise serializers.ValidationError("Subject cannot be blank.")
        return value

    def validate_body(self, value):
        if not value.strip():
            raise serializers.ValidationError("Body cannot be blank.")
        return value


class NotificationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = NotificationLog
        fields = [
            'id', 'recipient_email', 'recipient_name',
            'notification_type', 'subject',
            'sent_at', 'is_success', 'fail_reason',
            'ngo_id', 'ngo_name',
        ]