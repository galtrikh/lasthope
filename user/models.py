from django.db import models
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.conf import settings
from django.contrib.auth.models import Group
from django.utils import timezone

from django.contrib.auth import get_user_model

User = get_user_model()

# Create your models here.
class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name='Пользователь'
    )
    displayname = models.CharField(blank=True, max_length=255, verbose_name='Отображаемое имя')
    servername = models.CharField(blank=True, max_length=255, verbose_name='Ник в игре')
    bio = models.TextField(null=True, blank=True, verbose_name='О себе')
    avatar = models.ImageField(blank=True, upload_to='users/avatar/', null=True, verbose_name='Аватар')
    
    last_seen = models.DateTimeField(blank=True, null=True, verbose_name='Последняя активность')  # новое поле

    def is_online(self):
        """Считаем пользователя онлайн, если активен последние 5 минут"""
        if not self.last_seen:
            return False
        now = timezone.now()
        return (now - self.last_seen).total_seconds() < 300  # 5 минут

    def __str__(self):
        return f'[{self.user.username}] {self.displayname}'
    
    class Meta:
        verbose_name = "Профиль"
        permissions = [
            ('edit_profile', 'Редактировать чужие профили'),
            ('edit_user_perms', 'Менять права'),
            ('can_edit_profile_gropus', 'Редактировать роли'),
            ('see_full_profile', 'Видеть полный профиль'),
            ('safety', 'Защита от редактирования')
        ]

class GroupProfile(models.Model):
    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name='profile'
        , verbose_name='Роль'
    )
    style = models.CharField(
        null=True,
        blank=True,
        help_text='Tailwind-классы'
        , verbose_name='Стили роли'
    )
    display_priority = models.IntegerField(
        default=1,
        help_text='Приоритет отображения, если групп несколько будет отображена в чате самая значимая'
        , verbose_name='Приоритет'
    )

    def __str__(self):
        return f"{self.group.name} ({self.style})"
    
    class Meta:
        verbose_name = 'Дополнительно'

class Room(models.Model):
    name = models.CharField(max_length=255, verbose_name='Название комнаты')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages', verbose_name='Отправитель сообщений из этой комнаты')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages', verbose_name='Получатель сообщений из этой комнаты')

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Комната"
        verbose_name_plural = "Комнаты"

class Message(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='messages', verbose_name='Комната')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages_in_room', verbose_name='Отправитель')
    content = models.TextField(verbose_name='Содержание сообщения')
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name='Дата и время отправки')
    is_read = models.BooleanField(default=False, verbose_name='Прочитано')

    def __str__(self):
        return f'Message from {self.sender} in {self.room} at {self.timestamp}'
    
    class Meta:
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"