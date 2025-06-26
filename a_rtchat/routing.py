from django.urls import path
from . import consumers
from .consumers import *

websocket_urlpatterns = [
   path('ws/chatroom/<chatroom_name>/', consumers.ChatroomConsumer.as_asgi()),
   path('ws/online_status/', OnlineStatusConsumer.as_asgi()),
]
