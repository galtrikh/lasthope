from django.db import models

# Create your models here.

class SiteSettings(models.Model):
    maintenance = models.BooleanField(
        default=False,
        verbose_name='Режим технических работ'
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'Настройки сайта'

    class Meta:
        verbose_name = 'Настройки сайта'
        verbose_name_plural = 'Настройки сайта'

        permissions = [
            ('bypass_maintenance', 'Может обходить режим техработ'),
        ]

class AllowedDevIPs(models.Model):
    ip = models.CharField(default='127.0.0.1', verbose_name='Разрешенный IP')
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __srt__(self):
        return 'Разрешенные DEV IP'
    class Meta:
        verbose_name = 'Разрешенные DEV IP'
        verbose_name_plural = 'Разрешенный DEV IP'

class ActionType(models.TextChoices):
    COPY = 'copy', 'Скопировать текст'
    LINK = 'link', 'Перейти по ссылке'

class FooterInfo(models.Model):
    data = models.CharField(max_length=255, verbose_name='Текст')
    action_type = models.CharField(
        max_length=10,
        choices=ActionType.choices,
        default=ActionType.COPY,
        verbose_name='Тип действия'
    )

    copy_data = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Текст скопируется при нажатии'
    )

    link_data = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Ссылка для перехода'
    )

    def __str__(self):
        return 'Информация в футере сайта'
    
    def clean(self):
        from django.core.exceptions import ValidationError

        if self.action_type == ActionType.COPY and not self.copy_data:
            raise ValidationError({'copy_data': 'Заполните текст для копирования'})

        if self.action_type == ActionType.LINK and not self.link_data:
            raise ValidationError({'link_data': 'Заполните ссылку'})

        if self.copy_data and self.link_data:
            raise ValidationError('Можно заполнить только одно поле')

    class Meta:
        verbose_name = 'Информацию в футере сайта'
        verbose_name_plural = 'Информация в футере сайта'
