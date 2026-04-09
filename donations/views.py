from decimal import Decimal
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Max, Sum, Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import DonationFilterForm, DonationForm
from .models import Donation, DiscountTier, Donator, Privilegion
import json


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _sync_expired(qs):
    """
    Переводит в EXPIRED все ACTIVE донаты, у которых вышел срок.
    Вызывается при каждом открытии списка — лёгкая операция (bulk update).
    """
    now = timezone.now()
    qs.filter(status=Donation.Status.ACTIVE, end_date__lt=now).update(
        status=Donation.Status.EXPIRED
    )


def _apply_filters(qs, form: DonationFilterForm):
    if not form.is_valid():
        return qs

    d = form.cleaned_data

    if d.get('search'):
        qs = qs.filter(nickname__icontains=d['search'])

    if d.get('status'):
        qs = qs.filter(status=d['status'])

    if d.get('privilegion'):
        qs = qs.filter(privilegion=d['privilegion'])

    if d.get('date_from'):
        qs = qs.filter(date__date__gte=d['date_from'])
    if d.get('date_to'):
        qs = qs.filter(date__date__lte=d['date_to'])

    sort = d.get('sort') or '-date'
    if sort in {'-date', 'date', '-final_amount', 'final_amount', 'nickname'}:
        qs = qs.order_by(sort)

    return qs


def _stats(qs):
    return qs.aggregate(total_sum=Sum('final_amount'), total_count=Count('id'))


# ─────────────────────────────────────────────────────────────
# AJAX
# ─────────────────────────────────────────────────────────────

@require_GET
def ajax_discount(request):
    """GET /donations/ajax/discount/?nickname=<str>"""
    nickname = request.GET.get('nickname', '').strip()
    if not nickname:
        return JsonResponse({'found': False, 'percent': 0, 'total': 0, 'tier': ''})
    return JsonResponse(DonationForm.get_discount_for_nickname(nickname))


@require_GET
def ajax_privilegion_price(request):
    """GET /donations/ajax/price/?ids=1,2,3"""
    raw = request.GET.get('ids', '')
    ids = [int(i) for i in raw.split(',') if i.strip().isdigit()]
    if not ids:
        return JsonResponse({'price': 0, 'max_days': 0})

    qs       = Privilegion.objects.filter(pk__in=ids)
    total    = qs.aggregate(s=Sum('price'))['s'] or Decimal('0')
    max_days = qs.aggregate(m=Max('duration_days'))['m'] or 0
    return JsonResponse({'price': float(total), 'max_days': max_days})


# ─────────────────────────────────────────────────────────────
# Create
# ─────────────────────────────────────────────────────────────

@staff_member_required
def donation_create(request):
    form = DonationForm(request.POST or None)

    # Собираем все привилегии одним запросом, без лишних полей
    privileges_qs = Privilegion.objects.order_by('price').values(
        'id', 'name', 'price', 'duration_days'
    )

    if request.method == 'POST' and form.is_valid():
        donation = form.save()
        return redirect('donations:list')

    return render(request, 'donations/create.html', {
        'form': form,
        'privileges': list(privileges_qs),  # <-- передаём в контекст
    })


# ─────────────────────────────────────────────────────────────
# List
# ─────────────────────────────────────────────────────────────

@staff_member_required
def donation_list(request):
    """
    Структура:
      1. Блок EXPIRED — просроченные, ещё не завершённые
      2. Основной список со всеми фильтрами
      3. Сайдбар — топ донатеров + уровни скидок
    """
    # Синхронизируем статусы перед отображением
    _sync_expired(Donation.objects)

    now = timezone.now()

    # Просроченные (EXPIRED) — наверху
    expired_qs = (
        Donation.objects
        .filter(status=Donation.Status.EXPIRED)
        .prefetch_related('privilegion')
        .order_by('end_date')
    )
    expired_stats = _stats(expired_qs)

    # Основной список
    filter_form = DonationFilterForm(request.GET or None)
    main_qs = Donation.objects.prefetch_related('privilegion')
    main_qs = _apply_filters(main_qs, filter_form)
    main_stats = _stats(main_qs)

    # Топ-10 донатеров (tier подтягивается без N+1)
    tiers = list(DiscountTier.objects.order_by('-min_total'))
    top_donators = list(Donator.objects.order_by('-total_amount')[:10])
    for d in top_donators:
        d.tier = next((t for t in tiers if d.total_amount >= t.min_total), None)

    return render(request, 'donations/list.html', {
        'expired':        expired_qs,
        'expired_stats':  expired_stats,
        'donations':      main_qs,
        'main_stats':     main_stats,
        'filter_form':    filter_form,
        'top_donators':   top_donators,
        'discount_tiers': tiers,
        'now':            now,
        'Status':         Donation.Status,
    })


# ─────────────────────────────────────────────────────────────
# Activate  (WAITING → ACTIVE)
# ─────────────────────────────────────────────────────────────

@staff_member_required
@require_POST
def donation_activate(request, pk):
    """
    Запускает донат: WAITING → ACTIVE.
    end_date вычисляется здесь: activated_at + max(duration_days).
    """
    donation = get_object_or_404(Donation, pk=pk)
    is_ajax  = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if donation.status != Donation.Status.WAITING:
        msg = 'Донат уже активирован или завершён.'
        if is_ajax:
            return JsonResponse({'ok': False, 'error': msg})
        messages.warning(request, msg)
        return redirect('donations:list')

    ok = donation.activate()

    if is_ajax:
        return JsonResponse({
            'ok':       ok,
            'pk':       pk,
            'end_date': donation.end_date.strftime('%d.%m.%Y %H:%M') if donation.end_date else '',
            'status':   donation.get_status_display(),
        })

    if ok:
        messages.success(
            request,
            f'Донат «{donation.nickname}» активирован. '
            f'Действует до {donation.end_date:%d.%m.%Y %H:%M}.'
        )
    return redirect('donations:list')


# ─────────────────────────────────────────────────────────────
# Complete  (EXPIRED / ACTIVE → COMPLETED)
# ─────────────────────────────────────────────────────────────

@staff_member_required
@require_POST
def donation_complete(request, pk):
    """Вручную закрывает донат."""
    donation = get_object_or_404(Donation, pk=pk)
    is_ajax  = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if donation.status == Donation.Status.COMPLETED:
        msg = 'Донат уже завершён.'
        if is_ajax:
            return JsonResponse({'ok': False, 'error': msg})
        messages.warning(request, msg)
        return redirect('donations:list')

    ok = donation.complete()

    if is_ajax:
        return JsonResponse({'ok': ok, 'pk': pk})

    if ok:
        messages.success(request, f'Донат «{donation.nickname}» завершён.')
    return redirect('donations:list')


# ─────────────────────────────────────────────────────────────
# Donator profile
# ─────────────────────────────────────────────────────────────

@staff_member_required
def donator_detail(request, nickname):
    donator = get_object_or_404(Donator, nickname__iexact=nickname)
    history = (
        Donation.objects
        .filter(nickname__iexact=nickname)
        .prefetch_related('privilegion')
        .order_by('-date')
    )
    return render(request, 'donations/donator_detail.html', {
        'donator': donator,
        'history': history,
        'stats':   _stats(history),
        'tier':    donator.discount_tier,
        'tiers':   DiscountTier.objects.order_by('min_total'),
        'Status':  Donation.Status,
    })
