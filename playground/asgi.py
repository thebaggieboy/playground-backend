import os
from django.core.asgi import get_asgi_application

# Set Django settings module FIRST
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playground.settings')

# Initialize Django ASGI app BEFORE importing dependencies that require Django
django_asgi_app = get_asgi_application()

# Now import Channels and routing
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
 
application = ProtocolTypeRouter({
    "http": django_asgi_app,  # Use the pre-loaded ASGI app
   
})