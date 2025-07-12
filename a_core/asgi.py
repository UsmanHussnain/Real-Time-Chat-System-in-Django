import os
import django
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

# Set environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'a_core.settings')

# Setup Django
django.setup()

# Now it's safe to import your routing
from a_rtchat.routing import websocket_urlpatterns

# Create ASGI application
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
