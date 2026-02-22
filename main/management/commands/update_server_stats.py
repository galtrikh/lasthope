"""
main/management/commands/update_server_stats.py

Логика работы:
- Каждый запуск: обновляем session.duration = connected_seconds от сервера
- total_playtime = сумма ЗАКРЫТЫХ сессий + текущая открытая сессия
- total_kills    = сумма kills_in_session всех ЗАКРЫТЫХ сессий + текущей
- Статистика пересчитывается при каждом запуске, не только при выходе
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from main.models import ServerPlayer, ServerPlayerSession, ServerStatSnapshot
from main.utils.source_query import SourceServerQuery
import logging
import hashlib

logger = logging.getLogger(__name__)

SERVER_HOST = '46.174.49.39'
SERVER_PORT  = 27228
MAX_SESSION_SECONDS = 24 * 3600  # 24 часа — защита от аномалий


class Command(BaseCommand):
    help = 'Обновляет статистику игроков и управляет сессиями CS:S'

    def add_arguments(self, parser):
        parser.add_argument('--verbose', action='store_true', help='Подробный вывод')
        parser.add_argument('--reset',   action='store_true', help='Сбросить всю статистику')

    def handle(self, *args, **options):
        verbose = options['verbose']

        if options.get('reset'):
            self._reset_stats(verbose)
            return

        query = SourceServerQuery(SERVER_HOST, SERVER_PORT, timeout=5.0)
        info  = query.get_info()

        # ── Сервер недоступен ──────────────────────────────────────────
        if not info:
            if verbose:
                self.stdout.write(self.style.WARNING('Сервер недоступен'))
            ServerStatSnapshot.objects.create(
                players_online=0, current_map='N/A', server_online=False
            )
            self._close_stale_sessions(active_steam_ids=[], verbose=verbose)
            return

        # ── Снимок состояния ───────────────────────────────────────────
        ServerStatSnapshot.objects.create(
            players_online=info.get('players', 0),
            current_map=info.get('map', 'unknown'),
            server_online=True
        )

        players_data   = query.get_players() or []
        active_ids     = []

        if verbose:
            self.stdout.write(f'Игроков на сервере: {len(players_data)}')

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

                self._process_player(steam_id, name, connected_seconds, current_score, verbose)

            # Закрываем сессии вышедших игроков
            self._close_stale_sessions(active_ids, verbose)

        # Пересчитываем total_playtime/total_kills для ВСЕХ активных игроков
        # (чтобы фронт видел актуальные данные не дожидаясь закрытия сессии)
        self._recalculate_all_active(active_ids, verbose)

        if verbose:
            self.stdout.write(self.style.SUCCESS('✓ Готово'))

    # ──────────────────────────────────────────────────────────────────
    # Обработка одного игрока
    # ──────────────────────────────────────────────────────────────────

    def _process_player(self, steam_id, name, connected_seconds, current_score, verbose):
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

        if created and verbose:
            self.stdout.write(self.style.SUCCESS(f'  + Новый игрок: {name}'))

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
            if verbose:
                self.stdout.write(f'  → Новая сессия для {name}')
        else:
            # Проверяем реконнект: если время вдруг сильно уменьшилось
            if connected_seconds < session.duration * 0.5 and session.duration > 60:
                # Игрок переподключился — закрываем старую сессию
                if verbose:
                    self.stdout.write(
                        self.style.WARNING(f'  ↻ Реконнект {name}: {session.duration}s→{connected_seconds}s')
                    )
                self._close_session(session, player)

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

    def _recalculate_all_active(self, active_steam_ids, verbose=False):
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

            if verbose:
                self.stdout.write(
                    f'  ✓ {player.nickname}: '
                    f'{round(total_time/3600, 2)}ч, '
                    f'{total_kills} kills'
                )

    # ──────────────────────────────────────────────────────────────────
    # Закрытие сессий
    # ──────────────────────────────────────────────────────────────────

    def _close_session(self, session, player):
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

    def _close_stale_sessions(self, active_steam_ids, verbose=False):
        """Закрывает сессии игроков, которых нет в текущем списке."""
        stale = (
            ServerPlayerSession.objects
            .filter(session_end__isnull=True)
            .exclude(player__steam_id__in=active_steam_ids)
            .select_related('player')
        )

        count = 0
        for session in stale:
            self._close_session(session, session.player)
            count += 1
            if verbose:
                self.stdout.write(
                    f'  ✗ Закрыта сессия: {session.player.nickname} '
                    f'({round(session.duration/60, 1)} мин)'
                )

        if count and verbose:
            self.stdout.write(self.style.WARNING(f'Закрыто сессий: {count}'))

    # ──────────────────────────────────────────────────────────────────
    # Сброс статистики
    # ──────────────────────────────────────────────────────────────────

    def _reset_stats(self, verbose=False):
        """Полный сброс накопленной статистики."""
        ServerPlayerSession.objects.filter(
            session_end__isnull=True
        ).update(session_end=timezone.now())

        ServerPlayer.objects.all().update(
            total_playtime=0,
            total_kills=0,
            total_deaths=0,
        )

        if verbose:
            self.stdout.write(self.style.SUCCESS('✓ Статистика сброшена'))
