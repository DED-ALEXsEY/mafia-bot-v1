# mafia_style.py
class MafiaStyle:
    def escape(self, s: str) -> str:
        if s is None:
            return ""
        return (s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))

    def header(self, title: str) -> str:
        return f"🕯️ <b>{self.escape(title)}</b>"

    def format_system(self, text: str) -> str:
        return f"🗽 <b>Система:</b> {self.escape(text)}"

    # === ДИНАМИЧНЫЕ СИСТЕМНЫЕ СООБЩЕНИЯ ===

    def format_room_created(self, room_id: str, max_players: int) -> str:
        return (f"🕯️ <b>Комната {self.escape(str(room_id))}</b> создана.\n"
                f"Вместимость: {max_players} человек.\n"
                "Закройте двери — новые лица зашли на район.")

    def format_room_info(self, room_id: str, current_players: int, max_players: int,
                         bots: int, ready_count: int) -> str:
        """Динамичное отображение информации о комнате"""
        total = current_players + bots
        return (f"🏚 Комната {room_id}\n"
                f"👥 Игроков: {current_players}/{max_players}\n"
                f"🤖 Ботов: {bots}\n"
                f"📊 Всего будет: {total}/{max_players} игроков\n"
                f"✅ Готовы: {ready_count}/{total}\n\n")

    def format_game_start(self, day_number: int, players_count: int, max_players: int,
                          human_count: int, ai_count: int, player_names: List[str]) -> str:
        """Системное сообщение о начале игры"""
        names_str = ", ".join(player_names[:10])
        if len(player_names) > 10:
            names_str += f" и ещё {len(player_names) - 10}..."

        return (f"🎮 Игра начинается!\n"
                f"👥 Участники ({players_count}/{max_players}): {names_str}\n"
                f"🌙 Ночь {day_number} - специальные роли просыпаются!\n"
                f"🤖 Ботов в игре: {ai_count}\n"
                f"👤 Людей: {human_count}\n"
                f"📊 Всего: {players_count}/{max_players} игроков")

    def format_night_start(self, n: int, alive_count: int = None) -> str:
        msg = f"🌙 <b>Ночь {n}.</b>\nГород засыпает... Тени проснаются. Дела решаются тихо."
        if alive_count:
            msg += f"\n🕯️ Живых игроков: {alive_count}"
        return msg

    def format_day_start(self, n: int, alive_count: int = None) -> str:
        msg = (f"🌞 <b>День {n}.</b>\n"
               "Нью-Йорк просыпается, парень. Пора выяснить, кто вчера шумел.")
        if alive_count:
            msg += f"\n🕯️ Живых осталось: {alive_count}"
        return msg

    def format_vote_start(self, participants: int) -> str:
        return (f"⚖️ <b>Голосование началось.</b>\n"
                f"Участвуют: {participants} игроков.\n"
                "Выбирай мудро — в этом городе решения имеют последствия.")

    def format_vote_result(self, name: str, role: str = None) -> str:
        msg = (f"🚬 <b>{self.escape(name)}</b> покинул район.\n"
               "Пусть улицы запомнят это решение.")
        if role:
            msg += f"\n💀 Роль: {role}"
        return msg

    def format_court_start(self, suspect_name: str) -> str:
        return (f"⚖️ <b>Суд начался.</b>\n"
                f"👤 Обвиняемый: {self.escape(suspect_name)}\n"
                "⏳ 30 секунд на последнее слово…")

    def format_morning_deaths(self, killed: List[tuple]) -> str:
        """Форматирование утренних смертей"""
        if not killed:
            return "🌙 Ночь прошла спокойно — никто не погиб."

        lines = ["🩸 Ночью были убиты:"]
        for name, role in killed:
            lines.append(f"💀 {self.escape(name)} ({self.escape(role)})")
        return "\n".join(lines)

    def format_role_assignment(self, role_name: str, description: str) -> str:
        return f"🎭 Ваша роль: <b>{self.escape(role_name)}</b>\n\n{self.escape(description)}"

    def format_wait_for_players(self, current: int, max_p: int) -> str:
        return f"⏳ Ожидание игроков... {current}/{max_p}"

    # === ЧАТЫ ===

    def format_day_group(self, author: str, text: str) -> str:
        return (f"💬 <b>{self.escape(author)}</b>\n"
                f"{self.escape(text)}")

    def format_mafia_private(self, author: str, text: str) -> str:
        return (f"🔪 <b>{self.escape(author)} (мафия)</b>\n"
                f"{self.escape(text)}")

    def format_saved(self, name: str) -> str:
        return f"❤️ <b>{self.escape(name)}</b> спасён."

    def format_killed(self, name: str) -> str:
        return f"💀 <b>{self.escape(name)}</b> исчез навсегда."

    def format_evidence(self, source: str, target: str, note: str) -> str:
        return f"🔎 <b>Улика от {self.escape(source)}:</b> {self.escape(target)} — {self.escape(note)}"

    def format_rule_text(self) -> str:
        return (
            "Слушай, парень…\n\n"
            "В нашем деле ты либо говоришь с умом… либо вообще молчишь.\n"
            "Есть разговор приватный — и есть разговор перед всей семьёй.\n\n"
            "💬 ЛИЧНЫЙ ЧАТ — ГОВОРИШЬ МНЕ, СЛЫШИТ ВСЯ СЕМЬЯ\n"
            "Пишешь мне в личку?\n"
            "Считай, сообщение дошло.\n"
            "Ребята услышат. Вся семья услышит.\n\n"
            "🍷 СЕМЕЙНЫЙ СТОЛ — ОБЩИЙ ЧАТ\n"
            "Сказал что-то за столом?\n"
            "Оно остаётся за столом.\n\n"
            "🌙 КОГДА В ГОРОДЕ ГАСНУТ ОГНИ…\n"
            "Когда на Бруклин опускается ночь —\n"
            "все замолкают.\n"
            "Кроме парней в костюмах.\n\n"
            "💼 СЕМЕЙНЫЙ БИЗНЕС (ТОЛЬКО ДЛЯ МАФИИ)\n"
            "Если ты один из наших?\n"
            "Говоришь тихо. Только в приватном чате. Только среди своих.\n\n"
            "🗳️ ГОЛОСОВАНИЕ — КОГДА ПРИШЛО ВРЕМЯ РЕШАТЬ\n"
            "Я подам тебе знак в личке.\n"
            "Ты и сделаешь свой выбор.\n\n"
            "Запомни, парень…\n"
            "Умный держит язык за зубами.\n"
            "Дурак — нарывается на пулю."
        )

    def format_start(self) -> str:
        return (
            "🎮 Добро пожаловать в Мафию!\n\n"
            "Основные команды:\n"
            "• /play - Быстрый поиск игры\n"
            "• /createroom - Создать комнату\n"
            "• /join - Присоединиться к комнате\n"
            "• /rooms - Список комнат\n"
            "• /help - Помощь по игре"
        )

    def format_help(self) -> str:
        return (
            "🎮 Помощь по игре в Мафию\n\n"
            "📋 Основные команды:\n"
            "• /play - Начать быстрый поиск игры\n"
            "• /createroom - Создать свою комнату\n"
            "• /join [ID] - Присоединиться к комнате\n"
            "• /rooms - Показать доступные комнаты\n"
            "• /room - Показать текущую комнату\n"
            "• /ready - Готовность к игре\n"
            "• /setupbots - Настроить AI ботов\n"
            "• /startgame - Начать игру\n"
            "• /leave - Покинуть комнату\n"
            "• /mchat - Показать историю чата мафии\n\n"
            "🎭 Роли в игре:\n"
            "• Мафия, Дон - убивают ночью\n"
            "• Шериф - проверяет игроков\n"
            "• Доктор - лечит игроков\n"
            "• Маньяк - независимый убийца\n"
            "• Путана - защищает от голосования\n"
            "• Журналист - подслушивает разговоры\n\n"
            "💬 *Чаты в игре:*\n"
            "• *Дневной чат:* Все живые игроки могут общаться\n"
            "• *Чат мафии:* Только мафия и дон ночью (/mchat)\n"
            "• 🤖 AI-боты активно участвуют в обсуждении!"
        )