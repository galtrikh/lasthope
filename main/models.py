from django.db import models
from django.conf import settings
from PIL import Image as PilImage
from io import BytesIO
from django.core.files.base import ContentFile
from notification.models import Notification
from notification.services import notify_bulk
from django.contrib.auth.models import User
from django.db.models import Count

# Create your models here.

class VoteBox(models.Model):
    title = models.CharField(max_length=255, verbose_name='Заголовок')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='votes'
        , verbose_name='Автор'
    )
    multiple = models.BooleanField(default=False, verbose_name='Множественный выбор')
    active = models.BooleanField(default=True, verbose_name='Голосование активно')
    closed = models.BooleanField(default=False, verbose_name='Голосование закрыто', help_text='(не отображается)')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата начала')
    notified_finished = models.BooleanField(default=False, verbose_name='Уведомления об окончании разосланы')
    winner = models.ForeignKey(
        'VoteBoxItem',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+'
        , verbose_name='Выбран вариант'
    )

    def __str__(self):
        return self.title
    
    def _get_winner_item(self):
                return (
                    VoteBoxItem.objects
                    .filter(box=self)
                    .annotate(votes_count=Count('vote_item_vote'))
                    .order_by('-votes_count', 'id')
                    .first()
                )

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        if not is_new:
            old_active = (
                VoteBox.objects
                .filter(pk=self.pk)
                .values_list('active', flat=True)
                .first()
            )
        else:
            old_active = None

        super().save(*args, **kwargs)

        # active -> False
        if old_active is True and self.active is False and not self.notified_finished:
            users = User.objects.all()
            winner = self._get_winner_item()
            self.winner = winner
            VoteBox.objects.filter(pk=self.pk).update(
                winner=winner,
                notified_finished=True
            )
            notify_bulk(
                users=users,
                type=Notification.Type.POLL_FINISHED,
                data={
                    "title": self.title,
                    "winner": winner.text
                }
            )

    class Meta:
        verbose_name = "Голосование"
        verbose_name_plural = "Голосования"
        permissions = [
            ('can_vote', 'Может голосовать')
        ]

class VoteBoxItem(models.Model):
    box = models.ForeignKey(
        VoteBox,
        on_delete=models.CASCADE,
        related_name='vote_item',
        verbose_name='Голосование'
    )
    text = models.CharField(max_length=255, verbose_name='Текст')
    
    @property
    def is_winner(self):
        if not self.box.winner_id:
            return False
        return self.box.winner_id == self.id
    
    def __str__(self):
        return self.text
    
    class Meta:
        verbose_name = "Опцию голосования"
        verbose_name_plural = "Опции голосований"
    
class VoteBoxVote(models.Model):
    box = models.ForeignKey(
        VoteBox,
        on_delete=models.CASCADE,
        related_name='vote_box',
        verbose_name='Голосование'
    )
    item = models.ForeignKey(
        VoteBoxItem,
        on_delete=models.CASCADE,
        related_name='vote_item_vote',
        verbose_name='Выбор'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='poll_votes',
        verbose_name='Пользователь'
    )
    voted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return 'Голос'

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['box', 'item', 'user'],
                name='unique_vote_per_item'
            )
        ]
        verbose_name = 'Голос'
        verbose_name_plural = 'Голоса'

class MainBanner(models.Model):
    width = models.CharField(default='full', verbose_name='Ширина', help_text='[от 1 до 100] Значение указывается в процентах ширины экрана')
    hidden = models.BooleanField(default=False, verbose_name='Скрыт')
    image = models.ImageField(null=True, blank=True, upload_to='banner/', verbose_name='Картинка')
    image_small = models.ImageField(null=True, blank=True, upload_to='banner/small/')

    def __str__(self):
        return 'Настройки баннера'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.image:
            self.make_small_image()

    def make_small_image(self):
        img = PilImage.open(self.image.path)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.thumbnail((400, 400))
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=30, optimize=True)
        file_name = self.image.name.split('/')[-1]
        small_name = f'small_{file_name}'
        self.image_small.save(small_name, ContentFile(buffer.getvalue()), save=False)
        super().save(update_fields=['image_small'])

    @property
    def small_url(self):
        return self.image_small.url if self.image_small else self.image.url


    class Meta:
        verbose_name = "Баннер на главной"
        verbose_name_plural = "Баннер на главной"

class HelpAccardion(models.Model):
    question = models.CharField(max_length=1024, verbose_name='Вопрос')
    text = models.TextField(verbose_name='Ответ')

    def __str__(self):
        return self.question

    class Meta:
        verbose_name = "Пункт в разделе помощь"
        verbose_name_plural = "Пункты в разделе помощь"
    
class MainRules(models.Model):
    text = models.TextField(verbose_name='Правило')

    def __str__(self):
        return 'Правило'

    class Meta:
        verbose_name = "Правило"
        verbose_name_plural = "Правила"

    