# 11.11
import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest
from typing import Dict, List, Set, Optional
from enum import Enum
import asyncio
import random
import os
from roles import Role, RoleManager
from mafia_style import MafiaStyle  # ← относительный импорт
from night_controller import NightController
from AI.llama_integration import AIGameManager
style = MafiaStyle()
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY")

try:
    from Online.chat_manager import ChatManager
    from Online.chat_handlers import ChatHandlers
    from Online.chat_manager import ChatType

    print("✅ Онлайн модули импортированы успешно")
except ImportError as e:
    print(f"⚠️ Онлайн модули не найдены, используются заглушки: {e}")


    # Fallback классы
    class ChatManager:
        def __init__(self): pass

        def setup_game_chat(self, *args): pass
        def setup_mafia_chat(self, *args): pass
        def add_message(self, *args): return True
        def get_chat_history(self, *args): return []
        def can_player_chat_in_mafia(self, *args): return False
        def get_mafia_chat_members(self, *args): return set()
        def cleanup_game_chat(self, *args): pass
        def disable_mafia_chat(self, *args): pass

        def __init__(self):
            self._history = []  # список кортежей (username, text)

        def add_message(self, username: str, message: str, chat_type=None) -> bool:
            self._history.append((username, message))
            return True

        def get_chat_history(self, chat_id, chat_type=None):
            return self._history[-20:]


    class ChatHandlers:
        def __init__(self, chat_manager):
            self.chat_manager = chat_manager
            self.ai_manager = None

        def set_ai_manager(self, ai_manager):
            self.ai_manager = ai_manager

        async def handle_public_chat_message(self, *args): pass
        async def handle_mafia_chat_message(self, *args): pass
        async def show_mafia_chat_history(self, *args): pass


class HybridOnlineManager:
    """Упрощенный онлайн менеджер для замены отсутствующего"""

    def __init__(self):
        self.room_manager = RoomManager()
        self.matchmaking = Matchmaking()

    async def quick_play(self, *args, **kwargs):
        return "room_test"

    async def show_room_interface(self, *args, **kwargs):
        pass


class RoomManager:
    def __init__(self):
        self.rooms = {}

    def create_room(self, owner_id, username, max_players):
        room_id = str(random.randint(1000, 9999))
        self.rooms[room_id] = Room(room_id, owner_id, username, max_players)
        return room_id

    def join_room(self, room_id, user_id, username):
        if room_id in self.rooms:
            return self.rooms[room_id].add_player(user_id, username)
        return False

    def get_player_room(self, user_id):
        for room in self.rooms.values():
            if user_id in room.players:
                return room
        return None

    def leave_room(self, user_id):
        room = self.get_player_room(user_id)
        if room:
            room.remove_player(user_id)

    def get_public_rooms(self):
        return [room for room in self.rooms.values() if not room.game_started]


class Room:
    def __init__(self, room_id, owner_id, owner_name, max_players):
        self.room_id = room_id
        self.owner_id = owner_id
        self.max_players = max_players
        self.players = {owner_id: {'username': owner_name, 'ready': False}}
        self.game_started = False
        self.ai_bot_count = 0

    def add_player(self, user_id, username):
        if len(self.players) < self.max_players and not self.game_started:
            self.players[user_id] = {'username': username, 'ready': False}
            return True
        return False

    def remove_player(self, user_id):
        if user_id in self.players:
            del self.players[user_id]

    def toggle_ready(self, user_id):
        if user_id in self.players:
            self.players[user_id]['ready'] = not self.players[user_id]['ready']
            return self.players[user_id]['ready']
        return False

    def is_owner(self, user_id):
        return user_id == self.owner_id

    def get_player_count(self):
        return len(self.players)

    # ДОБАВИТЬ ЭТИ ДВА МЕТОДА:
    def get_ready_count(self):
        """Количество готовых игроков (людей)"""
        return sum(1 for player in self.players.values() if player.get('ready', False))

    def get_total_ready_count(self):
        """Общее количество готовых (люди + боты считаются готовыми всегда)"""
        ready_humans = self.get_ready_count()
        bots = getattr(self, 'ai_bot_count', 0)
        # Боты считаются готовыми всегда, если они добавлены
        return ready_humans + bots


class Matchmaking:
    async def leave_queue(self, user_id):
        pass


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


class GameState(Enum):
    LOBBY   = "lobby"
    NIGHT   = "night"
    DAY     = "day"
    COURT   = "court"
    VOTING  = "voting"
    ENDED   = "ended"


class MafiaGame:
    def __init__(self):
        self.players: Dict[int, Dict] = {}
        self.evidence: List[Dict] = []
        self.suspicion: Dict[int, int] = {}
        self.state = GameState.LOBBY
        self.chat_id = None
        self.players_order: List[int] = []
        self.court_target: Optional[int] = None
        self.court_votes: Dict[int, str] = {}
        self.votes = {}
        self.night_actions: Dict[str, int] = {}
        self.day_number = 0
        self.role_manager = RoleManager()
        self.mafia_suggestions: Dict[int, int] = {}
        self.route_protected: Optional[int] = None
        self.route_alibi: Optional[int] = None          # ← новое
        self.journalist_targets: Set[int] = set()
        self.night_timer_task = None
        self.night_actions_done: set[str] = set()
        self.night_ctrl: Optional[NightController] = None   # будет жить тут

    def add_player(self, user_id: int, username: str):
        if user_id not in self.players:
            self.players[user_id] = {
                'username': username,
                'role': None,
                'alive': True,
                'votes_received': 0
            }
            return True
        return False

    def assign_roles(self):
        player_ids = list(self.players.keys())
        role_assignment = self.role_manager.assign_roles(player_ids)
        for player_id, role in role_assignment.items():
            self.players[player_id]['role'] = role

    def get_alive_players(self) -> List[int]:
        return self.role_manager.get_alive_players(self.players)

    def get_mafia_players(self) -> List[int]:
        return self.role_manager.get_mafia_players(self.players)

    def get_don_player(self) -> Optional[int]:
        return self.role_manager.get_don_player(self.players)

    def is_group_game(self) -> bool:
        return self.chat_id is not None and self.chat_id < 0

    def check_win_condition(self) -> str:
        return self.role_manager.check_win_condition(self.players)


    def reset_night_actions(self):
        self.night_actions = {}
        self.mafia_suggestions = {}
        self.route_protected = None
        self.journalist_targets = set()
        # ➜ добавить
        self.night_actions_done.clear()

    def cancel_night_timer(self):
        # Отменяет активный таймер ночи, если он запущен.
        if self.night_timer_task and not self.night_timer_task.done():
            self.night_timer_task.cancel()
            logging.info("Ночной таймер отменён.")

    async def resolve_night(self, context, chat_id: int, bot_instance):
        """Применяет все ночные действия и рассылает результаты."""
        killed = set()

        # 1. Мафия/Дон
        if self.night_actions.get('mafia_kill'):
            target = self.night_actions['mafia_kill']
            if self.night_actions.get('doctor_save') != target:
                self.players[target]['alive'] = False
                killed.add(target)

        # 2. Маньяк
        if self.night_actions.get('maniac_kill'):
            target = self.night_actions['maniac_kill']
            if self.night_actions.get('doctor_save') != target:
                self.players[target]['alive'] = False
                killed.add(target)

        # 3. Путана
        if self.night_actions.get('route_block'):
            target = self.night_actions['route_block']
            # просто даём алиби, убийство не происходит
            pass

        # 4. Журналист
        if self.night_actions.get('journalist_listen'):
            # можно добавить логику улик позже
            pass

        # 5. Шериф
        if self.night_actions.get('sheriff_result'):
            target_id, result = self.night_actions['sheriff_result']
            sheriff_id = next(p for p in self.players if self.players[p]['role'] == Role.SHERIFF)
            try:
                await context.bot.send_message(sheriff_id, f"🔍 Результат проверки: {result}")
            except:
                pass

        # 6. Рассылаем итоги
        if killed:
            names = [self.players[k]['username'] for k in killed]
            role_names = [self.players[k]['role'].value for k in killed]
            message = "🩸 Ночью были убиты:\n" + "\n".join(
                f"💀 {name} ({role})" for name, role in zip(names, role_names)
            )
        else:
            message = "🌙 Ночь прошла спокойно — никто не погиб."

        await self.broadcast(message, context, parse_mode='HTML')
        try:
            await context.bot.send_message(chat_id, message, parse_mode='HTML')
        except:
            pass

    async def broadcast(self, text: str, context, parse_mode=None, reply_markup=None,silent=False):
        """
        Универсальная рассылка:
        - всегда в личку всем игрокам
        - дополнительно в группу, если игра в группе
        - отладка: выводит отчёт в консоль
        """
        import logging

        report = ["📊 Отчёт рассылки:"]
        success_count = 0
        fail_count = 0

        # 1. Личные сообщения
        for pid in list(self.players.keys()):
            try:
                await context.bot.send_message(pid, text, parse_mode=parse_mode, reply_markup=reply_markup)
                report.append(f"✅ {self.players[pid]['username']} ({pid})")
                success_count += 1
            except Exception as e:
                report.append(f"❌ {self.players[pid]['username']} ({pid}) — {e}")
                fail_count += 1

        # 2. Групповое сообщение
        if self.is_group_game() and self.chat_id:
            try:
                await context.bot.send_message(self.chat_id, text, parse_mode=parse_mode)
                report.append(f"✅ Группа {self.chat_id}")
                success_count += 1
            except Exception as e:
                report.append(f"❌ Группа {self.chat_id} — {e}")
                fail_count += 1

        # 3. Отчёт в консоль
        if not silent:
            report.append(f"📈 Итого: {success_count} получили, {fail_count} не получили")
            logging.info("\n" + "\n".join(report))


