#!/bin/bash
set -e

echo "Starting Celery Beat..."
celery -A notification_service beat -l info &

echo "Starting Celery Worker..."
celery -A notification_service worker -l info --concurrency=1 -P solo &

echo "Starting Daphne..."
exec daphne -b 0.0.0.0 -p ${PORT:-8000} notification_service.asgi:application