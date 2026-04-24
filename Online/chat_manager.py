# Online/chat_manager.py
import logging
from typing import Dict, List, Set, Optional
from enum import Enum
import asyncio


class ChatType(Enum):
    PUBLIC = "public"
    MAFIA = "mafia"


class ChatMessage:
    def __init__(self, player_id: int, username: str, message: str, chat_type: ChatType):
        self.player_id = player_id
        self.username = username
        self.message = message
        self.chat_type = chat_type
        self.timestamp = asyncio.get_event_loop().time()


class ChatManager:
    def __init__(self):
        self.game_chats: Dict[int, Dict[ChatType, List[ChatMessage]]] = {}
        self.active_mafia_chats: Dict[int, Set[int]] = {}

    def setup_game_chat(self, game_chat_id: int):
        self.game_chats[game_chat_id] = {
            ChatType.PUBLIC: [],
            ChatType.MAFIA: []
        }

    def setup_mafia_chat(self, game_chat_id: int, mafia_players: List[int]):
        self.active_mafia_chats[game_chat_id] = set(mafia_players)

    def add_message(self, game_chat_id: int, player_id: int, username: str,
                    message: str, chat_type: ChatType) -> bool:
        if game_chat_id not in self.game_chats:
            return False

        chat_message = ChatMessage(player_id, username, message, chat_type)
        self.game_chats[game_chat_id][chat_type].append(chat_message)

        if len(self.game_chats[game_chat_id][chat_type]) > 100:
            self.game_chats[game_chat_id][chat_type] = self.game_chats[game_chat_id][chat_type][-100:]

        return True

    async def broadcast_to_players(self, bot, game, text, only_alive=True):
        recipients = []
        for uid, pdata in game.players.items():
            if only_alive and not pdata.get('alive', True):
                continue
            recipients.append(uid)

        async def _send(uid):
            try:
                await bot.send_message(uid, text, parse_mode='HTML')
            except Exception as e:
                logging.getLogger(__name__).error(f"broadcast to {uid}: {e}")

        await asyncio.gather(*[_send(u) for u in recipients], return_exceptions=True)
        return len(recipients)

    async def mafia_private_message(self, bot, mafia_chat_id, text):
        try:
            await bot.send_message(mafia_chat_id, text, parse_mode='HTML')
        except Exception:
            pass

    def get_chat_history(self, chat_id, chat_type, limit: int = 50) -> List[ChatMessage]:
        """Исправлено: game_chat_id -> chat_id, добавлен limit параметр"""
        if (chat_id not in self.game_chats or
                chat_type not in self.game_chats[chat_id]):
            return []

        messages = self.game_chats[chat_id][chat_type]
        return messages[-limit:] if len(messages) > limit else messages

    def can_player_chat_in_mafia(self, game_chat_id: int, player_id: int) -> bool:
        return (game_chat_id in self.active_mafia_chats and
                player_id in self.active_mafia_chats[game_chat_id])

    def get_mafia_chat_members(self, game_chat_id: int) -> Set[int]:
        return self.active_mafia_chats.get(game_chat_id, set())

    def cleanup_game_chat(self, game_chat_id: int):
        if game_chat_id in self.game_chats:
            del self.game_chats[game_chat_id]
        if game_chat_id in self.active_mafia_chats:
            del self.active_mafia_chats[game_chat_id]

    def disable_mafia_chat(self, game_chat_id: int):
        if game_chat_id in self.active_mafia_chats:
            del self.active_mafia_chats[game_chat_id]

    def get_chat_stats(self, game_chat_id: int) -> Dict[str, int]:
        if game_chat_id not in self.game_chats:
            return {}

        public_count = len(self.game_chats[game_chat_id].get(ChatType.PUBLIC, []))
        mafia_count = len(self.game_chats[game_chat_id].get(ChatType.MAFIA, []))
        mafia_members = len(self.active_mafia_chats.get(game_chat_id, set()))

        return {
            'public_messages': public_count,
            'mafia_messages': mafia_count,
            'mafia_members': mafia_members
        }