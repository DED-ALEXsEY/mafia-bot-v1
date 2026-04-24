import requests
import json
import logging
import asyncio
import random
import re
from typing import Dict, List, Optional
from config import LLAMA_CONFIG
from datetime import datetime

logger = logging.getLogger(__name__)


class LlamaIntegration:
    def __init__(self,real_url: str = LLAMA_CONFIG["base_url"],fallback_url: str = "http://localhost:8080"):
        self.real_url = real_url
        self.fallback_url = fallback_url
        self.use_real = self._check_real_llama()
        logger.info(f"Llama mode: {'REAL' if self.use_real else 'FALLBACK'}")

    def _check_real_llama(self) -> bool:
        try:
            r = requests.post(f"{self.real_url}/api/generate",json={"model": "llama3.2", "prompt": "test", "stream": False},timeout=5)
            if r.status_code == 200:
                logger.info("✅ Ollama подключён")
                return True
        except Exception as e:
            logger.warning(f"⚠️ Ollama не отвечает ({e}), используется fallback")
        return False

    def generate_response(self, prompt: str, max_tokens: int = 150) -> Optional[str]:
        if self.use_real:
            try:
                r = requests.post(f"{self.real_url}/api/generate",json={"model": "llama3.2", "prompt": prompt,"stream": False, "max_tokens": max_tokens},timeout=30)
                if r.status_code == 200:
                    return r.json().get("response", "").strip()
            except Exception as e:
                logger.warning(f"Real Llama failed ({e}), switching to fallback")
                self.use_real = False   # больше не пробуем до перезапуска

        # ---------- fallback ----------
        return self._get_smart_fallback_response(prompt)

    def _get_smart_fallback_response(self, prompt: str) -> str:
        """Умная система ответов-заглушек с контекстом"""
        prompt_lower = prompt.lower()

        role = self._extract_role(prompt_lower)
        target = self._extract_target(prompt)
        action_type = self._determine_action_type(prompt_lower)

        # Генерация контекстного ответа
        return self._generate_contextual_response(role, action_type, target, prompt_lower)

    def _extract_role(self, prompt_lower: str) -> str:
        """Извлекает роль из промпта"""
        if any(word in prompt_lower for word in ["дон мафии", "дон"]):
            return "don"
        elif any(word in prompt_lower for word in ["мафия", "mafia"]):
            return "mafia"
        elif any(word in prompt_lower for word in ["шериф", "sheriff"]):
            return "sheriff"
        elif any(word in prompt_lower for word in ["доктор", "doctor"]):
            return "doctor"
        elif any(word in prompt_lower for word in ["маньяк", "maniac"]):
            return "maniac"
        elif any(word in prompt_lower for word in ["путана", "whore"]):
            return "whore"
        elif any(word in prompt_lower for word in ["журналист", "journalist"]):
            return "journalist"
        else:
            return "civilian"

    def _extract_target(self, prompt: str) -> Optional[str]:
        """Извлекает цель из промпта"""
        # Ищем паттерны типа "цель: Имя", "против: Имя", "target: Имя"
        patterns = [
            r'цель:\s*([^\n.,!?]+)',
            r'против:\s*([^\n.,!?]+)',
            r'target:\s*([^\n.,!?]+)',
            r'выбрал\s+([^\n.,!?]+)',
            r'голосуешь против\s+([^\n.,!?]+)',
            r'выбрала\s+([^\n.,!?]+)',
            r'проверить\s+([^\n.,!?]+)',
            r'защитить\s+([^\n.,!?]+)',
            r'убить\s+([^\n.,!?]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _determine_action_type(self, prompt_lower: str) -> str:
        """Определяет тип действия"""
        if any(word in prompt_lower for word in ["ноч", "night", "убить", "kill", "проверить", "защитить"]):
            return "night_action"
        elif any(word in prompt_lower for word in ["голосовани", "vote", "подозреваю", "голосую"]):
            return "voting"
        elif any(word in prompt_lower for word in ["обсуждени", "discuss", "заявлен", "скажи"]):
            return "discussion"
        elif any(word in prompt_lower for word in ["обосновани", "reasoning", "почему"]):
            return "reasoning"
        else:
            return "general"

    def _generate_contextual_response(self, role: str, action_type: str, target: str, prompt_lower: str) -> str:
        """Генерирует контекстный ответ на основе роли и действия"""

        # Расширенная база шаблонов ответов для всех ролей из roles.py
        templates = {
            # Основные роли мафии
            "mafia": {
                "night_action": [
                    "Как мафия, я выбрал {target} - его поведение слишком аналитическое для мирного жителя.",
                    "{target} должен исчезнуть. Вчера он почти раскрыл нашего товарища.",
                    "Устраним {target} - он задает неудобные вопросы и представляет угрозу.",
                    "Ночью мы уберем {target}. Его молчание говорит о многом.",
                    "{target} ведет себя как шериф. Лучше перестраховаться.",
                    "Этот {target} слишком внимателен к деталям. Опасно оставлять в живых.",
                    "Выбираю {target} - он проявляет лидерские качества, что опасно для нас."
                ],
                "voting": [
                    "Голосую против {target} - он пытается отвести подозрения от настоящей мафии.",
                    "{target} ведет себя подозрительно. Идеальная жертва для отвлечения внимания.",
                    "Поддерживаю исключение {target} - так мы скроем настоящих преступников.",
                    "{target} выглядит идеальным козлом отпущения в этой ситуации.",
                    "Надо убрать {target} - он начинает догадываться о нашей организации."
                ],
                "discussion": [
                    "Я считаю, что {target} ведет себя странно. Слишком уж он активен.",
                    "Ничего не имею против {target}, но его поведение настораживает.",
                    "Может проверим {target}? У меня есть сомнения.",
                    "Я мирный житель, просто пытаюсь разобраться в ситуации.",
                    "{target} слишком громко заявляет о своей невиновности."
                ]
            },

            # Дон мафии
            "don": {
                "night_action": [
                    "Как дон, я принимаю решение убить {target}. Мафия права - он опасен.",
                    "Выбираю {target}. Его стратегическое мышление угрожает нашей семье.",
                    "Ночью умрет {target}. Он слишком близко подобрался к правде.",
                    "Мой вердикт - {target} должен умереть. Он лидер среди мирных.",
                    "Как глава семьи, я одобряю устранение {target}. Он представляет угрозу.",
                    "{target} ведет расследование. Мы должны остановить его."
                ],
                "voting": [
                    "Как дон, я голосую против {target}. Он мешает нашим планам.",
                    "{target} должен быть устранен. Его аналитика слишком точна.",
                    "Поддерживаю исключение {target} - он вносит хаос в наши ряды.",
                    "Мой голос против {target}. Он пытается раскрыть нашу сеть."
                ],
                "discussion": [
                    "Как уважаемый житель города, я призываю к спокойствию и разуму.",
                    "Давайте не будем поддаваться панике. Истина откроется.",
                    "Я внимательно слежу за развитием событий как опытный житель.",
                    "{target} делает поспешные выводы. Нужно больше доказательств."
                ]
            },

            # Шериф
            "sheriff": {
                "night_action": [
                    "Проверю {target} - вчера он делал странные заявления.",
                    "Как шериф, я должен проверить {target}. У меня есть подозрения.",
                    "{target} попал под мой прицел. Узнаем его истинную роль.",
                    "Ночная проверка {target} покажет, на чьей он стороне.",
                    "Выбираю {target} для проверки - его пассивность подозрительна.",
                    "Проверяю {target} - его внезапная активность вызывает вопросы.",
                    "{target} избегал моего взгляда. Стоит проверить его."
                ],
                "voting": [
                    "Голосую против {target} - результаты проверки неутешительные.",
                    "Как шериф, я вынужден голосовать за {target}. Доказательства есть.",
                    "{target} скрывает свою роль. Голосую за исключение.",
                    "На основе ночной проверки поддерживаю исключение {target}.",
                    "Мое расследование указывает на {target}. Голосую за его исключение."
                ],
                "discussion": [
                    "Как шериф, я должен быть осторожен в высказываниях.",
                    "У меня есть кое-какая информация, но пока рано ею делиться.",
                    "Нужно проанализировать поведение всех игроков.",
                    "Я доверяю своей интуиции и наблюдениям.",
                    "Правда скоро откроется. Нужно набраться терпения."
                ]
            },

            # Доктор
            "doctor": {
                "night_action": [
                    "Выберу {target} для защиты - он кажется важным для города.",
                    "Как доктор, я должен защитить {target}. Он выглядит честным.",
                    "Спасу {target} - его смерть будет большой потерей.",
                    "Защищаю {target} - интуиция подсказывает, что он невиновен.",
                    "{target} нужен городу. Постараюсь его уберечь.",
                    "Лечу {target} - его знания могут помочь нам победить.",
                    "Выбираю {target} для защиты. Он кажется искренним."
                ],
                "voting": [
                    "Голосую против {target} - его поведение действительно подозрительно.",
                    "Как доктор, я видел многое. {target} вызывает сомнения.",
                    "Поддерживаю исключение {target} - для безопасности города.",
                    "{target} выглядит опасным. Лучше перестраховаться.",
                    "Медицинская интуиция подсказывает, что {target} нечист."
                ],
                "discussion": [
                    "Как доктор, я призываю к здравомыслию и спокойствию.",
                    "Жизнь каждого важна, но безопасность города - превыше всего.",
                    "Я видел достаточно, чтобы делать выводы.",
                    "Давайте действовать разумно, а не эмоционально."
                ]
            },

            # Маньяк
            "maniac": {
                "night_action": [
                    "Ха-ха-ха! Сегодня умрет {target}. Мне нравится его страх.",
                    "Выбираю {target} - его смерть будет особенно зрелищной.",
                    "Как маньяк, я наслаждаюсь выбором. {target} - идеальная жертва.",
                    "Ночью я приду за {target}. Пусть город содрогнется от ужаса.",
                    "{target} думал, что в безопасности. Как он ошибался...",
                    "Кровь {target} украсит эту ночь. Я уже чувствую его страх.",
                    "{target} слишком доверчив. Идеальная жертва для моей игры."
                ],
                "voting": [
                    "Голосую против {target}. Его паника так забавна!",
                    "Уберу {target} - его истерики надоели.",
                    "Ха-ха! {target} так боится смерти... Голосую за него!",
                    "Пусть {target} умрет. Его страх - лучшая награда.",
                    "Выбираю {target} - его агония будет восхитительна."
                ],
                "discussion": [
                    "Какой интересный хаос... Мне нравится эта игра!",
                    "Страх витает в воздухе... Восхитительно!",
                    "Ха-ха! Смотрите, как они боятся друг друга!",
                    "Кто следующий? Я уже не могу дождаться...",
                    "Эта ночь будет кровавой, обещаю!"
                ]
            },

            # Путана
            "whore": {
                "night_action": [
                    "Сегодня я проведу ночь с {target}. Он нуждается в защите.",
                    "Выбираю {target} - его невинность нуждается в охране.",
                    "Как путана, я защищу {target} от несправедливых обвинений.",
                    "{target} заслуживает безопасности. Я обеспечу ему защиту.",
                    "Ночью я буду с {target}. Никто не посмеет тронуть его.",
                    "Мое внимание сегодня для {target}. Он будет в безопасности.",
                    "Защищаю {target} - он кажется честным и нужным городу."
                ],
                "voting": [
                    "Голосую против {target} - он вел себя подозрительно со мной.",
                    "Как путана, я вижу фальшь в {target}. Голосую за исключение.",
                    "{target} пытался меня обмануть. Поддерживаю его исключение.",
                    "Моя интуиция говорит, что {target} опасен."
                ],
                "discussion": [
                    "Я вижу многое, о чем другие даже не догадываются...",
                    "Доверьтесь мне, я чувствую, кто говорит правду.",
                    "Ночью открываются многие секреты этого города.",
                    "Я знаю больше, чем кажется на первый взгляд."
                ]
            },

            # Журналист
            "journalist": {
                "night_action": [
                    "Подслушаю разговор с участием {target}. Узнаем его связи.",
                    "Как журналист, я изучаю коммуникации {target}.",
                    "{target} в центре моего расследования сегодня.",
                    "Прослушаю переговоры с {target}. Правда должна всплыть.",
                    "Исследую связи {target}. Информация - это сила.",
                    "Ночное расследование фокусируется на {target}."
                ],
                "voting": [
                    "Голосую против {target} - мои расследования указывают на него.",
                    "Как журналист, я собрал компромат на {target}.",
                    "Поддерживаю исключение {target} - улики неумолимы.",
                    "Мои источники подтверждают подозрения против {target}.",
                    "Расследование показывает: {target} замешан в темных делах."
                ],
                "discussion": [
                    "У меня есть информация, но нужны доказательства.",
                    "Правда скоро выйдет наружу. Я над этим работаю.",
                    "Как журналист, я собираю факты, а не слухи.",
                    "Скоро мы узнаем всю правду об этом деле.",
                    "Мое расследование приближается к развязке."
                ],
                "investigation_result": [
                    "Мои источники подтверждают - эти двое общались между собой.",
                    "Расследование показывает: между ними есть связь.",
                    "Журналистское чутье не подвело - они контактировали.",
                    "Факты указывают на их взаимодействие.",
                    "Мои наблюдения подтверждают их общение."
                ]
            },

            # Мирный житель
            "civilian": {
                "voting": [
                    "Голосую против {target} - он избегал прямых ответов.",
                    "{target} вел себя агрессивно. Возможно, пытается скрыть правду.",
                    "Подозреваю {target} из-за его пассивности в критические моменты.",
                    "Вчера {target} защищал подозрительного игрока. Голосую за исключение.",
                    "{target} слишком тихий. В тишине часто скрывается обман.",
                    "Мне кажется, {target} что-то скрывает. Лучше исключить.",
                    "{target} меняет свою позицию слишком часто."
                ],
                "discussion": [
                    "Я просто мирный житель, пытаюсь разобраться в этой неразберихе.",
                    "Все так запутанно... Нужно внимательно слушать каждого.",
                    "У меня нет особой информации, но я стараюсь анализировать поведение.",
                    "Надеюсь, мы найдем мафию до того, как они перебьют всех нас.",
                    "Интересно, почему {target} так резко изменил свою позицию?",
                    "Заметил странность в поведении {target}. Стоит присмотреться.",
                    "Я доверяю только фактам и логике.",
                    "Давайте не будем поддаваться эмоциям, а действовать разумно."
                ],
                "general": [
                    "Я просто хочу, чтобы в нашем городе был порядок.",
                    "Надо быть внимательнее к деталям.",
                    "Каждый может ошибиться, но некоторые ошибки слишком подозрительны.",
                    "Я верю, что правда восторжествует."
                ]
            }
        }

        # Получаем соответствующие шаблоны
        role_templates = templates.get(role, templates["civilian"])
        action_templates = role_templates.get(action_type, role_templates.get("discussion", ["Анализирую ситуацию."]))

        # Для журналиста при результате расследования используем специальные реплики
        if role == "journalist" and "результат" in prompt_lower:
            action_templates = role_templates.get("investigation_result", action_templates)

        # Выбираем случайный шаблон
        template = random.choice(action_templates)

        # Заменяем плейсхолдеры
        if target:
            response = template.format(target=target)
        else:
            # Если цели нет, убираем плейсхолдер
            response = template.replace("{target}", "этого игрока").replace("  ", " ").strip()

        # Добавляем немного вариативности в конец
        endings = ["", "", "", "!", "!!", "..."]
        if not response.endswith(('.', '!', '?')):
            response += random.choice(endings)

        return response


class MafiaAIAssistant:
    def __init__(self):
        self.llama = LlamaIntegration()
        self.game_context = {}
        self.player_personalities = {}

    def set_game_context(self, players: List[Dict], day_number: int, game_state: str):
        """Устанавливает контекст текущей игры"""
        self.game_context = {
            "players": players,
            "day_number": day_number,
            "game_state": game_state
        }

    def set_player_personality(self, user_id: int, personality: str):
        """Устанавливает личность для игрока"""
        self.player_personalities[user_id] = personality

    async def ask(self, role: str, message: str, game_state: dict) -> str:
        """Совместимость с внешним вызовом."""
        return self.generate_discussion_message(
            game_state.get("username", "игрок"),
            game_state.get("history", "")
        )

    def generate_night_action_reasoning(self, role: str, target: str, available_targets: List[str]) -> str:
        """Генерирует обоснование для ночного действия"""
        prompt = f"""
        Роль: {role}
        Цель: {target}
        Доступные цели: {', '.join(available_targets)}

        Объясни кратко (1-2 предложения) почему ты выбрал эту цель. 
        Будь убедительным и логичным. Говори в стиле своей роли.

        Обоснование:
        """

        reasoning = self.llama.generate_response(prompt)
        return reasoning or "Решение принято на основе анализа поведения игроков."

    def generate_voting_reasoning(self, voter: str, target: str, alive_players: List[str]) -> str:
        """Генерирует обоснование для голосования"""
        prompt = f"""
        Игрок: {voter}
        Цель голосования: {target}
        Живые игроки: {', '.join(alive_players)}

        Объясни кратко (1-2 предложения) почему ты подозреваешь этого игрока.
        Будь убедительным и логичным.

        Обоснование голосования:
        """

        reasoning = self.llama.generate_response(prompt)
        return reasoning or "Имеются подозрения в нечестной игре."

    def generate_discussion_message(self, player: str, game_situation: str) -> str:
        """Генерирует сообщение для дневного обсуждения"""
        prompt = f"""
        Игрок: {player}
        Ситуация в игре: {game_situation}

        Скажи краткое заявление (1-2 предложения) для обсуждения. 
        Можешь выражать подозрения, защищаться или анализировать ситуацию.

        Заявление:
        """

        message = self.llama.generate_response(prompt)
        return message or "Нужно внимательно проанализировать поведение всех игроков."

    def generate_role_play_message(self, role: str, situation: str) -> str:
        """Генерирует ролевое сообщение в соответствии с ролью"""
        prompt = f"""
        Роль: {role}
        Ситуация: {situation}

        Скажи что-то краткое и в стиле своей роли (1-2 предложения).
        {"Будь хитрым и скрытным если ты мафия." if role == "Мафия" else ""}
        {"Будь мудрым и аналитичным если ты шериф." if role == "Шериф" else ""}
        {"Будь заботливым и внимательным если ты доктор." if role == "Доктор" else ""}
        {"Будь непредсказуемым если ты маньяк." if role == "Маньяк" else ""}
        {"Будь соблазнительной если ты путана." if role == "Путана" else ""}
        {"Будь властным и стратегическим если ты дон мафии." if role == "Дон мафии" else ""}
        {"Будь любопытным и информативным если ты журналист." if role == "Журналист" else ""}

        Сообщение:
        """

        message = self.llama.generate_response(prompt)
        return message or "Я внимательно слежу за развитием событий."

    def generate_journalist_investigation_result(self, target1: str, target2: str, result: bool) -> str:
        """Генерирует результат расследования журналиста"""
        prompt = f"""
        Роль: Журналист
        Цели расследования: {target1} и {target2}
        Результат: {'общались' if result else 'не общались'}

        Сообщи результат своего расследования кратко (1-2 предложения) в стиле журналиста.

        Сообщение:
        """

        message = self.llama.generate_response(prompt)
        return message or f"Мое расследование показывает, что {target1} и {target2} {'общались' if result else 'не общались'}."


# Интеграция с основной игрой
class AIGameManager:
    def __init__(self):
        self.ai_assistant = MafiaAIAssistant()
        self.ai_players = {}  # user_id -> AI данные

    def enable_ai_for_player(self, user_id: int, personality: str = "neutral"):
        """Включает AI для игрока"""
        self.ai_players[user_id] = {
            "personality": personality,
            "enabled": True
        }
        self.ai_assistant.set_player_personality(user_id, personality)

    def disable_ai_for_player(self, user_id: int):
        """Отключает AI для игрока"""
        if user_id in self.ai_players:
            self.ai_players[user_id]["enabled"] = False

    def is_ai_player(self, user_id: int) -> bool:
        """Проверяет, является ли игрок AI"""
        return (user_id in self.ai_players and
                self.ai_players[user_id].get("enabled", False))

    def get_ai_night_reasoning(self, user_id: int, role: str, target: str, available_targets: List[str]) -> str:
        """Получает обоснование ночного действия от AI"""
        if self.is_ai_player(user_id):
            return self.ai_assistant.generate_night_action_reasoning(role, target, available_targets)
        return ""

    def get_ai_voting_reasoning(self, user_id: int, voter: str, target: str, alive_players: List[str]) -> str:
        """Получает обоснование голосования от AI"""
        if self.is_ai_player(user_id):
            return self.ai_assistant.generate_voting_reasoning(voter, target, alive_players)
        return ""

    def get_ai_discussion_message(self, user_id: int, player: str, game_situation: str) -> str:
        """Получает сообщение для обсуждения от AI"""
        if self.is_ai_player(user_id):
            return self.ai_assistant.generate_discussion_message(player, game_situation)
        return ""

    def get_ai_journalist_result(self, user_id: int, target1: str, target2: str, result: bool) -> str:
        """Получает результат расследования журналиста от AI"""
        if self.is_ai_player(user_id):
            return self.ai_assistant.generate_journalist_investigation_result(target1, target2, result)
        return ""

    async def generate_night_action(self, role_norm: str, game_state: dict) -> str:
        """Совместимость с вызовом из process_ai_night_action."""
        # 1-2 секунды «молчания» имитации llama
        await asyncio.sleep(random.uniform(0.3, 1.2))
        # fallback-выбор цели
        players = game_state.get("players", [])
        alive = [p for p in players if p.get("alive")]
        if not alive:
            return "Цель: никто"
        victim = random.choice(alive)["username"]
        return f"Цель: {victim}"

    async def ask(self, role: str, message: str, game_state: dict) -> str:
        """Совместимость с вызовом send_ai_messages_to_chat."""
        await asyncio.sleep(random.uniform(0.3, 1.0))
        # берём ролевое сообщение из существующего fallback
        return self.ai_assistant.generate_discussion_message(
            game_state.get("username", "игрок"),
            game_state.get("history", "")
        )
