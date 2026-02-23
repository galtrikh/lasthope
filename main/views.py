from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods, require_GET
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum, Avg
from django.core.cache import cache
from django.utils import timezone
from django.db import transaction
import logging

from .models import (
    MainBanner, VoteBox, VoteBoxItem, VoteBoxVote,
    MainRules, HelpAccardion, ServerPlayer, ServerStatSnapshot
)
from .forms import VoteForm
from .utils.source_query import SourceServerQuery

from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from main.models import ServerPlayer, ServerPlayerSession, ServerStatSnapshot
from main.utils.source_query import SourceServerQuery
import logging
import hashlib

logger = logging.getLogger(__name__)

SERVER_HOST = '46.174.49.39'
SERVER_PORT = 27228
SERVER_QUERY_TIMEOUT = 3.0


# ──────────────────────────────────────────────
# Error handlers
# ──────────────────────────────────────────────

def e404(request):
    return render(request, '404.html', status=404)

def e403(request):
    return render(request, '403.html', status=403)

def e500(request):
    return render(request, '500.html', status=500)

def e502(request):
    return render(request, '502.html', status=502)

def e503(request):
    return render(request, '503.html', status=503)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _format_player_kills(player):
    """Словарь игрока для топа по убийствам."""
    return {
        'nickname':  player.nickname,
        'steam_id':  player.steam_id,
        'kills':     player.total_kills,
        'deaths':    player.total_deaths,
        'playtime':  player.playtime_hours,   # уже в часах (float)
        'escapes':   player.total_escapes,
        'kd_ratio':  player.kd_ratio,
        'is_online': player.is_online,
    }

def _format_player_time(player):
    """Словарь игрока для топа по времени."""
    return {
        'nickname':      player.nickname,
        'steam_id':      player.steam_id,
        'playtime':      player.playtime_hours,   # часы
        'playtime_raw':  player.total_playtime,   # секунды (для отладки)
        'kills':         player.total_kills,
        'escapes':       player.total_escapes,
        'is_online':     player.is_online,
    }

def _format_player_escapes(player):
    """Словарь игрока для топа по побегам."""
    return {
        'nickname':  player.nickname,
        'steam_id':  player.steam_id,
        'escapes':   player.total_escapes,
        'kills':     player.total_kills,
        'playtime':  player.playtime_hours,
        'is_online': player.is_online,
    }


# ──────────────────────────────────────────────
# Server Stats API
# ──────────────────────────────────────────────

@require_GET
def server_stats_api(request):
    cache_key = f'server_stats_{SERVER_HOST}_{SERVER_PORT}'
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    try:
        info = SourceServerQuery(SERVER_HOST, SERVER_PORT, timeout=SERVER_QUERY_TIMEOUT).get_info()

        if info:
            data = {
                'status':           'online',
                'server_name':      info.get('server_name', 'Unknown'),
                'map':              info.get('map', 'Unknown'),
                'players':          info.get('players', 0),
                'max_players':      info.get('max_players', 0),
                'bots':             info.get('bots', 0),
                'password_protected': info.get('password_protected', False),
                'vac_enabled':      info.get('vac_enabled', False),
            }
        else:
            data = {
                'status': 'offline', 'server_name': 'LastHope v34',
                'map': 'N/A', 'players': 0, 'max_players': 32, 'bots': 0,
            }

        cache.set(cache_key, data, 25)
        return JsonResponse(data)

    except Exception as e:
        logger.error(f"server_stats_api error: {e}")
        return JsonResponse(
            {'status': 'error', 'map': 'N/A', 'players': 0, 'max_players': 32},
            status=503
        )


