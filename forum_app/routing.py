# routing.py - WebSocket маршруты

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # WebSocket для конкретной темы форума
    re_path(
        r'ws/forum/topic/(?P<topic_id>\d+)/$',
        consumers.ForumTopicConsumer.as_asgi()
    ),
    
    # WebSocket для личных уведомлений
    re_path(
        r'ws/notifications/$',
        consumers.NotificationConsumer.as_asgi()
    ),
]
