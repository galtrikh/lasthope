from django.contrib import admin
from django.db.models import Sum
from django.utils import timezone
from django.utils.html import format_html

from .models import Donation, Donator, DiscountTier, Privilegion


@admin.register(Privilegion)
class PrivilegionAdmin(admin.ModelAdmin):
    list_display  = ('name', 'price', 'duration_days')
    search_fields = ('name',)
    ordering      = ('price',)


@admin.register(DiscountTier)
class DiscountTierAdmin(admin.ModelAdmin):
    list_display = ('label', 'min_total', 'discount_percent')
    ordering     = ('min_total',)


# ─────────────────────────────────────────────────────────────
# Donation
# ─────────────────────────────────────────────────────────────

class StatusFilter(admin.SimpleListFilter):
    title          = 'Статус'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return Donation.Status.choices

    def queryset(self, request, qs):
        if self.value():
            return qs.filter(status=self.value())
        return qs


class ExpiredSoonFilter(admin.SimpleListFilter):
    title          = 'Срок'
    parameter_name = 'expiry'

    def lookups(self, request, model_admin):
        return [
            ('soon',    'Истекает в течение 3 дней'),
            ('overdue', 'Просрочен'),
        ]

    def queryset(self, request, qs):
        now = timezone.now()
        if self.value() == 'soon':
            from datetime import timedelta
            return qs.filter(
                status=Donation.Status.ACTIVE,
                end_date__lte=now + timedelta(days=3),
                end_date__gte=now,
            )
        if self.value() == 'overdue':
            return qs.filter(end_date__lt=now).exclude(status=Donation.Status.COMPLETED)
        return qs


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display    = (
        'nickname', 'amount_display', 'discount_applied',
        'privilegion_list', 'status_display', 'date',
        'end_date_display',
    )
    list_filter     = (StatusFilter, ExpiredSoonFilter, 'privilegion')
    search_fields   = ('nickname', 'comment')
    ordering        = ('-date',)
    readonly_fields = ('date', 'activated_at', 'final_amount', 'discount_applied')
    filter_horizontal = ('privilegion',)
    actions         = ['activate_selected', 'complete_selected']

    fieldsets = (
        (None, {
            'fields': ('nickname', 'privilegion', 'comment'),
        }),
        ('Сумма', {
            'fields': ('amount', 'final_amount', 'discount_applied'),
        }),
        ('Статус и сроки', {
            'fields': ('status', 'date', 'activated_at', 'end_date'),
        }),
    )

    # ── Кастомные колонки ──────────────────────────────────────────────

    @admin.display(description='Сумма', ordering='final_amount')
    def amount_display(self, obj):
        if obj.discount_applied:
            return format_html(
                '{} ₽&nbsp;<small style="opacity:.5;text-decoration:line-through">{}</small>',
                obj.final_amount, obj.amount,
            )
        return format_html('{} ₽', obj.final_amount)

    @admin.display(description='Привилегии')
    def privilegion_list(self, obj):
        return ', '.join(p.name for p in obj.privilegion.all()) or '—'

    STATUS_COLORS = {
        Donation.Status.WAITING:   ('#888', '⏳'),
        Donation.Status.ACTIVE:    ('#22c55e', '✅'),
        Donation.Status.EXPIRED:   ('#ef4444', '⚠️'),
        Donation.Status.COMPLETED: ('#64748b', '✔'),
    }

    @admin.display(description='Статус', ordering='status')
    def status_display(self, obj):
        color, icon = self.STATUS_COLORS.get(obj.status, ('#888', ''))
        return format_html(
            '<span style="color:{}">{} {}</span>',
            color, icon, obj.get_status_display(),
        )

    @admin.display(description='Истекает', ordering='end_date')
    def end_date_display(self, obj):
        if not obj.end_date:
            return '—'
        color = 'red' if obj.is_expired and obj.status != Donation.Status.COMPLETED else 'inherit'
        return format_html(
            '<span style="color:{}">{}</span>',
            color,
            obj.end_date.strftime('%d.%m.%Y %H:%M'),
        )

    # ── Actions ────────────────────────────────────────────────────────

    @admin.action(description='Активировать выбранные (WAITING → ACTIVE)')
    def activate_selected(self, request, qs):
        count = 0
        for obj in qs.filter(status=Donation.Status.WAITING):
            obj.activate()
            count += 1
        self.message_user(request, f'Активировано: {count}')

    @admin.action(description='Завершить выбранные (→ COMPLETED)')
    def complete_selected(self, request, qs):
        count = 0
        for obj in qs.exclude(status=Donation.Status.COMPLETED):
            obj.complete()
            count += 1
        self.message_user(request, f'Завершено: {count}')

    def save_model(self, request, obj, form, change):
        obj.apply_discount()
        super().save_model(request, obj, form, change)


# ─────────────────────────────────────────────────────────────
# Donator
# ─────────────────────────────────────────────────────────────

@admin.register(Donator)
class DonatorAdmin(admin.ModelAdmin):
    list_display    = ('nickname', 'total_amount', 'tier_display', 'recalc_link')
    search_fields   = ('nickname',)
    ordering        = ('-total_amount',)
    readonly_fields = ('total_amount',)
    actions         = ['recalculate_totals']

    @admin.display(description='Уровень скидки')
    def tier_display(self, obj):
        tier = obj.discount_tier
        if not tier:
            return '—'
        return format_html(
            '<span style="color:#22c55e">-{}% — {}</span>',
            tier.discount_percent, tier.label or '',
        )

    @admin.display(description='')
    def recalc_link(self, obj):
        return format_html(
            '<a href="?recalc={}">пересчитать</a>', obj.pk,
        )

    @admin.action(description='Пересчитать суммы донатов')
    def recalculate_totals(self, request, qs):
        for donator in qs:
            donator.recalc_total()
        self.message_user(request, f'Пересчитано: {qs.count()}')

    def changelist_view(self, request, extra_context=None):
        pk = request.GET.get('recalc')
        if pk:
            try:
                d = Donator.objects.get(pk=pk)
                d.recalc_total()
                self.message_user(request, f'Пересчитано для {d.nickname}')
            except Donator.DoesNotExist:
                pass

        extra_context = extra_context or {}
        extra_context['grand_total'] = (
            Donator.objects.aggregate(s=Sum('total_amount'))['s'] or 0
        )
        return super().changelist_view(request, extra_context)
