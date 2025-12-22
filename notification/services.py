from .models import Notification
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()

def notify(*, user, type, actor=None, actor_type='user', obj=None, data=None):
    """
    Универсальный helper для создания уведомлений
    """
    Notification.objects.create(
        user=user,
        type=type,
        actor=actor,
        actor_type=actor_type,
        content_object=obj,
        data=data or {}
    )

def notify_bulk(*, users, type, actor=None, actor_type='user', obj=None, data=None):
    notifications = [
        Notification(
            user=user,
            type=type,
            actor=actor,
            actor_type=actor_type,
            content_object=obj,
            data=data or {}
        )
        for user in users
    ]

    Notification.objects.bulk_create(
        notifications,
        batch_size=1000
    )