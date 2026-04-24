import logging
import uuid
import asyncio
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from enum import Enum
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class MatchmakingStatus(Enum):
    SEARCHING = "searching"
    FOUND = "found"
    CANCELLED = "cancelled"


class MatchmakingSystem:
    def __init__(self):
        self.searching_players: Dict[int, Dict] = {}
        self.waiting_queues: Dict[str, List[int]] = {
            "mafia_4": [], "mafia_6": [], "mafia_8": [], "mafia_10": [],
            "mafia_12": [], "mafia_15": [], "mafia_20": [],
        }
        self.player_callbacks: Dict[int, Callable] = {}

    async def join_queue(self, user_id: int, username: str, game_mode: str, callback: Callable):
        if user_id in self.searching_players:
            await callback("Вы уже в очереди поиска!")
            return

        player_data = {
            'user_id': user_id,
            'username': username,
            'game_mode': game_mode,
            'joined_at': datetime.now(),
            'status': MatchmakingStatus.SEARCHING
        }

        self.searching_players[user_id] = player_data
        self.waiting_queues[game_mode].append(user_id)
        self.player_callbacks[user_id] = callback

        queue_size = len(self.waiting_queues[game_mode])
        required_players = int(game_mode.split('_')[1])

        await callback(f"🔍 Поиск игры ({game_mode})...\nВ очереди: {queue_size}/{required_players} игроков")

        if queue_size >= required_players:
            await self._create_game(game_mode)

    async def leave_queue(self, user_id: int):
        if user_id in self.searching_players:
            game_mode = self.searching_players[user_id]['game_mode']
            if user_id in self.waiting_queues[game_mode]:
                self.waiting_queues[game_mode].remove(user_id)

            if user_id in self.player_callbacks:
                callback = self.player_callbacks[user_id]
                await callback("❌ Вы покинули очередь поиска")
                del self.player_callbacks[user_id]

            if user_id in self.searching_players:
                del self.searching_players[user_id]

    async def _create_game(self, game_mode: str):
        queue = self.waiting_queues[game_mode]
        required_players = int(game_mode.split('_')[1])

        if len(queue) >= required_players:
            players_to_start = queue[:required_players]

            # Создаем список имен перед удалением
            player_names = []
            for user_id in players_to_start:
                if user_id in self.searching_players:
                    player_data = self.searching_players[user_id]
                    player_names.append(player_data['username'])

            # Уведомляем всех игроков
            for user_id in players_to_start:
                if user_id in self.searching_players:
                    if user_id in self.player_callbacks:
                        callback = self.player_callbacks[user_id]
                        await callback(f"🎮 Игра найдена!\nУчастники: {', '.join(player_names)}\nНачинаем игру...")
                        del self.player_callbacks[user_id]
                    del self.searching_players[user_id]

            # Очищаем очередь
            for user_id in players_to_start:
                if user_id in queue:
                    queue.remove(user_id)

            logger.info(f"Создана игра {game_mode} с игроками: {player_names}")
            return players_to_start

    def get_searching_players_count(self) -> int:
        return sum(len(queue) for queue in self.waiting_queues.values())