class MafiaBot:
    def __init__(self, token: str, proxy_url: str = None): # Добавлен параметр proxy_url
        self.token = token
        request_kwargs = {
            'connect_timeout': 30.0,
            'read_timeout': 30.0,
            'write_timeout': 30.0,
            'pool_timeout': 30.0,
        }
        if proxy_url:
            request_kwargs['proxy'] = proxy_url
        request = HTTPXRequest(**request_kwargs)
        self.application = Application.builder().token(token).request(request).build()
        self.games: Dict[int, MafiaGame] = {}
        self.online_manager = HybridOnlineManager()
        self.evidence = []
        self.suspicion = {}
        try:
            from AI.ai_manager import AIManager as ExternalAIManager
            self.ai_manager = ExternalAIManager()
            print("✅ Внешний AI-менеджер загружен")
        except ImportError as e:
            print(f"⚠️ Внешний AI-менеджер не найден: {e}")
            print("⚠️ Используется встроенный AI-менеджер")
            self.ai_manager = AIGameManager()
        except Exception as e:
            print(f"⚠️ Ошибка загрузки AI-менеджера: {e}")
            self.ai_manager = AIGameManager()
        self.chat_manager = ChatManager()
        self.chat_handlers = ChatHandlers(self.chat_manager)
        self.chat_handlers.set_ai_manager(self.ai_manager)
        self.advanced_logic = None
        self.setup_handlers()
        self.night_actions_done: set[str] = set()

    async def safe_send(self, chat_id, text, context, **kw):
        try:
            await context.bot.send_message(chat_id, text, **kw)
        except Exception as e:
            logging.warning(f"safe_send: таймаут/ошибка {chat_id} – {e}")

    def _normalize_game_role(self, role_obj) -> str:
        try:
            name = getattr(role_obj, "name", "") or ""
            value = getattr(role_obj, "value", "") or ""
            name_l = str(name).lower()
            value_l = str(value).lower()
            ru_map = {
                "мафия": "mafia",
                "дон": "don",
                "доктор": "doctor",
                "шериф": "detective",
                "маньяк": "maniac",
                "путана": "whore",
                "журналист": "journalist",
                "мирный житель": "citizen",
            }
            if name_l in ("mafia", "don", "doctor", "sheriff", "detective", "maniac", "whore", "journalist", "civilian", "citizen"):
                if name_l == "sheriff":
                    return "detective"
                if name_l == "civilian":
                    return "citizen"
                return name_l
            if value_l in ru_map:
                return ru_map[value_l]
        except Exception:
            pass
        return "citizen"

    def _get_valid_targets(self, game: MafiaGame, player_id: int, role: Role, alive_players: List[int]) -> List[int]:
        """Возвращает список валидных целей для роли."""

        if role == Role.DOCTOR:
            return [p for p in alive_players if p != player_id]

        elif role == Role.SHERIFF:
            return [p for p in alive_players if p != player_id]

        elif role in (Role.MAFIA, Role.DON):
            # Мафия и Дон не могут убивать своих
            mafia_ids = {p for p in alive_players
                         if game.players[p]['role'] in (Role.MAFIA, Role.DON)}
            return [p for p in alive_players if p not in mafia_ids]

        elif role == Role.MANIAC:
            return [p for p in alive_players if p != player_id]

        elif role == Role.whore:
            return list(alive_players)

        elif role == Role.JOURNALIST:
            return [p for p in alive_players if p != player_id]

        else:
            return list(alive_players)

    def get_ai_discussion_message(self, player_id, game, message=None):
        role_key = self._normalize_game_role(game.players[player_id].get("role"))
        usernames = [p["username"] for p in game.players.values()]
        if message:
            replies = [
                f"Слышь, я тут подумал… {message}",
                "Это занятная мысль, но я бы добавил кое-что.",
                "Мне не нравится этот разговор, понял?",
                "Поддерживаю. Но давайте без глупостей.",
                "Спокойно, парни. Разберёмся.",
            ]
        else:
            if role_key in ("mafia", "don"):
                non_mafia_names = [p['username'] for p in game.players.values() if self._normalize_game_role(p['role']) not in ("mafia", "don")]
                target_name = random.choice(non_mafia_names) if non_mafia_names else (random.choice(usernames) if usernames else "кто-то")
                replies = [
                    "Держим ухо востро. Кто-то тут врёт.",
                    f"Мне не нравится, как ведёт себя {target_name}.",
                    "Поторопимся — и ошибёмся. Давайте думать.",
                ]
            elif role_key == "detective":
                replies = [
                    "Я кое-что проверил… и у меня появились вопросы.",
                    "Факты сходятся не у всех.",
                    "Кто-то очень старается казаться невиновным.",
                ]
            else:
                replies = [
                    "Что думаете по этому поводу?",
                    "У меня есть подозрения… но пока рано говорить.",
                    "По одному разбираем. Кто следующий?",
                ]
        return random.choice(replies)

    def get_ai_mafia_chat_message(self, player_id, game):
        role_key = self._normalize_game_role(game.players[player_id].get("role"))
        non_mafia = [p for p in game.players.values() if self._normalize_game_role(p['role']) not in ("mafia", "don")]
        target_name = random.choice(non_mafia)['username'] if non_mafia else "цель"
        lines = [
            "Кого берём сегодня?",
            "Делаем всё тихо. Без шума.",
            f"{target_name} выглядит опасно.",
        ]
        if role_key == "don":
            lines.extend([
                "Семья ждёт моего слова.",
                "Последнее слово за мной.",
                "Предлагайте варианты — я выберу.",
            ])
        return random.choice(lines)

    def setup_handlers(self):
        handlers = [
            CommandHandler("start", self.start),
            CommandHandler("help", self.help),
            CommandHandler("play", self.quick_play),
            CommandHandler("rule", self.rule),
            CommandHandler("createroom", self.create_room),
            CommandHandler("join", self.join_room),
            CommandHandler("rooms", self.list_rooms),
            CommandHandler("room", self.show_room),
            CommandHandler("ready", self.toggle_ready),
            CommandHandler("leave", self.leave_room),
            CommandHandler("startgame", self.start_game_command),
            CommandHandler("setupbots", self.setup_bots_command),
            CommandHandler("setbots", self.setup_bots_custom),
            CommandHandler("court", self._cmd_court),
            CommandHandler("vote", self.cmd_vote),
            CommandHandler("mchat", self.mafia_chat_command),
            CommandHandler("publish", self._cmd_publish),
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_chat_message),
            CallbackQueryHandler(self.button_handler)
        ]
        for h in handlers:
            self.application.add_handler(h)

    # ---------- ночные клавиатуры (новые, без обращений к несуществующим полям) ----------
    def night_doctor_keyboard(self, alive: List[int], game: "MafiaGame") -> InlineKeyboardMarkup:
        doctor_id = next((p for p in alive if game.players[p]['role'] == Role.DOCTOR), None)
        kb = [[InlineKeyboardButton(game.players[p]['username'], callback_data=f"doctor_save_{p}")]
              for p in alive if p != doctor_id]
        return InlineKeyboardMarkup(kb)

    def night_sheriff_keyboard(self, alive: List[int], game: "MafiaGame") -> InlineKeyboardMarkup:
        sheriff_id = next((p for p in alive if game.players[p]['role'] == Role.SHERIFF), None)
        kb = [[InlineKeyboardButton(game.players[p]['username'], callback_data=f"sheriff_check_{p}")]
              for p in alive if p != sheriff_id]
        return InlineKeyboardMarkup(kb)

    def night_mafia_keyboard(self, alive: List[int], game: "MafiaGame") -> InlineKeyboardMarkup:
        mafia_ids = {p for p in alive if game.players[p]['role'] in (Role.MAFIA, Role.DON)}
        kb = [[InlineKeyboardButton(game.players[p]['username'], callback_data=f"mafia_kill_{p}")]
              for p in alive if p not in mafia_ids]
        return InlineKeyboardMarkup(kb)

    def night_maniac_keyboard(self, alive: List[int], game: "MafiaGame") -> InlineKeyboardMarkup:
        maniac_id = next((p for p in alive if game.players[p]['role'] == Role.MANIAC), None)
        kb = [[InlineKeyboardButton(game.players[p]['username'], callback_data=f"maniac_kill_{p}")]
              for p in alive if p != maniac_id]
        return InlineKeyboardMarkup(kb)

    def night_whore_keyboard(self, alive: List[int], game: "MafiaGame") -> InlineKeyboardMarkup:
        # путана может выбрать любого живого (включая себя)
        kb = [[InlineKeyboardButton(game.players[p]['username'], callback_data=f"route_block_{p}")]
              for p in alive]
        return InlineKeyboardMarkup(kb)

    def _add_ai_players(self, game, chat_id: int, count: int = None):
        ai_names = ["🤖Алиса", "🤖Борис", "🤖Виктор", "🤖Дарья", "🤖Егор",
                    "🤖Ольга", "🤖Артёмка", "🤖Граф Максимиалиан",
                    "🤖Олег", "🤖Стас", "🤖Богдан", "🤖Евгений",
                    "🤖Аркаша", "🤖Димид", "🤖Александр", "🤖Терентий",
                    "🤖Ибрагим", "🤖Мария", "🤖Аня"]

        # 🔥 ИСПРАВЛЕНИЕ: Ищем комнату до проверки count
        room = None
        for r in self.online_manager.room_manager.rooms.values():
            if any(player_id in game.players for player_id in r.players):
                room = r
                break

        if count is None:
            if room and hasattr(room, 'ai_bot_count'):
                count = room.ai_bot_count
            else:
                count = max(0, 7 - len(game.players))

        # Теперь room всегда определен (может быть None)
        max_players = room.max_players if room else 20
        max_bots = max_players - len(game.players)
        count = min(count, max_bots, len(ai_names))

        added_count = 0
        for name in ai_names[:count]:
            ai_id = -hash(f"ai_{name}_{chat_id}") % 1000000
            if game.add_player(ai_id, name):
                personality = random.choice(["aggressive", "cautious", "neutral", "deceptive"])
                self.ai_manager.enable_ai_for_player(ai_id, personality)
                logging.info(f"Добавлен AI игрок {name} с личностью {personality}")
                added_count += 1

        logging.info(f"Добавлено AI игроков: {added_count}")
        return added_count

    async def start_game_from_room(self, room, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        if room.get_player_count() < 1:
            await context.bot.send_message(chat_id, "❌ Нужно минимум 1 игрок для начала игры!")
            return

        game = MafiaGame()
        for player_id, player_data in room.players.items():
            game.add_player(player_id, player_data['username'])

        self.chat_manager.setup_game_chat(chat_id)

        ai_bot_count = getattr(room, 'ai_bot_count', 0)
        if ai_bot_count > 0:
            self._add_ai_players(game, chat_id, ai_bot_count)
        else:
            player_needed = max(0, 7 - len(room.players))
            if player_needed > 0:
                self._add_ai_players(game, chat_id, player_needed)

        total_players = len(game.players)
        if total_players < 4:
            await context.bot.send_message(chat_id, "❌ Для начала игры нужно минимум 4 игрока!")
            return
        elif total_players > room.max_players:
            await context.bot.send_message(chat_id, f"❌ Слишком много игроков! Максимум {room.max_players}.")
            return

        game.assign_roles()
        game.state = GameState.NIGHT
        game.day_number = 1

        self.games[chat_id] = game
        room.game_started = True

        # связываем advanced_logic с игрой
        from advanced_logic import NightControlleAdvancedGameLogic as AdvancedGameLogic
        self.advanced_logic = AdvancedGameLogic(game)
        game.advanced_logic = self.advanced_logic
        game.chat_id = chat_id
        self.chat_manager.setup_game_chat(chat_id)
        mafia_players = game.get_mafia_players()
        if mafia_players:
            self.chat_manager.setup_mafia_chat(chat_id, mafia_players)
        self.advanced_logic.chat_id = chat_id

        for player_id, player_data in game.players.items():
            try:
                if not self.ai_manager.is_ai_player(player_id):
                    role_description = game.role_manager.get_role_description(player_data['role'])
                    await context.bot.send_message(
                        player_id,
                        f"🎭 Ваша роль: {player_data['role'].value}\n\n{role_description}"
                    )
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение игроку {player_id}: {e}")

        player_names = [p['username'] for p in game.players.values()]
        human_players = len([p for p in game.players.keys() if not self.ai_manager.is_ai_player(p)])
        ai_players = len([p for p in game.players.keys() if self.ai_manager.is_ai_player(p)])
        # derive room stats safely
        current_players = len(room.players)
        current_bots = getattr(room, 'ai_bot_count', 0)
        room_limit = room.max_players
        total_players = min(current_players + current_bots, room_limit)

        await context.bot.send_message(
            chat_id,
            f"🎮 Игра начинается!\n"
            f"👥 Участники: {', '.join(player_names)}\n"
            f"🌙 Ночь 1 - специальные роли просыпаются!\n"
            f"🤖 Ботов в игре: {ai_players}\n"
            f"👤 Игроков: {human_players}\n"
            f"📊 Всего: {total_players}/{room.max_players} игроков"
        )

        await self.start_night(chat_id, context)

    async def quick_play(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name

        result = await self.online_manager.quick_play(user_id, username, update, context)

        if result.startswith("room_"):
            room_id = result.replace("room_", "")
            await self.online_manager.show_room_interface(update, context, room_id)
        else:
            await self.list_rooms(update, context)

    async def create_room(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("4 игрока", callback_data="create_4")],
            [InlineKeyboardButton("6 игроков", callback_data="create_6")],
            [InlineKeyboardButton("8 игроков", callback_data="create_8")],
            [InlineKeyboardButton("10 игроков", callback_data="create_10")],
            [InlineKeyboardButton("12 игроков", callback_data="create_12")],
            [InlineKeyboardButton("15 игроков", callback_data="create_15")],
            [InlineKeyboardButton("20 игроков", callback_data="create_20")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🏠 Создание комнаты\n\nВыберите количество игроков:",
            reply_markup=reply_markup
        )

    async def join_room(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.args:
            room_id = context.args[0]
            user_id = update.effective_user.id
            username = update.effective_user.username or update.effective_user.first_name

            if self.online_manager.room_manager.join_room(room_id, user_id, username):
                await update.message.reply_text(f"✅ Вы присоединились к комнате {room_id}")
                await self.show_room(update, context)
            else:
                await update.message.reply_text("❌ Не удалось присоединиться к комнате. Проверьте ID.")
        else:
            await self.list_rooms(update, context)

    async def list_rooms(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        public_rooms = self.online_manager.room_manager.get_public_rooms()

        if not public_rooms:
            await update.message.reply_text(
                "😔 Нет доступных комнат.\nСоздайте свою: /createroom\nИли найдите игру: /play"
            )
            return

        rooms_text = "🏠 Доступные комнаты:\n\n"
        keyboard = []

        for room in public_rooms[:8]:
            # Получаем количество ботов
            bot_count = getattr(room, 'ai_bot_count', 0)
            human_count = len(room.players)
            total_count = human_count + bot_count

            # Три статуса: зеленый | желтый | красный
            fill_percentage = total_count / room.max_players * 100

            if fill_percentage >= 100:
                status = "🔴"  # Полная комната
            elif fill_percentage >= 80:
                status = "🟡"  # Почти полная
            else:
                status = "🟢"  # Много мест

            # Формируем строку игроков с ботами
            if bot_count > 0:
                rooms_text += f"{status} Комната {room.room_id}: {total_count}/{room.max_players} ({human_count}👤+{bot_count}🤖)\n"
            else:
                rooms_text += f"{status} Комната {room.room_id}: {human_count}/{room.max_players}\n"

            # Кнопка с индикацией заполнения
            if total_count >= room.max_players:
                button_text = f"🔴 Комната {room.room_id} (ПОЛНАЯ)"
            elif bot_count > 0:
                button_text = f"Комната {room.room_id} ({total_count}/{room.max_players} игроков)"
            else:
                button_text = f"Комната {room.room_id} ({human_count}/{room.max_players})"

            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"join_{room.room_id}")])

        rooms_text += f"\nВсего комнат: {len(public_rooms)}"
        rooms_text += "\n\n🟢 Много мест | 🟡 Почти полная | 🔴 Полная"
        keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="refresh_rooms")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(rooms_text, reply_markup=reply_markup)

    async def refresh_rooms_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await self.list_rooms(update, context)

    async def show_room(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        room = self.online_manager.room_manager.get_player_room(user_id)

        if not room:
            await update.message.reply_text("Вы не в комнате.")
            return

        # Получаем данные
        current_players = len(room.players)
        current_bots = getattr(room, "ai_bot_count", 0)
        room_limit = getattr(room, 'max_players', 8)
        total = min(current_players + current_bots, room_limit)
        max_possible_bots = max(room_limit - current_players, 0)

        # Формируем список игроков (люди + боты)
        players_list = []
        for pid, data in room.players.items():
            status = "✅" if data['ready'] else "❌"
            players_list.append(f"{status} {data['username']}")

        # Добавляем ботов как игроков
        if current_bots > 0:
            bot_names = ["🤖Алиса", "🤖Борис", "🤖Виктор", "🤖Дарья", "🤖Егор", "🤖Ольга", "🤖Артёмка", "🤖Граф Максимиалиан",
                    "🤖Олег", "🤖Стас", "🤖Богдан", "🤖Евгений", "🤖Аркаша", "🤖Димид", "🤖Александр","🤖Терентий",
                    "🤖Ибрагим", "🤖Мария", "🤖Аня"][:current_bots]
            for name in bot_names:
                players_list.append(f"🤖 {name}")

        players_text = "\n".join(players_list)

        # Если используете mafia_style
        header = style.format_room_info(room.room_id, current_players, room_limit, current_bots, room.get_ready_count())

        text = (header +
                f"Игроки:\n{players_text}\n\n"
                f"Команды:\n"
                f"/ready - готовность\n"
                f"/setupbots - настроить ботов (до {max_possible_bots})\n"
                f"/startgame - начать игру\n"
                f"/leave - покинуть комнату")

        await update.message.reply_text(text)

    async def toggle_ready(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        room = self.online_manager.room_manager.get_player_room(user_id)

        if room:
            is_ready = room.toggle_ready(user_id)
            status = "готов" if is_ready else "не готов"
            await update.message.reply_text(f"Вы {status} к игре!")
            await self.show_room(update, context)
        else:
            await update.message.reply_text("❌ Вы не в комнате!")

    async def leave_room(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.online_manager.room_manager.leave_room(user_id)
        await self.online_manager.matchmaking.leave_queue(user_id)
        await update.message.reply_text("Вы покинули комнату и остановили поиск")

    async def setup_bots_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        room = self.online_manager.room_manager.get_player_room(user_id)

        if not room:
            await update.message.reply_text("❌ Вы не находитесь в комнате!")
            return

        if not room.is_owner(user_id):
            await update.message.reply_text("❌ Только создатель комнаты может настраивать ботов!")
            return

        if context.args and context.args[0].isdigit():
            bot_count = int(context.args[0])
            max_possible_bots = room.max_players - len(room.players)

            if bot_count < 0 or bot_count > room.max_players - 1:  # ⬅️ Исправлено
                await update.message.reply_text(f"❌ Количество ботов должно быть от 0 до {room.max_players - 1}!")
                return

            if bot_count > max_possible_bots:
                await update.message.reply_text(
                    f"❌ Нельзя добавить {bot_count} ботов! "
                    f"Максимум можно добавить {max_possible_bots} ботов "
                    f"(всего игроков не должно превышать {room.max_players}, сейчас {len(room.players)})."
                )
                return

            room.ai_bot_count = bot_count
            await update.message.reply_text(
                f"✅ Установлено количество ботов: {bot_count}\n\n"
                f"Всего игроков в игре будет: {len(room.players) + bot_count}/{room.max_players}\n\n"
                f"Теперь можно начать игру командой /startgame"
            )
        else:
            current_bots = getattr(room, 'ai_bot_count', 0)
            max_possible_bots = room.max_players - len(room.players)

            keyboard = [
                [InlineKeyboardButton("1 бот", callback_data="setbots_1"),
                 InlineKeyboardButton("2 бота", callback_data="setbots_2"),
                 InlineKeyboardButton("4 бота", callback_data="setbots_4")],
                [InlineKeyboardButton("6 ботов", callback_data="setbots_6"),
                 InlineKeyboardButton("8 ботов", callback_data="setbots_8"),
                 InlineKeyboardButton("9 ботов", callback_data="setbots_9")],
            ]

            if max_possible_bots > 0:
                keyboard.append([InlineKeyboardButton(f"Макс. ({max_possible_bots} ботов)",callback_data=f"setbots_{max_possible_bots}")])

            keyboard.append([InlineKeyboardButton("📝 Ввести число вручную", callback_data="setbots_custom")])

            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"🤖 Настройка ботов\n\n"
                f"Текущее количество ботов: {current_bots}\n"
                f"Игроков в комнате: {len(room.players)}\n"
                f"Максимум можно добавить: {max_possible_bots} ботов\n"
                f"Всего игроков в игре будет: {len(room.players) + current_bots}/{room.max_players}\n\n"
                f"Выберите количество ботов для добавления в игру:",
                reply_markup=reply_markup
            )

    async def start_game_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        room = self.online_manager.room_manager.get_player_room(user_id)

        if not room:
            await update.message.reply_text("❌ Вы не находитесь в комнате!")
            return

        if not room.is_owner(user_id):
            await update.message.reply_text("❌ Только создатель комнаты может начать игру!")
            return

        await self.start_game_from_room(room, update.effective_chat.id, context)


    async def setup_bots_custom(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        room = self.online_manager.room_manager.get_player_room(user_id)

        if not room:
            await update.message.reply_text("❌ Вы не находитесь в комнате!")
            return

        if not room.is_owner(user_id):
            await update.message.reply_text("❌ Только создатель комнаты может настраивать ботов!")
            return

        if context.args and context.args[0].isdigit():
            bot_count = int(context.args[0])
            max_possible_bots = room.max_players - len(room.players)

            if bot_count < 0 or bot_count > 20:
                await update.message.reply_text("❌ Количество ботов должно быть от 0 до 19!")
                return

            if bot_count > max_possible_bots:
                await update.message.reply_text(
                    f"❌ Нельзя добавить {bot_count} ботов! "
                    f"Максимум можно добавить {max_possible_bots} ботов "
                    f"(всего игроков не должно превышать {room.max_players}, сейчас {len(room.players)})."
                )
                return

            room.ai_bot_count = bot_count
            await update.message.reply_text(
                f"✅ Установлено количество ботов: {bot_count}\n\n"
                f"Всего игроков в игре будет: {len(room.players) + bot_count}/{room.max_players}\n\n"
                f"Теперь можно начать игру командой /startgame"
            )
        else:
            await update.message.reply_text(
                "📝 Введите количество ботов (от 0 до 19):\n\n"
                f"Пример: /setupbots 5\n\n"
                f"Текущее количество игроков: {len(room.players)}\n"
                f"Максимум можно добавить: {20 - len(room.players)} ботов"
            )

    async def start_night(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        game = self.games[chat_id]
        game.reset_night_actions()

        game.night_ctrl = NightController(
            game, self.ai_manager,
            lambda: asyncio.create_task(self._night_finished(chat_id, context))
        )
        game.night_ctrl.start_night()

        mafia_players = game.get_mafia_players()
        if mafia_players:
            self.chat_manager.setup_mafia_chat(chat_id, mafia_players)

            for mafia_id in mafia_players:
                if not self.ai_manager.is_ai_player(mafia_id):
                    try:
                        await context.bot.send_message(
                            mafia_id,
                            "💬 *Чат мафии активирован!*\n\n"
                            "Теперь вы можете общаться с другими мафиями:\n"
                            "• Просто напишите сообщение в этот чат\n"
                            "• Его увидят все живые мафии\n"
                            "• /mchat - показать историю чата\n\n"
                            "Обсуждайте, кого убить этой ночью! 🗡️"
                        )
                    except Exception as e:
                        logging.error(f"Не удалось отправить уведомление мафии {mafia_id}: {e}")

        night_message = style.format_night_start(game.day_number)
        await game.broadcast(night_message, context, parse_mode='HTML')

        # Получи всех живых игроков
        alive_players = game.get_alive_players()

        # Доктор
        doctor_id = next((p for p in alive_players if game.players[p]['role'] == Role.DOCTOR), None)
        if doctor_id and not self.ai_manager.is_ai_player(doctor_id):
            kb = self.night_doctor_keyboard(alive_players, game)
            await context.bot.send_message(doctor_id, "🩺 Выберите, кого спасти:", reply_markup=kb)

        # Шериф
        sheriff_id = next((p for p in alive_players if game.players[p]['role'] == Role.SHERIFF), None)
        if sheriff_id and not self.ai_manager.is_ai_player(sheriff_id):
            kb = self.night_sheriff_keyboard(alive_players, game)
            await context.bot.send_message(sheriff_id, "🔍 Выберите, кого проверить:", reply_markup=kb)

        # Мафия и Дон
        mafia_players = game.get_mafia_players()
        don_id = game.get_don_player()

        # Отправляем обычным мафиози (не Дону)
        for mafia_id in mafia_players:
            if mafia_id == don_id:
                continue  # Дон пока пропускаем

            if not self.ai_manager.is_ai_player(mafia_id):
                kb = self.night_mafia_keyboard(alive_players, game)
                await context.bot.send_message(mafia_id, "🗡 Выберите, кого убить:", reply_markup=kb)

        # Отдельная логика для Дона
        if don_id and don_id in alive_players:
            if len(mafia_players) == 1:
                # Дон один - сразу отправляем ему выбор
                if not self.ai_manager.is_ai_player(don_id):
                    kb = self.night_mafia_keyboard(alive_players, game)
                    await context.bot.send_message(don_id, "🗡 Вы единственный мафиози. Выберите жертву:",
                                                   reply_markup=kb)
            else:
                # Дон не один - он ждёт предложений, но если мафиози мертвы, отправляем сразу
                alive_mafia_without_don = [p for p in mafia_players if p != don_id and p in alive_players]
                if not alive_mafia_without_don:
                    if not self.ai_manager.is_ai_player(don_id):
                        kb = self.night_mafia_keyboard(alive_players, game)
                        await context.bot.send_message(don_id, "🗡 Ваша мафия мертва. Выберите жертву самостоятельно:",
                                                       reply_markup=kb)

        # Маньяк
        maniac_id = next((p for p in alive_players if game.players[p]['role'] == Role.MANIAC), None)
        if maniac_id and not self.ai_manager.is_ai_player(maniac_id):
            kb = self.night_maniac_keyboard(alive_players, game)
            await context.bot.send_message(maniac_id, "🔪 Выберите, кого убить:", reply_markup=kb)

        # Путана
        whore_id = next((p for p in alive_players if game.players[p]['role'] == Role.whore), None)
        if whore_id and not self.ai_manager.is_ai_player(whore_id):
            kb = self.night_whore_keyboard(alive_players, game)
            await context.bot.send_message(whore_id, "💋 Выберите, кого блокировать:", reply_markup=kb)


        # Запускаем таймер ночи
        game.advanced_logic.night_completion_event.clear()
        game.night_timer_task = asyncio.create_task(
            self.night_timer_common(chat_id, context, game)
        )



        # Запускаем AI ночные действия
        for player_id in alive_players:
            if self.ai_manager.is_ai_player(player_id):
                await self.process_ai_night_action(chat_id, player_id, alive_players, context)

        # Запускаем чат мафии для AI
        if mafia_players:
            asyncio.create_task(self.mafia_night_chat(chat_id, context))

    async def mafia_night_chat(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        try:
            game = self.games[chat_id]
            if game.state != GameState.NIGHT:
                return

            mafia_players = [pid for pid in game.get_alive_players()
                             if game.players[pid]['role'] in [Role.MAFIA, Role.DON]
                             and self.ai_manager.is_ai_player(pid)]

            if not mafia_players:
                return

            await asyncio.sleep(3)

            while game.state == GameState.NIGHT and chat_id in self.games:
                ai_player_id = random.choice(mafia_players)
                ai_message = self.get_ai_mafia_chat_message(ai_player_id, game)

                if ai_message:
                    username = game.players[ai_player_id]['username']
                    full_text = f"💬 *{username} (мафия):* {ai_message}"

                    # ✅ Отправляем только мафиози в личку
                    for mafia_id in game.get_mafia_players():
                        if not self.ai_manager.is_ai_player(mafia_id):  # только реальным игрокам
                            try:
                                await context.bot.send_message(mafia_id, full_text, parse_mode="Markdown")
                            except Exception as e:
                                logging.warning(f"Не удалось отправить мафия-чат {mafia_id}: {e}")

                    # И сохраняем в историю чата
                    self.chat_manager.add_message(chat_id, ai_player_id, username, ai_message, ChatType.MAFIA)

                await asyncio.sleep(random.randint(7, 10))

        except Exception as e:
            logging.error(f"Ошибка в mafia_night_chat: {e}")

    async def night_timer_common(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, game: MafiaGame):
        try:
            # Ждем таймаута или события завершения
            await asyncio.wait_for(game.advanced_logic.night_completion_event.wait(), timeout=60.0)
            logging.info(f"night_actions_done = {game.night_actions_done}")  # ⬅️ Исправлено
            logging.info(f"Ночь {game.day_number} завершена досрочно (все сходили)")  # ⬅️ Исправлено
        except asyncio.TimeoutError:
            logging.info(f"Время ночи {game.day_number} истекло")  # ⬅️ Исправлено

        if chat_id in self.games and game.state == GameState.NIGHT:
            await self.start_day(chat_id, context)

    async def process_ai_night_action(self, chat_id: int, player_id: int, alive_players: List[int],
                                      context: ContextTypes.DEFAULT_TYPE) -> None:
        # AI выполняет ночное действие с валидацией целей.
        game = self.games[chat_id]
        player_data = game.players[player_id]
        role = player_data['role']

        action_map = {
            Role.DOCTOR: "doctor_heal",
            Role.SHERIFF: "sheriff_check",
            Role.DON: "don_kill",
            Role.MAFIA: "mafia_suggest",
            Role.MANIAC: "maniac_kill",
            Role.whore: "route_block",
            Role.JOURNALIST: "journalist_listen",
        }
        action_type = action_map.get(role)
        if not action_type:
            return

        # Получаем валидные цели
        valid_targets = self._get_valid_targets(game, player_id, role, alive_players)
        if not valid_targets:
            logging.info(f"AI {player_id} ({role.value}): нет валидных целей")
            return

        # AI выбирает цель
        try:
            raw = await self.ai_manager.generate_night_action(
                self._normalize_game_role(role),
                {
                    "players": [
                        {"username": p["username"], "role": p["role"], "alive": p["alive"]}
                        for p in game.players.values()
                    ],
                    "history": self.chat_manager.get_chat_history(chat_id, "mafia")[-3:],
                    "valid_targets": [game.players[t]["username"] for t in valid_targets],
                }
            )
        except Exception as e:
            logging.error(f"AI generate_night_action error: {e}")
            raw = ""

        target_name = raw.split("Цель:")[-1].strip() if "Цель:" in raw else None

        if not target_name or target_name == "никто":
            target_id = random.choice(valid_targets)
            logging.info(f"AI {player_id} выбрал случайную цель: {game.players[target_id]['username']}")
        else:
            target_id = next(
                (pid for pid, data in game.players.items() if data["username"] == target_name),
                None
            )

        if target_id is None:
            target_id = random.choice(valid_targets)

        # Финальная валидация
        if target_id not in valid_targets:
            logging.warning(f"AI {player_id} выбрал невалидную цель, исправляем")
            target_id = random.choice(valid_targets)

        await self.advanced_logic.handle_night_action(action_type, player_id, target_id, self, context)

    async def _send_don_direct_choice(self, chat_id: int, don_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        game = self.games[chat_id]
        alive = game.get_alive_players()
        kb = self.night_mafia_keyboard(alive, game)  # та же клавиатура, что и для мафии
        try:
            await context.bot.send_message(
                don_id,
                "⏰ Ваши люди молчат. Выберите цель самостоятельно:",
                reply_markup=kb
            )
        except Exception as e:
            logging.error(f"Не удалось отправить Дону прямой выбор {don_id}: {e}")

    async def _night_finished(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            game = self.games[chat_id]
            game.cancel_night_timer()

            await game.resolve_night(context, chat_id, self)

            # ← ПРОВЕРКА ПОБЕДЫ (используем твой end_game)
            winner = game.check_win_condition()
            if winner:
                await self.end_game(chat_id, winner, context)
                return  # Не начинаем день

            await self.start_day(chat_id, context)

        except Exception as e:
            logging.exception("_night_finished упал!")
            game.cancel_night_timer()

    async def start_day(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        game = self.games[chat_id]
        game.state = GameState.DAY
        game.day_number += 1

        alive = game.get_alive_players()
        day_text = style.format_day_start(game.day_number, len(alive))

        alive_players = game.get_alive_players()
        players_list = "\n".join([game.players[pid]['username'] for pid in alive_players])

        discussion_message = (
            f"🗣 Начинается дневное обсуждение!\n\n"
            f"Живые игроки ({len(alive_players)}):\n{players_list}\n\n"
            f"💬 Общайтесь в чате. Когда будете готовы - /vote"
        )

        # Отправляем день всем (и в группу, и в личку) - ЕДИНОЖДЫ
        await game.broadcast(day_text, context, parse_mode='HTML')
        await game.broadcast(discussion_message, context, parse_mode='HTML')

        # 🆕 ДОБАВЛЕНО: Запуск AI-дискуссий днем (были пропущены!)
        asyncio.create_task(self.ai_discussion_loop(chat_id, context))
        asyncio.create_task(self.delayed_ai_messages(chat_id, context))

    # --------------------------
    # Утренняя публикация улик
    # --------------------------
    async def _publish_morning_evidence(self, game: MafiaGame, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        published = game.publish_evidence()
        if not published:
            return

        lines = [f"🔎 Улика от {e['source']}: {game.players[e['target']]['username']} — {e['note']}"
                 for e in published]
        text = "📣 Утром появились улики:\n" + "\n".join(lines)

        # рассылаем всем
        await game.broadcast(text, context, parse_mode='HTML')
        # и в общий чат на всякий случай
        try:
            await context.bot.send_message(chat_id, text, parse_mode='HTML')
        except Exception:
            pass

        # увеличиваем подозрение
        for e in published:
            game.adjust_suspicion(e['target'], 2)
        game.clear_published_evidence()

    async def start_discussion(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        game = self.games[chat_id]

        # 1. Утренние улики
        try:
            published = game.publish_evidence()
            if published:
                evidence_text = "\n".join([
                    f"🔎 Улика от {e['source']}: {game.players.get(e['target'], {'username': 'Unknown'})['username']} — {e['note']}"
                    for e in published
                ])
                await game.broadcast(f"📣 Утром появились улики:\n{evidence_text}", context, parse_mode='HTML')
                for e in published:
                    t = e.get('target')
                    if t is not None:
                        game.adjust_suspicion(t, 2)
                game.clear_published_evidence()
        except Exception:
            pass

        # 2. Сообщение о начале дневного обсуждения
        alive_players = game.get_alive_players()
        players_list = "\n".join([game.players[pid]['username'] for pid in alive_players])

        discussion_message = (
            f"🗣 Начинается дневное обсуждение!\n\n"
            f"Живые игроки ({len(alive_players)}):\n{players_list}\n\n"
            f"💬 Теперь вы можете общаться в чате!\n"
            f"Просто пишите сообщения — они увидят все живые игроки.\n\n"
            f"🤖 AI-боты тоже будут участвовать в обсуждении!\n\n"
            f"Когда будете готовы голосовать, используйте /vote"
        )

        # 🔥 ВСЕГДА рассылаем в личку + в группу
        await game.broadcast(discussion_message, context, parse_mode='HTML')

        # 3. AI-реплики
        asyncio.create_task(self.delayed_ai_messages(chat_id, context))
        asyncio.create_task(self.ai_discussion_loop(chat_id, context))

    async def _cmd_court(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        game_chat_id = self._find_game_chat_id(update.effective_user.id)
        if not game_chat_id:
            await update.message.reply_text("❌ Вы не в активной игре!")
            return
        game = self.games.get(game_chat_id)
        if not game or game.state != GameState.DAY:
            await update.message.reply_text("❌ Суд можно вызвать только днём и в активной игре.")
            return
        alive = game.get_alive_players()
        if len(alive) <= 1:
            await update.message.reply_text("❌ Недостаточно игроков для суда.")
            return
        # убираем алиби путаны
        suspects = [pid for pid in alive if pid != game.route_alibi]
        if not suspects:
            await update.message.reply_text("💋 У всех живых алиби – суд не требуется.")
            return
        suspect = max(suspects, key=lambda pid: game.suspicion.get(pid, 0))
        await self.advanced_logic.start_court_logic(game, chat_id, context)

    async def start_court(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, suspect_id: int):
        await self.advanced_logic.run_court_session(self.games[chat_id], chat_id, context, suspect_id)

    async def send_ai_messages_to_chat(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        if chat_id not in self.games:
            return
        game = self.games[chat_id]
        if game.state != GameState.DAY:
            return

        alive_players = game.get_alive_players()
        ai_players = [pid for pid in alive_players if self.ai_manager.is_ai_player(pid)]
        if not ai_players:
            return

        ai_player_id = random.choice(ai_players)
        role_key = self._normalize_game_role(game.players[ai_player_id]['role'])

        history = self.chat_manager.get_chat_history(chat_id, "public")[-5:]
        ai_message = await self.ai_manager.ask(
            role=role_key,
            message="",
            game_state={
                "username": game.players[ai_player_id]['username'],
                "history": history
            }
        )

        if ai_message:
            username = game.players[ai_player_id]['username']
            full_text = f"💬 *{username}:* {ai_message}"

            # 🔥 ВСЕГДА в личку + в группу
            await game.broadcast(full_text, context, parse_mode="Markdown")

    async def ai_discussion_loop(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        try:
            while (chat_id in self.games and
                   self.games[chat_id].state == GameState.DAY):

                await asyncio.sleep(random.randint(7, 12))

                if (chat_id in self.games and
                        self.games[chat_id].state == GameState.DAY):
                    await self.send_ai_messages_to_chat(chat_id, context)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Ошибка в AI discussion loop: {e}")

    async def delayed_ai_messages(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        await asyncio.sleep(5)
        if chat_id in self.games and self.games[chat_id].state == GameState.DAY:
            for _ in range(random.randint(2, 3)):
                await self.send_ai_messages_to_chat(chat_id, context)
                await asyncio.sleep(3)

    async def start_court(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, suspect_id: int):
        game = self.games[chat_id]
        game.state = GameState.COURT
        game.court_target = suspect_id
        game.court_votes.clear()

        name = game.players[suspect_id]['username']

        # 1. Сообщение в чат
        await context.bot.send_message(
            chat_id,
            style.format_court_start() +
            f"\n\n👤 Обвиняемый: {name}\n"
            "⏳ 30 секунд на последнее слово…",
            parse_mode='HTML'
        )

        # 2. Даём слово обвиняемому (остальные молчат)
        await asyncio.sleep(30)

        # 3. Финальное голосование «За казнь / Против»
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚔️ За казнь", callback_data="court_kill")],
            [InlineKeyboardButton("🙅 Против", callback_data="court_spare")]
        ])
        alive = game.get_alive_players()
        for pid in alive:
            try:
                await context.bot.send_message(
                    pid,
                    "⚖️ Финальное голосование:\n"
                    f"Обвиняемый: {name}",
                    reply_markup=kb
                )
            except Exception as e:
                logging.error(f"Не удалось отправить кнопки суду {pid}: {e}")

        game.state = GameState.VOTING
        game.votes = {}

        voting_text = "🗳 Начинается голосование!\n\n"

        if game.route_alibi is not None:
            name = game.players[game.route_alibi]['username']
            await context.bot.send_message(
                chat_id,
                f"💋 {name} провёл ночь с путаной — у него **алиби**, он не может быть обвинён."
            )

        for player_id in alive:
            if not self.ai_manager.is_ai_player(player_id):
                await self.send_voting_buttons(player_id, alive_players, game, context)
            else:
                await self.process_ai_vote(player_id, alive_players, game, context)

    async def end_game(self, chat_id: int, winner: str, context: ContextTypes.DEFAULT_TYPE):
        game = self.games[chat_id]

        self.chat_manager.cleanup_game_chat(chat_id)
        game.cancel_night_timer()
        game.state = GameState.ENDED

        players_info = []
        for player_id, player_data in game.players.items():
            role = player_data['role'].value
            status = "жив" if player_data['alive'] else "мёртв"
            players_info.append(f"{player_data['username']} - {role} ({status})")

        players_list = "\n".join(players_info)

        end_message = (
            f"🎮 Игра окончена!\n\n"
            f"🏆 Победили: {winner}!\n\n"
            f"📊 Результаты:\n{players_list}\n\n"
            f"Спасибо за игру! 🎉"
        )

        await game.broadcast(end_message, context, parse_mode='HTML')

        if chat_id in self.games:
            del self.games[chat_id]

    async def handle_chat_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
        message_text = update.message.text
        chat_id = update.effective_chat.id

        game = None
        game_chat_id = None
        for current_chat_id, current_game in self.games.items():
            if user_id in current_game.players:
                game = current_game
                game_chat_id = current_chat_id
                break

        if not game:
            return

        # Проверка: мертвые не могут писать
        if user_id not in game.players or not game.players[user_id]['alive']:
            await update.message.reply_text("❌ Мёртвые игроки не могут говорить!")
            return

        if game.state == GameState.NIGHT:
            # Ночной чат только для мафии
            if (game.players[user_id]['role'] in [Role.MAFIA, Role.DON] and
                    self.chat_manager.can_player_chat_in_mafia(game_chat_id, user_id)):

                mafia_players = game.get_mafia_players()
                if user_id not in mafia_players:
                    await update.message.reply_text("❌ Вы не можете писать в мафия-чат!")
                    return

                # Рассылаем всей мафии (включая мертвых мафиози, если они есть)
                full_text = f"🌙 Мафия | {username}: {message_text}"
                for mafia_id in mafia_players:
                    try:
                        await context.bot.send_message(mafia_id, full_text)
                    except:
                        pass

                # Подтверждение отправителю
                await update.message.set_reaction("👍")

                if self.ai_manager.is_ai_player(user_id):
                    self.chat_manager.add_message(game_chat_id, user_id, username, message_text, ChatType.MAFIA)
            else:
                await update.message.reply_text("❌ Ночью общаться можно только в чате мафии!")

        elif game.state == GameState.DAY:
            # ДНЕВНОЙ ЧАТ - рассылаем ВСЕМ игрокам (включая мёртвых!)
            full_message = f"💬 {username}: {message_text}"

            # Рассылка всем
            for player_id in game.players:
                try:
                    await context.bot.send_message(player_id, full_message)
                except Exception as e:
                    logging.debug(f"Не удалось отправить сообщение {player_id}: {e}")

            # Сохраняем в историю
            self.chat_manager.add_message(game_chat_id, user_id, username, message_text, ChatType.PUBLIC)

            # Подтверждение доставки (реакция)
            try:
                await update.message.set_reaction("👍")
            except:
                pass

        elif game.state in (GameState.VOTING, GameState.COURT):
            await update.message.reply_text("❌ Во время голосования общение запрещено!")
            return
        else:
            await update.message.reply_text("❌ Сейчас не время для обсуждения!")


    async def mafia_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        game_chat_id = self._find_game_chat_id(update.effective_user.id)
        if game_chat_id:
            await self.chat_handlers.show_mafia_chat_history(update, context, game_chat_id)
        else:
            await update.message.reply_text("❌ Вы не в активной игре!")

    def _find_game_chat_id(self, user_id: int) -> Optional[int]:
        for chat_id, game in self.games.items():
            if user_id in game.players:
                return chat_id
        return None

    async def generate_ai_responses_with_delay(self, game: MafiaGame, chat_id: int,sender_id: int, message: str,context: ContextTypes.DEFAULT_TYPE):
        await asyncio.sleep(random.uniform(2, 5))

        alive_players = game.get_alive_players()
        ai_players = [pid for pid in alive_players
                      if self.ai_manager.is_ai_player(pid) and pid != sender_id]

        random.shuffle(ai_players)

        for ai_player_id in ai_players[:2]:
            if random.random() < 0.6:
                ai_response = self.get_ai_discussion_message(
                    ai_player_id, game, message
                )
                if ai_response:
                    username = game.players[ai_player_id]['username']
                    await asyncio.sleep(random.uniform(1, 3))

                    await context.bot.send_message(
                        chat_id,
                        f"💬 *{username}:* {ai_response}"
                    )

    #========================Кнопки========================
    # --------------------------------------------------
    # 1. Доктор
    # --------------------------------------------------
    def night_doctor_keyboard(self, alive: List[int], game: "MafiaGame") -> InlineKeyboardMarkup:
        doctor_id = next(
            (pid for pid, data in game.players.items()
             if data.get('role') == Role.DOCTOR and data.get('alive')),
            None
        )
        kb = [[InlineKeyboardButton(game.players[p]['username'], callback_data=f"doctor_save_{p}")]
              for p in alive if p != doctor_id]
        return InlineKeyboardMarkup(kb)

    # --------------------------------------------------
    # 2. Шериф
    # --------------------------------------------------
    def night_sheriff_keyboard(self, alive: List[int], game: "MafiaGame") -> InlineKeyboardMarkup:
        sheriff_id = next(
            (pid for pid, data in game.players.items()
             if data.get('role') == Role.SHERIFF and data.get('alive')),
            None
        )
        kb = [[InlineKeyboardButton(game.players[p]['username'], callback_data=f"sheriff_check_{p}")]
              for p in alive if p != sheriff_id]
        return InlineKeyboardMarkup(kb)

    # --------------------------------------------------
    # 3. Мафия / Дон  (одна клавиатура)
    # --------------------------------------------------
    def night_mafia_keyboard(self, alive: List[int], game: "MafiaGame") -> InlineKeyboardMarkup:
        mafia_ids = {pid for pid, data in game.players.items()
                     if data.get('role') in (Role.MAFIA, Role.DON) and data.get('alive')}
        non_mafia = [p for p in alive if p not in mafia_ids]
        kb = [[InlineKeyboardButton(game.players[p]['username'], callback_data=f"mafia_kill_{p}")]
              for p in non_mafia]
        return InlineKeyboardMarkup(kb)

    # --------------------------------------------------
    # 4. Маньяк
    # --------------------------------------------------
    def night_maniac_keyboard(self, alive: List[int], game: "MafiaGame") -> InlineKeyboardMarkup:
        maniac_id = next(
            (pid for pid, data in game.players.items()
             if data.get('role') == Role.MANIAC and data.get('alive')),
            None
        )
        kb = [[InlineKeyboardButton(game.players[p]['username'], callback_data=f"maniac_kill_{p}")]
              for p in alive if p != maniac_id]
        return InlineKeyboardMarkup(kb)

    # --------------------------------------------------
    # 5. Путана
    # --------------------------------------------------
    def night_whore_keyboard(self, alive: List[int], game: "MafiaGame") -> InlineKeyboardMarkup:
        # путана может выбрать любого живого (включая себя)
        kb = [[InlineKeyboardButton(game.players[p]['username'], callback_data=f"route_block_{p}")]
              for p in alive]
        return InlineKeyboardMarkup(kb)

    # --------------------------------------------------
    # ❶ ОТКРЫТОЕ ГОЛОСОВАНИЕ (с путаной и стилем)
    # --------------------------------------------------
    def public_vote_keyboard(self, alive: List[int], game: MafiaGame, voter_id: int) -> InlineKeyboardMarkup:
        """Кнопки: все живые, кроме себя и алиби-путаны"""
        kb = []
        for pid in alive:
            if pid == game.route_alibi or pid == voter_id:  # ⬅️ Добавлено: исключаем voter_id
                continue
            name = game.players[pid]['username']
            kb.append([InlineKeyboardButton(f"🗡 {name}", callback_data=f"pvote_{pid}")])
        kb.append([InlineKeyboardButton("❗ Воздержаться", callback_data="pvote_abstain")])
        return InlineKeyboardMarkup(kb)

    async def send_public_vote_message(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, game: MafiaGame):
        """Отправляет публичное сообщение о начале голосования в групповой чат"""
        alive_count = len(game.get_alive_players())
        message = (
            f"🗳 <b>Начинается открытое голосование!</b>\n\n"
            f"📅 День {game.day_number} | 👥 Живых игроков: {alive_count}\n"
            f"💌 Проверьте <b>личные сообщения</b> от бота, чтобы проголосовать.\n\n"
            f"⏳ У вас есть время, чтобы обсудить перед голосованием."
        )
        await context.bot.send_message(chat_id, message, parse_mode='HTML')

    async def send_private_public_vote(self, game: MafiaGame, context: ContextTypes.DEFAULT_TYPE):
        alive = [p for p in game.get_alive_players() if p != game.route_alibi]
        # Отправляем каждому игроку клавиатуру без него самого
        for pid in alive:
            kb = self.public_vote_keyboard(alive, game, pid)  # ⬅️ Передаем pid
            try:
                await context.bot.send_message(
                    pid,
                    "⚖️ Проголосуй открыто:\nКого отправить на плаху?",
                    reply_markup=kb
                )
            except Exception as e:
                logging.warning(f"skip {pid}: {e}")

        for pid in alive:
            if self.ai_manager.is_ai_player(pid):
                await self.process_ai_vote(pid, alive, game, context)


    async def handle_public_vote_callback(self, game: MafiaGame, user_id: int,data: str, context: ContextTypes.DEFAULT_TYPE, query):
        if data == "pvote_abstain":
            game.votes[user_id] = None
            await query.edit_message_text("✅ Вы воздержались")
        else:
            target_id = int(data.split('_')[1])
            game.votes[user_id] = target_id
            name = game.players[target_id]['username']
            await query.edit_message_text(f"✅ Вы проголосовали против {name}")

        # автоподсчёт при полном наборе
        alive_no_alibi = [p for p in game.get_alive_players() if p != game.route_alibi]
        if len(game.votes) == len(alive_no_alibi):
            await self.publish_public_result(game, context)

    async def cmd_vote(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        game_chat_id = self._find_game_chat_id(update.effective_user.id)
        if not game_chat_id:
            await update.message.reply_text("❌ Вы не в активной игре!")
            return
        game = self.games.get(game_chat_id)
        if not game or game.state != GameState.DAY:
            await update.message.reply_text("❌ Голосование можно вызвать только днём и в активной игре.")
            return

        alive_no_alibi = [p for p in game.get_alive_players() if p != game.route_alibi]
        if len(alive_no_alibi) < 2:
            await update.message.reply_text("❌ Недостаточно игроков для голосования.")
            return

        # запускаем новое открытое голосование
        await self.send_public_vote_message(game_chat_id, context, game)
        await self.send_private_public_vote(game, context)
        game.state = GameState.VOTING

    async def publish_public_result(self, game: MafiaGame, context: ContextTypes.DEFAULT_TYPE):
        counter: dict[int, int] = {}
        for v in game.votes.values():
            if v is not None:
                counter[v] = counter.get(v, 0) + 1

        max_v = max(counter.values()) if counter else 0
        leaders = [pid for pid, c in counter.items() if c == max_v]

        lines = [f"{game.players[pid]['username']} – {cnt} голос(а/ов)" for pid, cnt in
                 sorted(counter.items(), key=lambda x: -x[1])]
        table = "\n".join(lines) if lines else "Все воздержались"

        if not leaders:
            text = style.header("ИТОГИ ГОЛОСОВАНИЯ") + "\n🕯️ Никто не набрал голосов. Никто не казнён."
        elif len(leaders) == 1:
            pid = leaders[0]
            name = game.players[pid]['username']
            role = game.players[pid]["role"].value
            game.players[pid]["alive"] = False
            text = (
                    style.header("ИТОГИ ГОЛОСОВАНИЯ") +
                    f"\n💀 {name} ({role}) изгнан по открытому голосованию.\n"
                    f"Голосов: {max_v}\n\n"
                    f"📊 Результаты:\n{table}"
            )
        else:
            names = ", ".join(game.players[pid]["username"] for pid in leaders)
            text = (
                    style.header("НИЧЬЯ") +
                    f"\n{names} – по {max_v} голосов.\n"
                    "Никто не изгнан."
            )

        chat_id = next(cid for cid, g in self.games.items() if g is game)
        await game.broadcast(text, context, parse_mode='HTML')

        game.votes.clear()
        winner = game.check_win_condition()
        if winner:
            await self.end_game(chat_id, winner, context)
        else:
            game.state = GameState.NIGHT
            game.day_number += 1
            await self.start_night(chat_id, context)


    async def _cmd_publish(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        game_chat_id = self._find_game_chat_id(update.effective_user.id)
        if not game_chat_id:
            await update.message.reply_text("❌ Вы не в активной игре!")
            return
        game = self.games[game_chat_id]
        # allow only alive journalist
        pid = update.effective_user.id
        if pid not in game.players or not game.players[pid].get('alive', True):
            await update.message.reply_text("❌ Только живые игроки могут публиковать улики.")
            return
        role = game.players[pid].get('role')
        if getattr(role, 'value', '').lower() not in ('журналист', 'journalist'):
            await update.message.reply_text("❌ Только журналист может публиковать улики.")
            return
        published = game.publish_evidence()
        if not published:
            await update.message.reply_text("ℹ️ Улик пока нет.")
            return
        text_lines = ["📣 Журналист публикует улики:"]
        for e in published:
            t = e.get('target')
            tname = game.players.get(t, {}).get('username', 'Unknown')
            note = e.get('note', '')
            text_lines.append(f"- {note} (цель: {tname})")
        await context.bot.send_message(game_chat_id, "\n".join(text_lines))
        game.clear_published_evidence()


    def run(self):
        self.application.run_polling()

    async def handle_court_vote(self, game: MafiaGame, user_id: int, data: str,context: ContextTypes.DEFAULT_TYPE, query):
        vote = "kill" if data == "court_kill" else "spare"
        game.court_votes[user_id] = vote
        await query.edit_message_text(
            f"✅ Вы проголосовали «{'За казнь' if vote == 'kill' else 'Против'}»"
        )

        alive_no_alibi = [p for p in game.get_alive_players() if p != game.route_alibi]
        if len(game.court_votes) == len(alive_no_alibi):
            await self.finish_court(game, context.effective_chat.id, context)

    async def finish_court(self, game: MafiaGame, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        kill_cnt = sum(1 for v in game.court_votes.values() if v == "kill")
        alive_total = len([p for p in game.get_alive_players() if p != game.route_alibi])

        if kill_cnt >= alive_total * 2 / 3:
            target = game.court_target
            game.players[target]['alive'] = False
            name = game.players[target]['username']
            role = game.players[target]['role'].value
            text = style.format_vote_result(name) + f"\nРоль: {role}"
        else:
            text = "⚖️ Суд решил пощадить обвиняемого."

        await game.broadcast(text, context, parse_mode='HTML')

        game.state = GameState.NIGHT
        game.day_number += 1
        game.court_votes.clear()
        await self.start_night(chat_id, context)

    # -------------------  заглушка  -------------------
    async def process_ai_vote(self, ai_id: int, alive: List[int], game: MafiaGame, context: ContextTypes.DEFAULT_TYPE):
        """AI-бот автоматически голосует за случайного НЕ-союзника."""
        import random
        targets = [p for p in alive if p != ai_id and p != game.route_alibi]
        if not targets:
            game.votes[ai_id] = None  # воздержался
            return
        victim = random.choice(targets)
        game.votes[ai_id] = victim
        # если все проголосовали – сразу считаем результат
        if len(game.votes) == len(alive):
            await self.publish_public_result(game, context)

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        data = query.data

        logging.info(f"📍 CALLBACK: user={user_id}, data={data}")

        # ==== СОЗДАНИЕ КОМНАТЫ ====
        if data.startswith("create_"):
            max_players = int(data.split("_")[1])
            room_id = self.online_manager.room_manager.create_room(
                user_id,
                query.from_user.username or query.from_user.first_name,
                max_players
            )
            try:
                await query.edit_message_text(
                    f"✅ Комната создана!\nID: {room_id}\nИгроков: 1/{max_players}\n\nПриглашайте друзей: /join {room_id}"
                )
            except Exception as e:
                logging.error(f"❌ Ошибка при создании комнаты: {e}")
            return

        if data.startswith("join_"):
            room_id = data.split("_")[1]
            username = query.from_user.username or query.from_user.first_name
            if self.online_manager.room_manager.join_room(room_id, user_id, username):
                await query.edit_message_text(f"✅ Вы присоединились к комнате {room_id}")
            else:
                await query.edit_message_text("❌ Не удалось присоединиться к комнате")
            return

        if data.startswith("setbots_"):
            if data == "setbots_custom":
                await query.edit_message_text(
                    "📝 Введите количество ботов (от 0 до 19):\n\n"
                    "Пример: /setupbots 5\n\n"
                    "Или выберите из списка выше."
                )
                return

            bot_count = int(data.split("_")[1])
            room = self.online_manager.room_manager.get_player_room(user_id)
            if room and room.is_owner(user_id):
                max_possible_bots = 20 - len(room.players)

                if bot_count > max_possible_bots:
                    await query.answer(
                        f"❌ Нельзя добавить {bot_count} ботов! Максимум: {max_possible_bots}",
                        show_alert=True
                    )
                    return

                room.ai_bot_count = bot_count

                await query.edit_message_text(
                    f"✅ Установлено количество ботов: {bot_count}\n\n"
                    f"Всего игроков в игре будет: {len(room.players) + bot_count}/{room.max_players}\n\n"
                    f"Теперь можно начать игру командой /startgame\n\n"
                    f"Чтобы изменить количество, используйте /setupbots"
                )
            else:
                await query.answer("❌ Только создатель комнаты может настраивать ботов!", show_alert=True)
            return

        game = None
        chat_id = None
        for cid, g in self.games.items():
            if user_id in g.players:
                game, chat_id = g, cid
                break

        if not game or not game.players.get(user_id, {}).get('alive'):
            await query.answer("❌ Вы не в игре или мертвы", show_alert=True)
            return

        if data == "refresh_rooms":
            await self.refresh_rooms_callback(update, context)
            return

        # ========= НОЧНЫЕ ДЕЙСТВИЯ =========
        if data.startswith(("doctor_save_", "sheriff_check_", "mafia_kill_", "maniac_kill_", "route_block_", "don_final_")):
            await self.handle_night_action(game, user_id, data, context, query)
            return

        # ========= СУД =========
        if data in ("court_kill", "court_spare"):
            await self.handle_court_vote(game, user_id, data, context, query)
            return

        if data.startswith("pvote_"):
            await self.handle_public_vote_callback(game, user_id, data, context, query)
            return

        # ⬅️ Исправлено: Убран второй блок поиска игры (был дубль)

        if data.startswith("vote_"):
            if game.state != GameState.VOTING:
                await query.answer("❌ Сейчас не время голосования!", show_alert=True)
                return

            if data == "vote_abstain":
                game.votes[user_id] = None
                await query.edit_message_text("✅ Вы воздержались от голосования")
            else:
                target_id = int(data.split("_")[1])
                if (target_id not in game.get_alive_players() or
                        target_id == game.route_protected):
                    await query.answer("❌ Этот игрок не может быть выбран!", show_alert=True)
                    return

                game.votes[user_id] = target_id
                target_name = game.players[target_id]['username']
                await query.edit_message_text(f"✅ Вы проголосовали против {target_name}")

            alive_players = game.get_alive_players()
            if len(game.votes) == len(alive_players):
                await self.publish_public_result(game,context)  # ⬅️ Исправлено: было process_votes (метод не существует)

    async def handle_night_action(self, game: MafiaGame, user_id: int, data: str, context: ContextTypes.DEFAULT_TYPE,
                                  query) -> None:
        """Асинхронный хендлер ночных кнопок."""
        role = game.players[user_id]['role']
        alive = game.get_alive_players()

        # --- Добавить обработку don_final ---
        if data.startswith("don_final_"):
            target_id = int(data.split('_')[2])
            action_type = "don_kill"
        elif data.startswith("don_kill_"):
            target_id = int(data.split('_')[2])
            action_type = "don_kill"
        else:
            # Оригинальная логика парсинга для остальных
            target_id = int(data.split('_')[-1])
            if target_id not in alive:
                await query.answer("Цель мертва!", show_alert=True)
                return

            action_map = {
                "mafia_kill": "don_kill" if role == Role.DON else "mafia_suggest",
                "doctor_save": "doctor_heal",
                "sheriff_check": "sheriff_check",
                "maniac_kill": "maniac_kill",
                "route_block": "route_block"
            }
            action_type = action_map.get(data.split('_')[0] + '_' + data.split('_')[1])

        if not action_type:
            return

        # Остальной код без изменений...
        done = await self.advanced_logic.handle_night_action(
            action_type, user_id, target_id, self, context
        )
        target_name = game.players[target_id]['username']
        await query.edit_message_text(f"✅ Вы выбрали {target_name}")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            style.format_start(),
            parse_mode='HTML'
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            style.format_help(),
            parse_mode='HTML'
        )

    async def rule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает правила игры"""
        await update.message.reply_text(
            style.format_rule_text(),  # У вас уже есть этот метод в mafia_style.py
            parse_mode='HTML'
        )


if not hasattr(MafiaGame, 'add_evidence'):
    def _mg_add_evidence(self, source: str, target_id: int, note: str):
        if not hasattr(self, 'evidence'): self.evidence = []
        self.evidence.append({'source': source, 'target': target_id, 'note': note})
    MafiaGame.add_evidence = _mg_add_evidence
if not hasattr(MafiaGame, 'publish_evidence'):
    def _mg_publish_evidence(self): return list(getattr(self, 'evidence', []))
    MafiaGame.publish_evidence = _mg_publish_evidence
if not hasattr(MafiaGame, 'clear_published_evidence'):
    def _mg_clear_published(self): self.evidence = []
    MafiaGame.clear_published_evidence = _mg_clear_published
if not hasattr(MafiaGame, 'adjust_suspicion'):
    def _mg_adjust_suspicion(self, player_id: int, delta: int = 1):
        if not hasattr(self, 'suspicion'): self.suspicion = {}
        self.suspicion[player_id] = self.suspicion.get(player_id, 0) + delta
    MafiaGame.adjust_suspicion = _mg_adjust_suspicion
if not hasattr(MafiaGame, 'get_most_suspected'):
    def _mg_get_most_suspected(self, candidates: list):
        import random as _r
        if not candidates: return None
        scores = [(cid, getattr(self, 'suspicion', {}).get(cid, 0)) for cid in candidates]
        maxs = max(s[1] for s in scores) if scores else 0
        top = [cid for cid, sc in scores if sc == maxs] if scores else []
        return _r.choice(top) if top else None
    MafiaGame.get_most_suspected = _mg_get_most_suspected


if __name__ == "__main__":
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise ValueError("Пожалуйста, установите TELEGRAM_BOT_TOKEN в переменные окружения")
    bot = MafiaBot(BOT_TOKEN)
    bot.run()