@require_GET
def server_players_api(request):
    cache_key = f'server_players_{SERVER_HOST}_{SERVER_PORT}'
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    try:
        players = SourceServerQuery(SERVER_HOST, SERVER_PORT, timeout=SERVER_QUERY_TIMEOUT).get_players()

        if players is not None:
            sanitized = [
                {
                    'name':     str(p.get('name', 'Unknown'))[:64],
                    'score':    int(p.get('score', 0)),
                    'duration': float(p.get('duration', 0.0)),
                }
                for p in players[:32]
            ]
            data = {'status': 'success', 'count': len(sanitized), 'players': sanitized}
            cache.set(cache_key, data, 15)
            return JsonResponse(data)

        return JsonResponse(
            {'status': 'error', 'message': 'Server offline', 'count': 0, 'players': []},
            status=503
        )

    except Exception as e:
        logger.error(f"server_players_api error: {e}")
        return JsonResponse(
            {'status': 'error', 'message': 'Failed', 'count': 0, 'players': []},
            status=500
        )


@require_GET
def top_players_api(request):
    """API топа игроков. ?type=kills|time|escapes  &limit=10"""
    stat_type = request.GET.get('type', 'kills')
    try:
        limit = min(int(request.GET.get('limit', 10)), 50)
    except ValueError:
        limit = 10

    order_map = {
        'kills':   '-total_kills',
        'time':    '-total_playtime',
        'escapes': '-total_escapes',
    }
    order_by = order_map.get(stat_type, '-total_kills')

    try:
        qs = (
            ServerPlayer.objects
            .filter(is_banned=False)
            .order_by(order_by, '-last_seen')[:limit]
        )
        data = [
            {
                'rank':               i + 1,
                'nickname':           p.nickname,
                'steam_id':           p.steam_id,
                'kills':              p.total_kills,
                'deaths':             p.total_deaths,
                'playtime_hours':     p.playtime_hours,
                'escapes':            p.total_escapes,
                'kd_ratio':           p.kd_ratio,
                'headshot_percentage': p.headshot_percentage,
                'last_seen':          p.last_seen.isoformat(),
                'is_online':          p.is_online,
            }
            for i, p in enumerate(qs)
        ]
        return JsonResponse({'status': 'success', 'type': stat_type, 'count': len(data), 'players': data})

    except Exception as e:
        logger.error(f"top_players_api error: {e}")
        return JsonResponse({'status': 'error', 'message': 'Failed'}, status=500)


@require_GET
def server_full_info(request):
    cache_key = f'server_full_info_{SERVER_HOST}_{SERVER_PORT}'
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    try:
        q = SourceServerQuery(SERVER_HOST, SERVER_PORT, timeout=SERVER_QUERY_TIMEOUT)
        info    = q.get_info()
        players = q.get_players()
        data = {
            'online':    info is not None,
            'info':      info,
            'players':   players or [],
            'timestamp': timezone.now().isoformat(),
        }
        cache.set(cache_key, data, 20)
        return JsonResponse(data)

    except Exception as e:
        logger.error(f"server_full_info error: {e}")
        return JsonResponse({'online': False, 'info': None, 'players': []}, status=500)


