import aiohttp
import asyncio
import random
import logging
from config import LLAMA_CONFIG

ROLE_PERSONALITIES = {
    "don": "calm",
    "mafia": "aggressive",
    "maniac": "crazy",
    "detective": "paranoid",
    "doctor": "calm",
    "journalist": "paranoid",
    "whore": "charming",
    "citizen": "default"
}

class AIManager:
    def _normalize_role(self, role: str) -> str:
        if role.lower() in ("whore", "whore", "prostitute", "escort"):
            return "whore"
        return role.lower()

    """
    Менеджер ИИ-игроков:
    - дневные ответы
    - ночные решения
    - LLaMA-интеграция
    - нью-йоркский мафиозный стиль
    """

    def __init__(self, llama_url: str = "http://localhost:11434/api/generate"):
        self.llama_url = llama_url
        self.llama = LlamaIntegration()
        self._ai_players = {}

    def enable_ai_for_player(self, player_id, personality: str = "neutral"):
        """Register a player as AI-driven with a given personality."""
        self._ai_players[player_id] = {"personality": personality}

    def is_ai_player(self, player_id) -> bool:
        """Detect whether a player is AI. Also consider negative IDs as AI for compatibility."""
        try:
            return player_id in self._ai_players or int(player_id) < 0
        except Exception:
            return player_id in self._ai_players


    def _normalize_game_role(self, role_obj) -> str:
        """Normalize various role representations (Enum name/value, RU/EN) to internal keys."""
        try:
            name = getattr(role_obj, "name", "") or ""
            value = getattr(role_obj, "value", "") or ""
            name_l = str(name).lower()
            value_l = str(value).lower()

            ru_map = {
                "мафия": "mafia",
                "дон": "don",
                "доктор": "doctor",
                "шериф": "detective",  # map sheriff to detective persona
                "маньяк": "maniac",
                "путана": "whore",
                "журналист": "journalist",
                "мирный житель": "citizen",
            }

            # direct english names
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

    async def update_suspicion_from_evidence(self, game):
        try:
            for e in getattr(game, 'evidence', []):
                t = e.get('target')
                if t is not None:
                    try:
                        game.adjust_suspicion(t, 2)
                    except Exception:
                        pass
        except Exception:
            pass

    async def ask(self, role: str, message: str, game_state: dict) -> str:
        prompt = self._build_day_prompt(role, message, game_state)
        llama_response = await self._ask_llama(prompt)

        if llama_response and llama_response.strip():
            persona = ROLE_PERSONALITIES.get(role, "default")
            return self._personality_modifier(llama_response.strip(), persona)

        # 🔥 УБРАЛИ фикс-список -> умная заглушка или LLaMA
        return await self.llama.generate_response(prompt) or "Молчу — и вам советую."

    async def generate_night_action(self, role: str, game_state: dict) -> str:
        night_line = self._fallback_night_line(role)
        target = self._night_strategy(role, game_state)
        persona = ROLE_PERSONALITIES.get(role, "default")
        night_line = self._personality_modifier(night_line, persona)
        return f"{night_line}\\nЦель: {target}"

    # --------- новый промпт ---------
    def _build_day_prompt(self, role: str, message: str, state: dict) -> str:
        hist = state.get("history", [])[-5:]
        history = "\n".join(f"{a}: {t}" for a, t in hist)
        return f"""
    Ты — игрок в мафию в стиле Нью-Йоркской криминальной семьи 1970-х.
    Твоя роль: {role}.
    Тебя зовут {state.get("username", "игрок")}.
    Ты участвуешь в дневном обсуждении.
    ПРИДУМАЙ и НАПИШИ свою оригинальную реплику (1-2 коротких предложения).
    Не отвечай на сообщение выше – просто скажи что-то своё.
    Будь жёстким, по-уличному, без шаблонов.
    История чата (последние сообщения):
    {history}
    Ответь от себя:
    """

    # --------- вызов без шаблона ---------
    async def get_ai_discussion_message(self, player_id: int, username: str,situation: str = "") -> str:
        role = self._normalize_game_role(
            self._ai_players.get(player_id, {}).get("role", "citizen"))
        # situation не используем – LLM сама придумывает
        return await self.ask(role=role, message="",game_state={"username": username,"history": situation})  # situation теперь = history

    def _fallback_night_line(self, role: str) -> str:
        night_phrases = {
            "mafia": [
                "Пора делать работу, парни. Семья сама себя не защитит.",
                "Ночь — наше время. Кто-то сегодня не проснётся.",
                "Тсс… решаем тихо. Без шума."
            ],
            "don": [
                "Наступила ночь… и я решаю, кто завтра не увидит солнца.",
                "Семья ждёт моего слова. И я его скажу.",
                "Время пришло. Сделаем всё аккуратно."
            ],
            "maniac": [
                "Ох… вот оно, сладкое время.",
                "Мир спит, а я выбираю новую игрушку.",
                "Тишина… и только моё дыхание в темноте."
            ],
            "journalist": [
                "Ночью все маски падают. Кто-то точно покажет свою слабость.",
                "Мне нужно больше фактов… ночь принесёт подсказки.",
                "Если я не сплю — значит, я ищу правду."
            ],
            "whore": [
                "Ой, мальчики… ночью вы такие разговорчивые.",
                "Я найду, к кому заглянуть… и что вытянуть.",
                "Ночь — моё время. Я узнаю всё, что мне нужно."
            ],
            "detective": [
                "Сегодня я узнаю правду. Кому можно доверять?",
                "В темноте легче услышать ложь.",
                "Иногда ответы приходят лишь ночью."
            ],
            "doctor": [
                "Кого же сегодня прикрыть? Решение тяжелое…",
                "Жизнь и смерть — всё в моих руках.",
                "Я должен выбрать правильно."
            ],
            "citizen": [
                "Темно как в подвале у мафии…",
                "Ну и ночка. Чует сердце — будет беда.",
                "Лишь бы пережить до утра…"
            ]
        }
        return random.choice(night_phrases.get(role, ["Тихая ночь…"]))

    def _night_strategy(self, role: str, state: dict) -> str:
        alive = [p for p in state.get("players", []) if p.get("alive", True)]
        names = [p.get("username") for p in alive]
        if not alive:
            return "никто"
        if role == "don":
            priority = ["detective", "journalist"]
            for target_role in priority:
                for p in alive:
                    if p.get("role") == target_role:
                        return p["username"]
            if state.get("history"):
                return state["history"][-1][0]
        if role == "mafia":
            if state.get("history"):
                return state["history"][-1][0]
        if role == "maniac":
            loners = [p for p in alive if p.get("username") not in [h[0] for h in state.get("history", [])]]
            if loners:
                return random.choice(loners)["username"]
        if role == "detective":
            if state.get("history"):
                return state["history"][-1][0]
        if role == "doctor":
            if state.get("history"):
                return state["history"][-1][0]
        if role == "journalist":
            if state.get("history"):
                return state["history"][-1][0]
        if role == "whore":
            if state.get("history"):
                return state["history"][-1][0]
        return random.choice(names)

    def _personality_modifier(self, text: str, persona: str) -> str:
        if persona == "aggressive":
            return text + " И запомни это, понял?"
        if persona == "calm":
            return "…" + text.lower().capitalize()
        if persona == "paranoid":
            return text + " Но я никому не верю. Никому."
        if persona == "crazy":
            return text.replace(".", "!") + "! ХА-ХА-ХА!"
        if persona == "charming":
            return text + " Дорогуша."
        return text

    def _fallback_day_answer(self, role: str) -> str:
        phrases = {
            "mafia": [
                "Эй, тихо там. Я всё вижу.",
                "Не нравится мне этот разговор.",
                "Хм... подозрительно, дружок."
            ],
            "don": [
                "Сынок… я за этим столом уже двадцать лет. Не вздумай меня учить.",
                "Если я молчу — значит, думаю. А вот это уж точно должно тебя беспокоить.",
                "В этой семье каждый знает своё место. Ты своё не перепутал?"
            ],
            "maniac": [
                "Хе-хе… какие же вы все смешные.",
                "Сегодня будет весело. Очень весело.",
                "Тсс… я выбираю следующего."
            ],
            "journalist": [
                "Так-так… интересный поворот.",
                "Мне нужны факты… а здесь пахнет ложью.",
                "Парни, у меня есть вопросы."
            ],
            "whore": [
                "Ой, сладкий, да не строй из себя святого.",
                "Я-то знаю, кто где бывает ночью.",
                "Если хочешь правду — спроси меня."
            ],
            "detective": [
                "Я присматриваюсь… кое-что не сходится.",
                "Ты что-то скрываешь?",
                "Мне нужно больше информации."
            ],
            "doctor": [
                "Семья под моей защитой.",
                "Я знаю, кого сегодня спасать.",
                "В этой игре главное — выжить."
            ],
            "citizen": [
                "Мне это не нравится.",
                "Кто-то здесь врёт.",
                "Мы найдём мафию, парни."
            ],
        }
        return random.choice(phrases.get(role, ["Ладно..."]))

    async def _ask_llama(self, prompt: str) -> str | None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.llama_url, json={"prompt": prompt,"max_tokens": LLAMA_CONFIG["max_tokens"],"temperature": LLAMA_CONFIG["temperature"],"top_p": 0.95}) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    logging.info(f"[LLaMA raw] {data}")
                    return data.get("response")
        except Exception as e:
            logging.error(f"[AIManager] Ошибка запроса к LLaMA: {e}")
            return None