class Room:
    def __init__(self, room_id: str, creator_id: int, creator_name: str, max_players: int = 8):
        self.room_id = room_id
        self.creator_id = creator_id
        self.max_players = max_players
        self.players: Dict[int, Dict] = {}
        self.created_at = datetime.now()
        self.is_public = True
        self.password = None
        self.game_started = False
        self.invited_players: set[int] = set()  # Приглашенные игроки
        self.ai_bot_count = 0  # Добавляем поле для ботов

        # Добавляем создателя в комнату
        self.add_player(creator_id, creator_name)

    def add_player(self, user_id: int, username: str) -> bool:
        if len(self.players) < self.max_players and user_id not in self.players:
            self.players[user_id] = {
                'username': username,
                'joined_at': datetime.now(),
                'ready': False
            }
            return True
        return False

    def remove_player(self, user_id: int):
        if user_id in self.players:
            del self.players[user_id]

    def toggle_ready(self, user_id: int) -> bool:
        if user_id in self.players:
            self.players[user_id]['ready'] = not self.players[user_id]['ready']
            return self.players[user_id]['ready']
        return False

    def all_players_ready(self) -> bool:
        if len(self.players) < 3:  # Уменьшил минимум до 3 игроков
            return False
        return all(player['ready'] for player in self.players.values())

    def get_player_count(self) -> int:
        return len(self.players)

    def get_ready_count(self) -> int:
        return sum(1 for player in self.players.values() if player['ready'])

    def add_invited_player(self, user_id: int):
        """Добавляет игрока в список приглашенных"""
        self.invited_players.add(user_id)

    def is_player_invited(self, user_id: int) -> bool:
        """Проверяет, приглашен ли игрок"""
        return user_id in self.invited_players

    def is_owner(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь создателем комнаты"""
        return user_id == self.creator_id


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self.player_rooms: Dict[int, str] = {}
        self.room_messages: Dict[str, int] = {}  # message_id для обновления интерфейса
        self._used_ids: set[str] = set()

    def create_room(self, creator_id: int, creator_name: str, max_players: int = 8, is_public: bool = True,password: str = None) -> str:
        while True:
            room_id = str(uuid.uuid4())[:8]
            if room_id not in self._used_ids:
                break
        self._used_ids.add(room_id)
        room = Room(room_id, creator_id, creator_name, max_players)
        room.is_public = is_public
        room.password = password

        self.rooms[room_id] = room
        self.player_rooms[creator_id] = room_id

        return room_id

    def join_room(self, room_id: str, user_id: int, username: str, password: str = None) -> bool:
        if room_id not in self.rooms:
            return False

        room = self.rooms[room_id]

        # Проверка пароля
        if room.password and room.password != password:
            return False

        # Проверка приглашения (если комната приватная)
        if not room.is_public and not room.is_player_invited(user_id):
            return False

        # Выходим из старой комнаты если есть
        if user_id in self.player_rooms:
            old_room_id = self.player_rooms[user_id]
            if old_room_id in self.rooms:
                self.rooms[old_room_id].remove_player(user_id)

        if room.add_player(user_id, username):
            self.player_rooms[user_id] = room_id
            return True

        return False

    def leave_room(self, user_id: int):
        if user_id in self.player_rooms:
            room_id = self.player_rooms[user_id]
            if room_id in self.rooms:
                room = self.rooms[room_id]
                room.remove_player(user_id)

                # Удаляем комнату если пустая
                if room.get_player_count() == 0:
                    del self.rooms[room_id]
                    if room_id in self.room_messages:
                        del self.room_messages[room_id]

            del self.player_rooms[user_id]

    def get_room(self, room_id: str) -> Optional[Room]:
        return self.rooms.get(room_id)

    def get_player_room(self, user_id: int) -> Optional[Room]:
        if user_id in self.player_rooms:
            return self.rooms.get(self.player_rooms[user_id])
        return None

    def get_public_rooms(self) -> List[Room]:
        return [room for room in self.rooms.values()
                if room.is_public and not room.game_started and room.get_player_count() < room.max_players]

    def invite_player_to_room(self, room_id: str, user_id: int) -> bool:
        """Приглашает игрока в комнату"""
        if room_id in self.rooms:
            room = self.rooms[room_id]
            room.add_invited_player(user_id)
            return True
        return False

    def set_room_message(self, room_id: str, message_id: int):
        """Сохраняет ID сообщения комнаты для обновления"""
        self.room_messages[room_id] = message_id

    def get_room_message(self, room_id: str) -> Optional[int]:
        """Возвращает ID сообщения комнаты"""
        return self.room_messages.get(room_id)


class HybridOnlineManager:
    def __init__(self):
        self.room_manager = RoomManager()
        self.matchmaking = MatchmakingSystem()

    async def quick_play(self, user_id: int, username: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Гибридный поиск игры - основная функция"""

        # 1. Проверяем матчмейкинг
        game_mode = "mafia_8"
        total_players = len(self.matchmaking.waiting_queues[game_mode])
        if total_players >= 1:
            await update.message.reply_text("🔍 Найдены другие игроки! Используем систему матчмейкинга...")
            await self._start_matchmaking(update, context, "mafia_8")
            return "matchmaking"

        # 2. Проверяем комнаты
        public_rooms = self.room_manager.get_public_rooms()
        suitable_rooms = [room for room in public_rooms if room.get_player_count() >= 1]

        if suitable_rooms:
            best_room = max(suitable_rooms, key=lambda r: len(r.players))
            if self.room_manager.join_room(best_room.room_id, user_id, username):
                await update.message.reply_text(f"🎯 Быстрое присоединение к комнате {best_room.room_id}!")
                await self.show_room_interface(update, context, best_room.room_id)
                return f"room_{best_room.room_id}"

        # 3. Создаем новую комнату
        room_id = self.room_manager.create_room(user_id, username, 8, True)
        await update.message.reply_text(
            f"🎉 Создана новая комната {room_id}!\n"
            f"Ожидаем игроков..."
        )
        await self.show_room_interface(update, context, room_id)
        return f"room_{room_id}"

    async def _start_matchmaking(self, update: Update, context: ContextTypes.DEFAULT_TYPE, game_mode: str):
        # Запускает поиск через матчмейкинг
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name

        async def callback(message):
            await update.message.reply_text(message)

        await self.matchmaking.join_queue(user_id, username, game_mode, callback)

    def get_online_stats(self) -> Dict[str, int]:
        """Возвращает статистику онлайн"""
        total_searching = self.matchmaking.get_searching_players_count()
        public_rooms = self.room_manager.get_public_rooms()
        total_in_rooms = sum(len(room.players) for room in public_rooms)

        return {
            "searching": total_searching,
            "in_rooms": total_in_rooms,
            "active_rooms": len(public_rooms)
        }

    async def show_room_interface(self, update: Update, context: ContextTypes.DEFAULT_TYPE, room_id: str):
        """Показывает интерфейс комнаты"""
        room = self.room_manager.get_room(room_id)
        if not room:
            await update.message.reply_text("❌ Комната не найдена!")
            return

        room_text = self._format_room_info(room)
        keyboard = self._create_room_keyboard(room, update.effective_user.id)

        reply_markup = InlineKeyboardMarkup(keyboard)

        if hasattr(update, 'message') and update.message:
            message = await update.message.reply_text(room_text, reply_markup=reply_markup)
        else:
            message = await update.callback_query.message.reply_text(room_text, reply_markup=reply_markup)

        self.room_manager.set_room_message(room_id, message.message_id)

    async def update_room_interface(self, context: ContextTypes.DEFAULT_TYPE, room_id: str, chat_id: int):
        """Обновляет интерфейс комнаты"""
        room = self.room_manager.get_room(room_id)
        if not room:
            return

        message_id = self.room_manager.get_room_message(room_id)
        if not message_id:
            return

        room_text = self._format_room_info(room)
        keyboard = self._create_room_keyboard(room, None)

        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=room_text,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка обновления интерфейса комнаты: {e}")

    def _format_room_info(self, room: Room) -> str:
        """Форматирует информацию о комнате"""
        room_text = f"🏠 Комната: {room.room_id}\n"
        room_text += f"👥 Игроков: {len(room.players)}/{room.max_players}\n"
        room_text += f"🤖 Ботов: {room.ai_bot_count}\n"
        room_text += f"✅ Готовы: {room.get_ready_count()}/{len(room.players)}\n\n"
        room_text += "Участники:\n"

        for player_id, player_data in room.players.items():
            status = "✅" if player_data['ready'] else "⏳"
            creator = " 👑" if player_id == room.creator_id else ""
            room_text += f"{status} {player_data['username']}{creator}\n"

        return room_text

    def _create_room_keyboard(self, room: Room, user_id: Optional[int] = None) -> List[List[InlineKeyboardButton]]:
        """Создает клавиатуру для комнаты"""
        keyboard = []

        # Кнопка готовности только для участников комнаты
        if user_id and user_id in room.players:
            keyboard.append(
                [InlineKeyboardButton("✅ Готов/Не готов", callback_data=f"room_toggle_ready_{room.room_id}")])

        # Кнопки управления
        manage_buttons = []
        manage_buttons.append(InlineKeyboardButton("📊 Пригласить", callback_data=f"room_invite_{room.room_id}"))
        manage_buttons.append(InlineKeyboardButton("🚪 Выйти", callback_data=f"room_leave_{room.room_id}"))
        keyboard.append(manage_buttons)

        # Кнопка начала игры только для создателя
        if user_id == room.creator_id and room.all_players_ready() and len(room.players) >= 3:
            keyboard.append([InlineKeyboardButton("🎮 НАЧАТЬ ИГРУ", callback_data=f"room_start_{room.room_id}")])

        return keyboard

    async def handle_room_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает callback от кнопок комнаты"""
        query = update.callback_query
        await query.answer()

        data = query.data
        user_id = query.from_user.id
        username = query.from_user.username or query.from_user.first_name
        chat_id = query.message.chat_id

        if data.startswith("room_toggle_ready_"):
            room_id = data.replace("room_toggle_ready_", "")
            await self._toggle_ready(user_id, room_id, context, chat_id)

        elif data.startswith("room_invite_"):
            room_id = data.replace("room_invite_", "")
            await self._invite_player(update, context, room_id)

        elif data.startswith("room_leave_"):
            room_id = data.replace("room_leave_", "")
            await self._leave_room(user_id, room_id, context, chat_id)

        elif data.startswith("room_start_"):
            room_id = data.replace("room_start_", "")
            await self._start_game(user_id, room_id, context, chat_id)

    async def _toggle_ready(self, user_id: int, room_id: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        """Переключает статус готовности"""
        room = self.room_manager.get_room(room_id)
        if room and user_id in room.players:
            is_ready = room.toggle_ready(user_id)
            status = "готов" if is_ready else "не готов"
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎯 {room.players[user_id]['username']} теперь {status}!"
            )
            await self.update_room_interface(context, room_id, chat_id)

    async def _invite_player(self, update: Update, context: ContextTypes.DEFAULT_TYPE, room_id: str):
        """Приглашает игрока в комнату"""
        room = self.room_manager.get_room(room_id)
        if not room:
            return

        # Создаем ссылку-приглашение
        invite_text = (
            f"🎮 Приглашение в игру!\n"
            f"Комната: {room_id}\n"
            f"Игроков: {len(room.players)}/{room.max_players}\n"
            f"Чтобы присоединиться, используйте команду:\n"
            f"/join {room_id}"
        )

        await update.callback_query.message.reply_text(invite_text)

    async def _leave_room(self, user_id: int, room_id: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        """Покидает комнату"""
        self.room_manager.leave_room(user_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text="🚪 Вы покинули комнату"
        )

    async def _start_game(self, user_id: int, room_id: str, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        """Начинает игру"""
        room = self.room_manager.get_room(room_id)
        if room and user_id == room.creator_id and room.all_players_ready() and len(room.players) >= 3:
            room.game_started = True
            await context.bot.send_message(
                chat_id=chat_id,
                text="🎮 Игра начинается! Подготовка к распределению ролей..."
            )
            return room
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Не все игроки готовы или недостаточно игроков (минимум 3)"
            )
            return None

    async def join_room_by_id(self, user_id: int, username: str, room_id: str, update: Update,context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Присоединяет игрока к комнате по ID"""
        success = self.room_manager.join_room(room_id, user_id, username)
        if success:
            room = self.room_manager.get_room(room_id)
            await update.message.reply_text(f"🎉 Вы присоединились к комнате {room_id}!")
            await self.show_room_interface(update, context, room_id)

            # Уведомляем других участников
            for player_id in room.players:
                if player_id != user_id:
                    try:
                        await context.bot.send_message(
                            chat_id=player_id,
                            text=f"🎯 {username} присоединился к комнате!"
                        )
                    except:
                        pass  # Игрок может заблокировать бота
            return True
        else:
            await update.message.reply_text(
                "❌ Не удалось присоединиться к комнате. Возможно, она заполнена или не существует.")
            return False

    def get_room_manager(self) -> RoomManager:
        return self.room_manager

    def get_matchmaking(self) -> MatchmakingSystem:
        return self.matchmaking