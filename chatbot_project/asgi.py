# chatbot_project/asgi.py
import os
import django # Import django

# Set the Django settings module for the application
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chatbot_project.settings')

# Configure Django settings *immediately* after setting the module path
# This is the ONLY place django.setup() should be called in the entry point
django.setup()

# --- NOW import the necessary components AFTER django.setup() has run ---
# This ensures that when these modules are imported, Django's settings and
# app registry are already configured, preventing the ImproperlyConfigured error.
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

# Import your custom JWT authentication middleware (now safe to import)
from .middleware import JwtAuthMiddlewareStack

# Import your chat application's routing file (now safe to import)
from chat import routing


# Get Django's standard ASGI application (handles HTTP requests)
# This is called *after* django.setup()
django_asgi_app = get_asgi_application()

# Define the root ASGI application
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        JwtAuthMiddlewareStack(
            URLRouter(
                routing.websocket_urlpatterns
            )
        )
    ),
})