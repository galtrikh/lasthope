from django.db import models
from django.conf import settings
from django_ckeditor_5.fields import CKEditor5Field

# Create your models here.

class ForumCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Наименование')
    description = models.TextField(blank=True, null=True, verbose_name='Описание')
    slug = models.SlugField(unique=True, verbose_name='Вид ссылки')
    visible = models.BooleanField(default=True, verbose_name='Отображается')
    
    def __str__(self):
        return self.name
    
    class Meta:
        permissions = [
            ('can_see_hidden_cats', 'Видеть скрытые категории'),
            ('can_hide_cats', 'Скрывать категории'),
        ]
        verbose_name = 'Категорию'
        verbose_name_plural = 'Категории'


class ForumTopic(models.Model):
    category = models.ForeignKey(
        ForumCategory,
        on_delete=models.CASCADE,
        related_name='topics'
        , verbose_name='Категория'
    )
    title = models.CharField(max_length=255, verbose_name='Заголовок')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='topics'
        , verbose_name='Автор'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Изменено')
    pinned = models.BooleanField(default=False, verbose_name='Закреплено')  # закрепление темы
    visible = models.BooleanField(default=True, verbose_name='Отображается')
    closed = models.BooleanField(default=False, verbose_name='Тема закрыта')

    @property
    def get_posts(self):
        return ForumPost.objects.filter(topic=self).order_by('id')

    def __str__(self):
        return self.title
    
    class Meta:
        permissions = [
            ('can_pin_topic', 'Закреплять топики'),
            ('can_see_hidden_topics', 'Видеть скрытые топики'),
            ('can_hide_topic', 'Скрывать топики'),
            ('can_close_topic', 'Закрывать топики'),
            ('can_delete_topic', 'Удалять топики'),
            ('can_create_topic', 'Создавать новые темы')
        ]
        verbose_name = 'Тему'
        verbose_name_plural = 'Темы'

class ForumPost(models.Model):
    topic = models.ForeignKey(
        ForumTopic,
        on_delete=models.CASCADE,
        related_name='posts'
        , verbose_name='Тема'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='posts'
        , verbose_name='Автор'
    )
    content = CKEditor5Field(config_name='default', verbose_name='Текст поста')
    pinned = models.BooleanField(default=False, verbose_name='Закреплен')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Изменен')
    edited = models.BooleanField(default=False, verbose_name='Изменен')
    visible = models.BooleanField(default=True, verbose_name='Отображается')
    deleted = models.BooleanField(default=False, verbose_name='Удален пользователем')

    def __str__(self):
        return f"Публикация пользователя {self.author} в теме {self.topic}"
    
    class Meta:
        permissions = [
            ('can_see_hidden_post', 'Видеть скрытые посты'),
            ('can_hide_post', 'Скрывать посты'),
            ('can_pin_post', 'Закреплять посты'),
            ('can_edit_post', 'Редактировать посты'),
            ('can_edit_another_post', 'Редактировать чужие посты'),
            ('can_delete_post', 'Удалять посты'),
            ('can_really_delete_post', 'Реально удалять посты'),
            ('can_post', 'Писать на форуме'),
            ('can_post_closed', 'Писать даже в закрытые темы')
        ]
        verbose_name = 'Пост'
        verbose_name_plural = 'Посты'
