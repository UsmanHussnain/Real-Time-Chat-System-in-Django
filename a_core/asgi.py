import os
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
from a_rtchat.routing import websocket_urlpatterns
import a_rtchat

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'a_core.settings')

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            a_rtchat.routing.websocket_urlpatterns
        )
    ),
})