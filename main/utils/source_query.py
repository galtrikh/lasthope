# main/utils/source_query.py
import a2s
from typing import Dict, List, Optional
import socket

class SourceServerQuery:
    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.address = (host, port)
        self.timeout = timeout
    
    def get_info(self) -> Optional[Dict]:
        try:
            info = a2s.info(self.address, timeout=self.timeout)
            return {
                'server_name': info.server_name,
                'map': info.map_name,
                'game': info.game,
                'players': info.player_count,
                'max_players': info.max_players,
                'bots': info.bot_count,
                'server_type': info.server_type,
                'platform': info.platform,
                'password_protected': info.password_protected,
                'vac_enabled': info.vac_enabled,
            }
        except Exception as e:
            print(f"Error getting server info: {e}")
            return None
    
    def get_players(self) -> Optional[List[Dict]]:
        try:
            players = a2s.players(self.address, timeout=self.timeout)
            return [{
                'name': player.name,
                'score': player.score,
                # ✅ duration оставляем в секундах как есть — НЕ делим на 60
                # player.duration уже в секундах (float) от a2s
                'duration': player.duration,
            } for player in players]
        except Exception as e:
            print(f"Error getting players: {e}")
            return None
    
    def get_rules(self) -> Optional[Dict]:
        try:
            rules = a2s.rules(self.address, timeout=self.timeout)
            return dict(rules)
        except Exception as e:
            print(f"Error getting rules: {e}")
            return None
    
    def is_online(self) -> bool:
        return self.get_info() is not None