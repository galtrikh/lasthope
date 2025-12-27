from django.conf import settings
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Notification(models.Model):
    class Type(models.TextChoices):
        ADMIN = 'admin', 'Сообщение от администрации'

        POST_EDITED = 'post_edited', 'Пост отредактирован'
        POST_PINNED = 'post_pinned', 'Пост закреплён'
        POST_UNPINNED = 'post_unpinned', 'Пост откреплён'
        POST_DELETED = 'post_deleted', 'Пост удален'

        TOPIC_DELETED = 'topic_deleted', 'Топик удалён'
        TOPIC_PINNED = 'topic_pinned', 'Топик закреплен'
        TOPIC_UNPINNED = 'topic_unpinned', 'Топик откреплен'
        TOPIC_CLOSED = 'topic_closed', 'Обсуждение закрыто'
        TOPIC_UNCLOSED = 'topic_unclosed', 'Обсуждение открыто'
        TOPIC_HIDDEN = 'topic_hidden', 'Топик скрыт'
        TOPIC_SHOWN = 'topic_shown', 'Топик отображен'

        GROUP_ADDED = 'group_added', 'Вам выдана роль'
        GROUP_REMOVED = 'group_removed', 'Ваша роль была отозвана'
        GROUPS_CLEARED = 'groups_cleared', 'Роли очищены'
        PERMISSION_ADDED = 'permission_added', 'Вам выдано право'
        PERMISSION_REMOVED = 'permission_removed', 'Ваше право было отозвано'
        PERMISSIONS_CLEARED = 'permissions_cleared', 'Права очищены'

        POLL_FINISHED = 'poll_finished', 'Голосование завершено'
        WARNING = 'warning', 'Важное уведомление!'
        MODERATION_ALERT = 'moderation_alert', 'Зафиксировано нарушение'
        POST_BLOCKED = 'post_blocked', 'Ваш пост был автоматически скрыт системой'
        OTHER = 'other', 'Другое'
        
        USER = 'user',
        SYSTEM = 'system'
        

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
        , verbose_name='Кому отправлено'
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='actor_notifications'
        , verbose_name='Отправитель'
    )

    actor_type = models.CharField(
        max_length=20,
        default=Type.USER,
        choices=Type.choices,
        help_text='USER | SYSTEM'  # user | system
        , verbose_name='Тип отправителя'
    )

    type = models.CharField(
        max_length=32,
        choices=Type.choices
        , verbose_name='Тип уведомления'
        , help_text='НЕ ВЫБИРАТЬ USER И SYSTEM ЭТО ВЫЗОВЕТ ОШИБКУ'
    )

    # универсальная связь
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
        , verbose_name='Уведомление привязано к'
    )
    object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name='ID объекта')
    content_object = GenericForeignKey()

    data = models.JSONField(default=dict, blank=True, verbose_name='Данные', help_text='В формате JSON')

    is_read = models.BooleanField(default=False, verbose_name='Прочитано')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата')

    class Meta:
        ordering = ['-id']  # ВАЖНО: быстрее, чем created_at
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', 'id']),
            models.Index(fields=['type']),
        ]
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'

    def __str__(self):
        return f'{self.user} — {self.type}'