# ──────────────────────────────────────────────
# Main index
# ──────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
def index(request):
    """Главная страница."""

    # ── POST: голосование ──────────────────────
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return JsonResponse({'status': 'error', 'message': 'Требуется авторизация'}, status=401)

        if not request.user.has_perm('main.can_vote'):
            return JsonResponse({'status': 'error', 'message': 'Нет прав для голосования'}, status=403)

        poll_id = request.POST.get('poll_id')
        if not poll_id or not poll_id.isdigit():
            return JsonResponse({'status': 'error', 'message': 'Некорректный ID опроса'}, status=400)

        poll = get_object_or_404(VoteBox, id=poll_id, closed=False)

        if not poll.active:
            return JsonResponse({'status': 'error', 'message': 'Голосование закрыто'}, status=400)

        if VoteBoxVote.objects.filter(box=poll, user=request.user).exists():
            return JsonResponse({'status': 'error', 'message': 'Вы уже проголосовали'}, status=400)

        form = VoteForm(request.POST, poll=poll)
        if not form.is_valid():
            return JsonResponse({'status': 'error', 'message': 'Некорректные данные формы'}, status=400)

        selected = form.cleaned_data['options']
        if not isinstance(selected, list):
            selected = [selected]

        try:
            with transaction.atomic():
                # Повторная проверка внутри транзакции (race condition)
                if VoteBoxVote.objects.filter(box=poll, user=request.user).exists():
                    return JsonResponse({'status': 'error', 'message': 'Вы уже проголосовали'}, status=400)

                votes = []
                for option_id in selected:
                    if not VoteBoxItem.objects.filter(id=option_id, box=poll).exists():
                        transaction.set_rollback(True)
                        return JsonResponse({'status': 'error', 'message': 'Некорректный вариант'}, status=400)
                    votes.append(VoteBoxVote(box=poll, user=request.user, item_id=option_id))

                VoteBoxVote.objects.bulk_create(votes)
                cache.delete(f'poll_{poll.id}_stats')

        except Exception as e:
            logger.error(f"Vote save error: {e}")
            return JsonResponse({'status': 'error', 'message': 'Ошибка сохранения голоса'}, status=500)

        return redirect('main')

    # ── GET: отображение страницы ──────────────

    try:
        # Баннер
        banner = cache.get_or_set('main_banner', lambda: MainBanner.objects.first(), 3600)

        # Активные опросы
        polls = (
            VoteBox.objects
            .filter(closed=False, active=True)
            .prefetch_related('vote_item')
            .order_by('-created_at')
        )

        # Правила
        rules = cache.get_or_set(
            'main_rules',
            lambda: list(MainRules.objects.order_by('id')),
            3600
        )

        # ── Топ по убийствам ───────────────────────────────────────────────
        raw_kills = cache.get_or_set(
            'top_players_kills',
            lambda: list(
                ServerPlayer.objects
                .filter(is_banned=False)
                .order_by('-total_kills', '-total_playtime')[:10]
            ),
            300
        )
        top_players_kills = [_format_player_kills(p) for p in raw_kills]

        # ── Топ по времени ─────────────────────────────────────────────────
        raw_time = cache.get_or_set(
            'top_players_time',
            lambda: list(
                ServerPlayer.objects
                .filter(is_banned=False)
                .order_by('-total_playtime', '-total_kills')[:10]
            ),
            300
        )
        top_players_time = [_format_player_time(p) for p in raw_time]

        # ── Топ по побегам ─────────────────────────────────────────────────
        raw_escapes = cache.get_or_set(
            'top_players_escapes',
            lambda: list(
                ServerPlayer.objects
                .filter(is_banned=False)
                .exclude(total_escapes=0)
                .order_by('-total_escapes', '-total_kills')[:10]
            ),
            300
        )
        top_players_escapes = [_format_player_escapes(p) for p in raw_escapes]

        # Топ-5 для главной карточки
        top_players = top_players_kills[:5]

        # Кол-во пользователей форума
        User = get_user_model()
        total_users = cache.get_or_set('total_users_count', lambda: User.objects.count(), 300)

        recent_posts = []  # TODO: заменить на реальные посты

    except Exception as e:
        logger.error(f"Index GET error: {e}")
        banner = None
        polls = VoteBox.objects.none()
        rules = []
        top_players = top_players_kills = top_players_time = top_players_escapes = []
        recent_posts = []
        total_users = 0

    # ── Формирование данных опросов ────────────
    poll_forms = []

    for poll in polls:
        try:
            cache_key = f'poll_{poll.id}_stats'
            poll_stats = cache.get(cache_key)

            if not poll_stats:
                total_votes = VoteBoxVote.objects.filter(box=poll).count()
                items = VoteBoxItem.objects.filter(box=poll).annotate(
                    votes=Count('vote_item_vote')
                )
                items_with_stats = []
                for item in items:
                    percent = round(item.votes * 100 / total_votes, 1) if total_votes > 0 else 0
                    items_with_stats.append({
                        'id':        item.id,
                        'is_winner': item.is_winner,
                        'text':      item.text,
                        'votes':     item.votes,
                        'percent':   int(percent),
                    })
                poll_stats = {'total_votes': total_votes, 'items': items_with_stats}
                cache.set(cache_key, poll_stats, 60)

            user_voted   = False
            selected_ids = []

            if request.user.is_authenticated:
                selected_ids = list(
                    VoteBoxVote.objects
                    .filter(box=poll, user=request.user)
                    .values_list('item_id', flat=True)
                )
                user_voted = bool(selected_ids)

            form = VoteForm(poll=poll, initial={'options': selected_ids})
            if not poll.active or user_voted:
                form.fields['options'].disabled = True

            poll_forms.append({
                'poll':        poll,
                'form':        form,
                'items':       poll_stats['items'],
                'total_votes': poll_stats['total_votes'],
                'can_vote': (
                    request.user.is_authenticated
                    and request.user.has_perm('main.can_vote')
                    and poll.active
                    and not user_voted
                ),
                'voted': user_voted,
            })

        except Exception as e:
            logger.error(f"Poll {poll.id} processing error: {e}")
            continue

    return render(request, 'main/index.html', {
        'polls':               poll_forms,
        'banner':              banner,
        'rules':               rules,
        'top_players':         top_players,          # топ-5 по убийствам (словари)
        'top_players_kills':   top_players_kills,    # топ-10 по убийствам (словари)
        'top_players_time':    top_players_time,     # топ-10 по времени (словари)
        'top_players_escapes': top_players_escapes,  # топ-10 по побегам (словари)
        'recent_posts':        recent_posts,
        'total_users':         total_users,
    })


