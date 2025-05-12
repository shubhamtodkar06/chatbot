# chat/routing.py
from django.urls import re_path

from . import consumers # Import the consumers module from the current directory

# Define the list of WebSocket URL patterns
websocket_urlpatterns = [
    re_path(r'ws/chat/voice/$', consumers.VoiceChatConsumer.as_asgi()),

    ]