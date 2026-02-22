from django.db import models
from django.conf import settings
from PIL import Image as PilImage
from io import BytesIO
from django.core.files.base import ContentFile
from notification.models import Notification
from notification.services import notify_bulk
from django.contrib.auth.models import User
from django.db.models import Count
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.utils import timezone

User = get_user_model()


class ServerPlayer(models.Model):
    """
    Статистика игрока на сервере CS:S
    Хранит данные, собранные с сервера через Source Query
    """
    steam_id = models.CharField(
        max_length=32, 
        unique=True, 
        db_index=True,
        verbose_name='Steam ID'
    )
    nickname = models.CharField(
        max_length=64, 
        verbose_name='Последний никнейм',
        db_index=True
    )
    
    # Статистика
    total_playtime = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Общее время игры (секунды)',
        help_text='Общее время на сервере в секундах'
    )
    total_kills = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Всего убийств'
    )
    total_deaths = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Всего смертей'
    )
    total_escapes = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Успешных побегов',
        help_text='Количество успешных побегов из тюрьмы'
    )
    total_rounds = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Сыгранных раундов'
    )
    
    # Дополнительная статистика
    headshots = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Хедшотов'
    )
    longest_killstreak = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Максимальная серия убийств'
    )
    
    # Метаданные
    first_seen = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Первый вход'
    )
    last_seen = models.DateTimeField(
        auto_now=True,
        verbose_name='Последний вход',
        db_index=True
    )
    is_banned = models.BooleanField(
        default=False,
        verbose_name='Забанен'
    )
    
    # Связь с пользователем форума (опционально)
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='server_stats',
        verbose_name='Пользователь форума'
    )
    
    class Meta:
        verbose_name = 'Статистика игрока'
        verbose_name_plural = 'Статистика игроков'
        ordering = ['-total_kills', '-total_playtime']
        indexes = [
            models.Index(fields=['-total_kills', '-total_playtime']),
            models.Index(fields=['-last_seen']),
        ]
    
    def __str__(self):
        return f"{self.nickname} ({self.steam_id})"
    
    @property
    def playtime_hours(self):
        """Время игры в часах"""
        return round(self.total_playtime / 3600, 1)
    
    @property
    def kd_ratio(self):
        """Соотношение убийств к смертям"""
        if self.total_deaths == 0:
            return self.total_kills
        return round(self.total_kills / self.total_deaths, 2)
    
    @property
    def headshot_percentage(self):
        """Процент хедшотов"""
        if self.total_kills == 0:
            return 0
        return round(self.headshots * 100 / self.total_kills, 1)
    
    @property
    def is_online(self):
        """Был ли игрок онлайн в последние 5 минут"""
        if not self.last_seen:
            return False
        return timezone.now() - self.last_seen < timezone.timedelta(minutes=5)


class ServerPlayerSession(models.Model):
    """
    История игровых сессий
    Для отслеживания активности и построения графиков
    """
    player = models.ForeignKey(
        ServerPlayer,
        on_delete=models.CASCADE,
        related_name='sessions',
        verbose_name='Игрок'
    )
    session_start = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Начало сессии',
        db_index=True
    )
    session_end = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Конец сессии'
    )
    duration = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Длительность (секунды)'
    )
    kills_in_session = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Убийств за сессию'
    )
    deaths_in_session = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Смертей за сессию'
    )
    
    class Meta:
        verbose_name = 'Игровая сессия'
        verbose_name_plural = 'Игровые сессии'
        ordering = ['-session_start']
        indexes = [
            models.Index(fields=['-session_start']),
        ]
    
    def __str__(self):
        return f"{self.player.nickname} - {self.session_start.strftime('%Y-%m-%d %H:%M')}"


class ServerStatSnapshot(models.Model):
    """
    Снимок состояния сервера
    Для построения графиков онлайна и истории
    """
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name='Время снимка'
    )
    players_online = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name='Игроков онлайн'
    )
    current_map = models.CharField(
        max_length=64,
        verbose_name='Текущая карта'
    )
    server_online = models.BooleanField(
        default=True,
        verbose_name='Сервер онлайн'
    )
    
    class Meta:
        verbose_name = 'Снимок сервера'
        verbose_name_plural = 'Снимки сервера'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.timestamp.strftime('%Y-%m-%d %H:%M')} - {self.players_online} игроков"

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

    