#!/bin/sh
python manage.py migrate
celery -A notification_service worker --loglevel=info &
celery -A notification_service beat --loglevel=info &
exec python manage.py runserver 0.0.0.0:${PORT:-8000}