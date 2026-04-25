import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import notification.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'notification_service.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter(
        notification.routing.websocket_urlpatterns
    ),
})