# ──────────────────────────────────────────────
# Help page
# ──────────────────────────────────────────────

def help_page(request):
    return render(request, 'main/help.html', {'points': HelpAccardion.objects.all()})

def about_page(request):
    return render(request, 'main/about.html', {})

def contacts_page(request):
    return render(request, 'main/contacts.html', {})

def job_page(request):
    return render(request, 'main/job.html', {})
# ============================================
# Player stats
# ============================================

SERVER_HOST = '46.174.49.39'
SERVER_PORT  = 27228
MAX_SESSION_SECONDS = 24 * 3600

def server_players_api(request):

    query = SourceServerQuery(SERVER_HOST, SERVER_PORT, timeout=5.0)
    info  = query.get_info()

    # ── Сервер недоступен ──────────────────────────────────────────
    if not info:
        ServerStatSnapshot.objects.create(
            players_online=0, current_map='N/A', server_online=False
        )
        _close_stale_sessions(active_steam_ids=[])
        return JsonResponse({'status': 'err'})

    # ── Снимок состояния ───────────────────────────────────────────
    ServerStatSnapshot.objects.create(
        players_online=info.get('players', 0),
        current_map=info.get('map', 'unknown'),
        server_online=True
    )

    players_data   = query.get_players() or []
    active_ids     = []

    with transaction.atomic():
        for p_data in players_data:
            name = (p_data.get('name') or '').strip()
            if not name:
                continue

            # Стабильный ID на основе ника
            steam_id = 'g_' + hashlib.md5(name.encode('utf-8')).hexdigest()[:16]
            active_ids.append(steam_id)

            # duration от a2s — секунды подключения (float), НЕ делим на 60
            connected_seconds = min(
                float(p_data.get('duration', 0)),
                MAX_SESSION_SECONDS
            )
            current_score = max(int(p_data.get('score', 0)), 0)  # защита от отрицательных

            _process_player(steam_id, name, connected_seconds, current_score)

        # Закрываем сессии вышедших игроков
        _close_stale_sessions(active_ids)

    # Пересчитываем total_playtime/total_kills для ВСЕХ активных игроков
    # (чтобы фронт видел актуальные данные не дожидаясь закрытия сессии)
    _recalculate_all_active(active_ids)
    return JsonResponse({'status': 'ok'})

# ──────────────────────────────────────────────────────────────────
# Обработка одного игрока
# ──────────────────────────────────────────────────────────────────

