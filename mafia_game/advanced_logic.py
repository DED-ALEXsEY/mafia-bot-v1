from typing import Dict, List, Set, Optional, TYPE_CHECKING
import asyncio
import random
from mafia_style import MafiaStyle
from roles import Role
from enum import Enum
import logging
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from game import MafiaGame

style = MafiaStyle()


class NightControlleAdvancedGameLogic:
    """
    Улучшенная логика игры для мафии:
    1. Управление ночью — через NightController
    2. Голосование — только суд
    3. Все уведомления идут игрокам через game.broadcast
    """

    def __init__(self, game_instance: "MafiaGame"):
        self.game = game_instance
        self.chat_id = None
        self.pending_votes: Set[int] = set()
        self.night_actions_log: Dict[str, int] = {}
        self.night_completion_event = asyncio.Event()
        self.on_don_no_proposals: Optional[Callable[[], None]] = None

    def register_mafia_proposal(self, mafia_id: int) -> None:
        """Сообщаем NightController, что мафиози сделал предложение Дону"""
        if self.game.night_ctrl:  # защита от None
            self.game.night_ctrl.register_mafia_proposal(mafia_id)

    # ---------- СУД ----------
    def setup_voting_session(self, alive_players: List[int]) -> int:
        self.pending_votes = set(alive_players)
        logger.info(f"Voting session started, awaiting {len(alive_players)} votes")
        return len(alive_players)

    def register_vote(self, voter_id: int) -> bool:
        if voter_id in self.pending_votes:
            self.pending_votes.remove(voter_id)
            logger.info(f"Vote registered from {voter_id}, remaining: {len(self.pending_votes)}")
        return len(self.pending_votes) == 0

    def are_all_votes_collected(self) -> bool:
        return len(self.pending_votes) == 0

    def get_pending_votes_count(self) -> int:
        return len(self.pending_votes)

    def get_pending_voters_list(self) -> List[str]:
        pending_names = []
        for player_id in self.pending_votes:
            if player_id in self.game.players:
                pending_names.append(self.game.players[player_id]['username'])
        return pending_names

    def get_voting_status(self) -> str:
        return "Все голоса собраны" if self.are_all_votes_collected() else f"Ожидаем {self.get_pending_votes_count()} голосов"

    # ---------- НОЧНЫЕ ДЕЙСТВИЯ ----------
    async def handle_night_action(self, action_type: str, user_id: int, target_id: int, bot_instance, context) -> bool:
        game = self.game
        chat_id = game.chat_id

        try:
            role = game.players[user_id]['role']
            target_name = game.players[target_id]['username']

            # === МАФИЯ: ПРЕДЛОЖЕНИЕ ЦЕЛИ ===
            if action_type == "mafia_suggest":
                # ← ВАЛИДАЦИЯ: мафия не может предложить убить своего
                if game.players[target_id]['role'] in (Role.MAFIA, Role.DON):
                    logger.warning(f"Мафия {user_id} пыталась убить свою ({target_id})")
                    return False

                game.mafia_suggestions[user_id] = target_id
                game.night_actions_done.add(f"mafia_suggest_{user_id}")
                self.register_mafia_proposal(user_id)

                alive_maf = [p for p in game.get_alive_players()
                             if game.players[p]['role'] == Role.MAFIA]
                don_id = game.get_don_player()
                don_alive = don_id and game.players[don_id]['alive']

                if not don_alive:
                    # ← ДОН МЕРТВ: автовыбор
                    if len(game.mafia_suggestions) == len(alive_maf):
                        candidates = list(game.mafia_suggestions.values())
                        candidates = [c for c in candidates
                                      if game.players[c]['role'] not in (Role.MAFIA, Role.DON)]
                        if candidates:
                            target = random.choice(candidates)
                            game.night_actions['mafia_kill'] = target
                            game.night_actions_done.add("mafia_kill_auto")
                            logger.info(f"Дон мертв, мафия убила {game.players[target]['username']}")
                            game.night_ctrl.register_action("don_kill")
                        return True
                else:
                    # ← ДОН ЖИВ: ждем его решения
                    if len(game.mafia_suggestions) == len(alive_maf):
                        candidates = list(set(game.mafia_suggestions.values()))
                        candidates = [c for c in candidates
                                      if game.players[c]['role'] not in (Role.MAFIA, Role.DON)]
                        if candidates:
                            await self._send_don_candidates(don_id, candidates, context)
                        if game.night_ctrl.mafia_proposal_deadline:
                            game.night_ctrl.mafia_proposal_deadline.cancel()

            # === ДОН: ФИНАЛЬНОЕ РЕШЕНИЕ ===
            elif action_type == "don_kill":
                # ← ВАЛИДАЦИЯ
                if game.players[target_id]['role'] in (Role.MAFIA, Role.DON):
                    logger.warning(f"Дон {user_id} пытался убить свою ({target_id})")
                    return False

                game.night_actions['mafia_kill'] = target_id
                game.night_actions_done.add(f"don_kill_{user_id}")
                logger.info(f"Дон выбрал жертву: {target_name}")
                game.night_ctrl.register_action("don_kill")

            elif action_type == "don_kill":
                game.night_actions['mafia_kill'] = target_id
                game.night_actions_done.add(f"don_kill_{user_id}")
                logger.info(f"Don {user_id} finalized kill: {target_name}")

            elif action_type == "doctor_heal":
                game.night_actions['doctor_save'] = target_id
                game.night_actions_done.add(f"doctor_heal_{user_id}")
                logger.info(f"Doctor {user_id} healed {target_name}")

            elif action_type == "sheriff_check":
                target_role = game.players[target_id]['role']
                result = "🔴 Мафия" if target_role.value in ["Мафия", "Дон"] else "🟢 Мирный житель"
                game.night_actions['sheriff_result'] = (target_id, result)
                asyncio.create_task(self._send_sheriff_result(user_id, result, context))
                game.night_actions_done.add(f"sheriff_check_{user_id}")
                logger.info(f"Sheriff {user_id} checked {target_name}: {result}")

            elif action_type == "maniac_kill":
                game.night_actions['maniac_kill'] = target_id
                game.night_actions_done.add(f"maniac_kill_{user_id}")
                logger.info(f"Maniac {user_id} chose to kill {target_name}")

            elif action_type == "route_block":
                game.route_protected = target_id
                game.route_alibi = target_id
                game.night_actions_done.add(f"route_block_{user_id}")
                logger.info(f"Route {user_id} blocked {target_name}")

            elif action_type == "journalist_listen":
                game.journalist_targets.add(target_id)
                game.night_actions_done.add(f"journalist_listen_{user_id}")
                logger.info(f"Journalist {user_id} listened to {target_name}")

            elif action_type == "vote":
                if user_id in game.players and game.players[user_id]['alive']:
                    game.votes[user_id] = target_id
                    logger.info(f"Player {user_id} voted against {target_name}")
                    self.register_vote(user_id)
                return True

            else:
                return False

            game.night_ctrl.register_action(action_type)
            return True

        except Exception as e:
            logger.error(f"Error handling night action: {e}")
            return False

    async def _send_don_candidates(self, don_id: int, candidates: List[int], context) -> None:
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        kb = [[InlineKeyboardButton(self.game.players[c]['username'],callback_data=f"don_final_{c}")] for c in candidates]
        try:
            await context.bot.send_message(
                don_id,
                "📋 Все мафиози высказались. Выберите жертву:",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        except Exception as e:
            logger.error(f"Не удалось отправить список Дону {don_id}: {e}")

    # ----------------------------------------------------------
    # вызывается из night_controller когда Дон молчит / время вышло
    # ----------------------------------------------------------

    async def on_don_no_proposals(self, context) -> None:  # ⬅️ Добавлен context параметр
        game = self.game
        don_id = game.get_don_player()
        if not don_id:
            return
        candidates = list(set(game.mafia_suggestions.values()))
        if not candidates:
            alive = game.get_alive_players()
            candidates = [p for p in alive
                          if game.players[p]['role'] not in (Role.MAFIA, Role.DON)]
        await self._send_don_candidates(don_id, candidates, context)  # ⬅️ Используем переданный context


    # ----------------------------------------------------------
    # финализация когда Дон нажал кнопку (уже была, оставляем)
    # ----------------------------------------------------------
    def setup_don_timer(self, on_silence: Callable[[], None]) -> None:
        self.on_don_no_proposals = on_silence
        self.game.night_ctrl.start_don_waiting()

    # ---------- СУД ----------
    async def start_court_logic(self, game, chat_id: int, context):
        alive = game.get_alive_players()
        if len(alive) <= 1:
            await game.broadcast("❌ Недостаточно игроков для суда.", context)
            return

        suspects = [pid for pid in alive if pid != game.route_alibi]
        if not suspects:
            await game.broadcast("💋 У всех живых алиби — суд не требуется.", context)
            return

        suspect = max(suspects, key=lambda pid: game.suspicion.get(pid, 0))
        await self.run_court_session(game, chat_id, context, suspect)

    async def run_court_session(self, game, chat_id: int, context, suspect_id: int):
        alive = game.get_alive_players()
        game.state = GameState.COURT
        game.court_target = suspect_id
        game.court_votes.clear()

        name = game.players[suspect_id]['username']

        await game.broadcast(
            style.format_court_start() + f"\n\n👤 Обвиняемый: {name}\n⏳ 30 секунд на последнее слово…",
            context,
            parse_mode='HTML'
        )

        await asyncio.sleep(30)

        from telegram import InlineKeyboardMarkup, InlineKeyboardButton

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚔️ За казнь", callback_data="court_kill")],
            [InlineKeyboardButton("🙅 Против", callback_data="court_spare")]
        ])

        for pid in alive:
            try:
                await context.bot.send_message(
                    pid,
                    f"⚖️ Финальное голосование:\nОбвиняемый: {name}",
                    reply_markup=kb
                )
            except Exception as e:
                logger.error(f"Не удалось отправить кнопки суду {pid}: {e}")

    async def register_court_vote(self, game, voter_id: int, vote: str) -> bool:
        game.court_votes[voter_id] = vote
        return len(game.court_votes) == len(game.get_alive_players())

    async def finish_court(self, game, chat_id: int, context):
        target = game.court_target
        name = game.players[target]['username']

        kill_cnt = sum(1 for v in game.court_votes.values() if v == 'kill')
        alive_total = len(game.get_alive_players())

        if kill_cnt >= alive_total * 2 / 3:
            game.players[target]['alive'] = False
            msg = style.format_vote_result(name)
        else:
            msg = f"⚖️ {name} спасён. Суд решил пощадить."

        await game.broadcast(msg, context, parse_mode='HTML')

        game.state = GameState.NIGHT
        game.day_number += 1

        await game.broadcast(
            style.format_night_start(game.day_number),
            context,
            parse_mode='HTML'
        )

    # ---------- УТИЛИТЫ ----------
    async def _send_sheriff_result(self, sheriff_id: int, result: str, context):
        try:
            await context.bot.send_message(sheriff_id, f"🔍 Результат проверки: {result}")
        except Exception as e:
            logger.error(f"Cannot send sheriff result: {e}")
