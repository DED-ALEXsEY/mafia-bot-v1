# night_controller.py
import logging
import asyncio
from roles import Role
from typing import Callable, List, Set, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from game import MafiaGame

logger = logging.getLogger(__name__)

COUNT_ONLY_HUMANS = False

NightEndCallback = Callable[[], None]


class NightController:
    def __init__(self, game: "MafiaGame", ai_manager, on_night_end: NightEndCallback):
        self.game = game
        self.ai_manager = ai_manager
        self.on_night_end = on_night_end
        self._pending: Set[str] = set()
        self.don_proposals: set[int] = set()
        self.mafia_proposal_deadline: Optional[asyncio.Task] = None
        self._night_ended = False  # ← ЗАЩИТА ОТ ПОВТОРНОГО ВЫЗОВА

    def start_night(self) -> None:
        self._pending.clear()
        self._night_ended = False  # Сброс флага
        alive = self.game.get_alive_players()

        don_id = self.game.get_don_player()
        don_alive = don_id and self.game.players[don_id]['alive']

        alive_maf = [p for p in alive if self.game.players[p]['role'] == Role.MAFIA]
        alive_don = [p for p in alive if self.game.players[p]['role'] == Role.DON]

        for pid in alive:
            if COUNT_ONLY_HUMANS and self.ai_manager.is_ai_player(pid):
                continue
            role = self.game.players[pid]['role']

            if role.name == "DOCTOR":
                self._pending.add("doctor_heal")
            elif role.name == "SHERIFF":
                self._pending.add("sheriff_check")
            elif role.name == "MANIAC":
                self._pending.add("maniac_kill")
            elif role.name == "whore":
                self._pending.add("route_block")
            elif role.name == "MAFIA":
                if len(alive_maf) == 1 and not alive_don:
                    self._pending.add("don_kill")
                else:
                    self._pending.add("mafia_suggest")
            elif role.name == "DON":
                self._pending.add("don_kill")

        logger.info(f"NightController: ожидаем {len(self._pending)} действий")

        if self._pending:
            self.mafia_proposal_deadline = asyncio.create_task(self._mafia_proposal_deadline_timer())

    async def _mafia_proposal_deadline_timer(self) -> None:
        await asyncio.sleep(60)
        don_id = self.game.get_don_player()
        don_alive = don_id and self.game.players[don_id]['alive']

        if don_alive and not self.game.night_actions.get('mafia_kill'):
            if self.on_don_no_proposals and not self._night_ended:
                self.on_don_no_proposals()

    def register_action(self, action_type: str) -> None:
        if self._night_ended:  # ← Защита от повторного вызова
            return

        if action_type in self._pending:
            self._pending.remove(action_type)

        if not self._pending and not self._night_ended:
            self._night_ended = True  # ← Блокируем повторы
            self.on_night_end()

    def register_mafia_proposal(self, mafia_id: int) -> None:
        self.don_proposals.add(mafia_id)

    def pending_count(self) -> int:
        return len(self._pending)

    def is_night_ended(self) -> bool:
        return self._night_ended

    def start_don_waiting(self) -> None:
        self.don_proposals: set[int] = set()
        self.don_timer_task = asyncio.create_task(self._don_timer())

    async def _don_timer(self) -> None:
        await asyncio.sleep(15)
        if self.on_don_no_proposals and not self._night_ended:
            self.on_don_no_proposals()