def _process_player(steam_id, name, connected_seconds, current_score):
    """
    Создаёт/обновляет игрока и его текущую сессию.
    НЕ трогает total_playtime/total_kills напрямую — они пересчитываются
    в _recalculate_all_active после обхода всех игроков.
    """
    # Получаем или создаём игрока
    player, created = ServerPlayer.objects.get_or_create(
        steam_id=steam_id,
        defaults={'nickname': name[:64]}
    )

    if not created:
        # Обновляем ник и last_seen
        ServerPlayer.objects.filter(pk=player.pk).update(
            nickname=name[:64],
            last_seen=timezone.now()
        )
        player.refresh_from_db()

    # Ищем открытую сессию
    session = (
        ServerPlayerSession.objects
        .filter(player=player, session_end__isnull=True)
        .last()
    )

    if session is None:
        # Первый раз видим игрока в этом коннекте — создаём сессию
        ServerPlayerSession.objects.create(
            player=player,
            duration=int(connected_seconds),
            kills_in_session=current_score,
        )
    else:
        # Проверяем реконнект: если время вдруг сильно уменьшилось
        if connected_seconds < session.duration * 0.5 and session.duration > 60:
            # Игрок переподключился — закрываем старую сессию
            _close_session(session, player)

            # Открываем новую
            ServerPlayerSession.objects.create(
                player=player,
                duration=int(connected_seconds),
                kills_in_session=current_score,
            )
        else:
            # Обычное обновление
            # kills_in_session = текущий score (может только расти в рамках сессии)
            new_kills = current_score if current_score >= 0 else session.kills_in_session
            ServerPlayerSession.objects.filter(pk=session.pk).update(
                duration=int(connected_seconds),
                kills_in_session=new_kills,
            )

# ──────────────────────────────────────────────────────────────────
# Пересчёт итоговой статистики
# ──────────────────────────────────────────────────────────────────

def _recalculate_all_active(active_steam_ids):
    """
    Пересчитывает total_playtime и total_kills для всех игроков онлайн.

    Формула:
        total_playtime = Σ duration(закрытые сессии) + duration(открытая)
        total_kills    = Σ kills_in_session(закрытые) + kills_in_session(открытая)

    Это гарантирует корректные данные на фронте без ожидания выхода игрока.
    """
    players = ServerPlayer.objects.filter(steam_id__in=active_steam_ids)

    for player in players:
        # Сумма закрытых сессий
        closed = ServerPlayerSession.objects.filter(
            player=player,
            session_end__isnull=False
        ).aggregate(
            t=Sum('duration'),
            k=Sum('kills_in_session')
        )
        closed_time  = closed['t'] or 0
        closed_kills = closed['k'] or 0

        # Открытая сессия
        open_session = ServerPlayerSession.objects.filter(
            player=player,
            session_end__isnull=True
        ).last()

        open_time  = open_session.duration          if open_session else 0
        open_kills = open_session.kills_in_session  if open_session else 0

        total_time  = closed_time  + open_time
        total_kills = closed_kills + open_kills

        ServerPlayer.objects.filter(pk=player.pk).update(
            total_playtime=max(total_time,  0),
            total_kills=   max(total_kills, 0),
        )


# ──────────────────────────────────────────────────────────────────
# Закрытие сессий
# ──────────────────────────────────────────────────────────────────

def _close_session(session, player):
    """Закрывает одну сессию и пересчитывает итоговую статистику игрока."""
    session.session_end = timezone.now()
    session.save(update_fields=['session_end'])

    # Пересчитываем на основе всех закрытых сессий
    agg = ServerPlayerSession.objects.filter(
        player=player,
        session_end__isnull=False
    ).aggregate(t=Sum('duration'), k=Sum('kills_in_session'))

    ServerPlayer.objects.filter(pk=player.pk).update(
        total_playtime=max(agg['t'] or 0, 0),
        total_kills=   max(agg['k'] or 0, 0),
    )

def _close_stale_sessions(active_steam_ids):
    """Закрывает сессии игроков, которых нет в текущем списке."""
    stale = (
        ServerPlayerSession.objects
        .filter(session_end__isnull=True)
        .exclude(player__steam_id__in=active_steam_ids)
        .select_related('player')
    )

    count = 0
    for session in stale:
        _close_session(session, session.player)
        count += 1

# ──────────────────────────────────────────────────────────────────
# Сброс статистики
# ──────────────────────────────────────────────────────────────────

def _reset_stats():
    """Полный сброс накопленной статистики."""
    ServerPlayerSession.objects.filter(
        session_end__isnull=True
    ).update(session_end=timezone.now())

    ServerPlayer.objects.all().update(
        total_playtime=0,
        total_kills=0,
        total_deaths=0,
    )
