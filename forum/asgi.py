# asgi.py - ASGI конфигурация с поддержкой WebSocket

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

# Устанавливаем настройки Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')

# Инициализируем Django ASGI application рано, чтобы AppRegistry
# был заполнен до импорта кода, который может использовать ORM
django_asgi_app = get_asgi_application()

# Импортируем routing после инициализации Django
from forum_app import routing

application = ProtocolTypeRouter({
    # HTTP запросы обрабатываются обычным Django
    "http": django_asgi_app,
    
    # WebSocket запросы обрабатываются Channels
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                routing.websocket_urlpatterns
            )
        )
    ),
})
