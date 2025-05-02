# chat/routing.py
from django.urls import re_path

from . import consumers # Import the consumers module from the current directory

# Define the list of WebSocket URL patterns
websocket_urlpatterns = [
    # re_path uses regular expressions for flexible matching
    # r'ws/chat/voice/$' matches the path 'ws/chat/voice/' exactly at the end of the URL
    # consumers.VoiceChatConsumer.as_asgi() maps the matching URL to the VoiceChatConsumer
    # We will create the VoiceChatConsumer in the next steps.
    re_path(r'ws/chat/voice/$', consumers.VoiceChatConsumer.as_asgi()),

    # You could add more WebSocket URL patterns here if needed for other features
    # re_path(r'ws/another/feature/$', consumers.AnotherConsumer.as_asgi()),
]