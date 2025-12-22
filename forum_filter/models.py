from django.db import models
from django.conf import settings
from forum_app.models import ForumPost

# Create your models here.

class ForbiddenWord(models.Model):
    word = models.CharField(max_length=100, unique=True, verbose_name='Слово')
    enabled = models.BooleanField(default=True, verbose_name='Фильтрация включена')

    def __str__(self):
        return self.word
    
    class Meta:
        verbose_name = 'Запрещенное слово'
        verbose_name_plural = 'Черный список слов'

class AllowedIP(models.Model):
    ip = models.GenericIPAddressField(unique=True)
    comment = models.CharField(max_length=255, blank=True, verbose_name='Комментарий')

    def __str__(self):
        return self.ip
    
    class Meta:
        verbose_name = 'Разрешенный IP'
        verbose_name_plural = 'Разрешенные IP'

class ModerationViolation(models.Model):
    class Type(models.TextChoices):
        IP = 'ip', 'Запрещённый IP'
        WORD = 'word', 'Запрещённое слово'
        OBFUSCATION = 'obfuscation', 'Попытка обхода'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    post = models.ForeignKey('forum_app.ForumPost', on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=Type.choices)
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class UserWarning(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='Пользователь')
    post = models.ForeignKey(ForumPost, on_delete=models.CASCADE, null=True, verbose_name='Пост')
    reason = models.CharField(max_length=255, verbose_name='Причина')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата')

    class Meta:
        verbose_name = 'Предупреждение'
        verbose_name_plural = 'Предупреждения'

