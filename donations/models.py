from django.db import models
from django.utils import timezone
from django.db.models import Sum
from datetime import timedelta


class Privilegion(models.Model):
    """Привилегия (например: VIP, MVP, донатер месяца)."""
    name          = models.CharField(max_length=255, verbose_name='Название')
    description   = models.TextField(blank=True, verbose_name='Описание')
    price         = models.DecimalField(max_digits=10, decimal_places=2,
                                        verbose_name='Базовая цена')
    duration_days = models.PositiveIntegerField(
        default=30,
        verbose_name='Длительность (дней)',
        help_text='Сколько дней действует привилегия после активации',
    )

    class Meta:
        verbose_name        = 'Привилегия'
        verbose_name_plural = 'Привилегии'
        ordering            = ['price']

    def __str__(self):
        return f'{self.name} ({self.price} ₽)'


class DiscountTier(models.Model):
    """
    Уровни скидок для постоянных донатеров.
    Редактируются в /admin без изменения кода.
    """
    min_total        = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name='Минимальная общая сумма донатов',
    )
    discount_percent = models.PositiveSmallIntegerField(
        verbose_name='Скидка (%)',
        help_text='0–100',
    )
    label            = models.CharField(
        max_length=64, blank=True,
        verbose_name='Метка уровня',
        help_text='Например: «Друг сервера», «Меценат»',
    )

    class Meta:
        verbose_name        = 'Уровень скидки'
        verbose_name_plural = 'Уровни скидок'
        ordering            = ['min_total']

    def __str__(self):
        return f'{self.label or "Уровень"}: от {self.min_total} ₽ → -{self.discount_percent}%'


class Donator(models.Model):
    """Агрегированный профиль донатера по никнейму."""
    nickname     = models.CharField(max_length=255, unique=True,
                                    verbose_name='Никнейм')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2,
                                       default=0, verbose_name='Всего задонатил')

    class Meta:
        verbose_name        = 'Донатер'
        verbose_name_plural = 'Донатеры'
        ordering            = ['-total_amount']

    def __str__(self):
        return f'{self.nickname} ({self.total_amount} ₽)'

    def recalc_total(self):
        """Пересчитывает total_amount по всем донатам никнейма."""
        result = (
            Donation.objects
            .filter(nickname__iexact=self.nickname)
            .aggregate(s=Sum('amount'))['s'] or 0
        )
        self.total_amount = result
        self.save(update_fields=['total_amount'])

    @property
    def discount_tier(self):
        return (
            DiscountTier.objects
            .filter(min_total__lte=self.total_amount)
            .order_by('-min_total')
            .first()
        )

    @property
    def discount_percent(self):
        tier = self.discount_tier
        return tier.discount_percent if tier else 0


class Donation(models.Model):
    """Запись о конкретном донате."""

    class Status(models.TextChoices):
        WAITING   = 'waiting',   'Ожидает активации'
        ACTIVE    = 'active',    'Активен'
        EXPIRED   = 'expired',   'Просрочен'
        COMPLETED = 'completed', 'Завершён'

    nickname         = models.CharField(max_length=255, verbose_name='Никнейм',
                                        db_index=True)
    amount           = models.DecimalField(max_digits=10, decimal_places=2,
                                           verbose_name='Сумма')
    final_amount     = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name='Итоговая сумма (со скидкой)',
        help_text='Заполняется автоматически при сохранении',
    )
    discount_applied = models.PositiveSmallIntegerField(
        default=0, verbose_name='Применена скидка (%)',
    )
    status           = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.WAITING,
        verbose_name='Статус',
        db_index=True,
    )
    date             = models.DateTimeField(auto_now_add=True,
                                            verbose_name='Дата создания')
    activated_at     = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Дата активации',
        help_text='Заполняется автоматически при нажатии «Активировать»',
    )
    end_date         = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Действует до',
        db_index=True,
        help_text='Вычисляется автоматически из даты активации + срока привилегий',
    )
    privilegion      = models.ManyToManyField(
        Privilegion, blank=True,
        related_name='donations',
        verbose_name='Привилегии',
    )
    comment          = models.TextField(blank=True, verbose_name='Комментарий')

    class Meta:
        verbose_name        = 'Донат'
        verbose_name_plural = 'Донаты'
        ordering            = ['-date']
        indexes             = [
            models.Index(fields=['nickname', '-date']),
            models.Index(fields=['status', 'end_date']),
        ]

    def __str__(self):
        return f'{self.nickname} — {self.final_amount} ₽ ({self.date:%d.%m.%Y}) [{self.get_status_display()}]'

    # ── Computed properties ───────────────────────────────────────────────

    @property
    def is_expired(self):
        return self.end_date is not None and self.end_date < timezone.now()

    @property
    def is_pending_collection(self):
        """Активирован, просрочен, но ещё не завершён — нужно закрыть."""
        return self.status == self.Status.EXPIRED

    # ── Автоматика ───────────────────────────────────────────────────────

    def apply_discount(self):
        """Вычисляет final_amount по скидке текущего донатера."""
        try:
            donator = Donator.objects.get(nickname__iexact=self.nickname)
            pct = donator.discount_percent
        except Donator.DoesNotExist:
            pct = 0

        self.discount_applied = pct
        if pct:
            self.final_amount = self.amount * (100 - pct) / 100
        else:
            self.final_amount = self.amount

    def activate(self):
        """
        Переводит донат в статус ACTIVE, запускает таймер.
        end_date = activated_at + max(duration_days) выбранных привилегий.
        """
        if self.status != self.Status.WAITING:
            return False

        self.activated_at = timezone.now()
        self.status = self.Status.ACTIVE

        # Считаем срок из привилегий (нужен pk, поэтому after save M2M)
        max_days = (
            self.privilegion.aggregate(m=models.Max('duration_days'))['m'] or 30
        )
        self.end_date = self.activated_at + timedelta(days=max_days)
        self.save(update_fields=['status', 'activated_at', 'end_date'])
        return True

    def sync_expired_status(self):
        """
        Если активен и срок вышел — переводит в EXPIRED.
        Вызывается при каждом просмотре списка (или по крону).
        """
        if self.status == self.Status.ACTIVE and self.is_expired:
            self.status = self.Status.EXPIRED
            self.save(update_fields=['status'])

    def complete(self):
        """Вручную закрыть донат (EXPIRED → COMPLETED)."""
        if self.status in (self.Status.EXPIRED, self.Status.ACTIVE):
            self.status = self.Status.COMPLETED
            self.save(update_fields=['status'])
            return True
        return False

    def save(self, *args, **kwargs):
        if not self.pk or kwargs.pop('recalc', False):
            self.apply_discount()
        super().save(*args, **kwargs)

        # Обновляем агрегат донатера
        donator, _ = Donator.objects.get_or_create(
            nickname__iexact=self.nickname,
            defaults={'nickname': self.nickname},
        )
        donator.recalc_total()
