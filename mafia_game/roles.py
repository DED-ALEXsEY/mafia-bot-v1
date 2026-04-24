from enum import Enum
import random
from typing import Dict, List


class Role(Enum):
    MAFIA = "Мафия"
    CIVILIAN = "Мирный житель"
    DOCTOR = "Доктор"
    SHERIFF = "Шериф"
    MANIAC = "Маньяк"
    whore = "Путана"
    DON = "Дон"
    JOURNALIST = "Журналист"


class RoleManager:
    def __init__(self):
        self.role_descriptions = {
            Role.MAFIA: "Вы - мафия! Ночью вы предлагаете дону кого убить. Днём старайтесь не выдать себя.",
            Role.CIVILIAN: "Вы - мирный житель. Найдите мафию и голосуйте против них днём.",
            Role.DOCTOR: "Вы - доктор. Ночью можете спасти одного игрока от убийства.",
            Role.SHERIFF: "Вы - шериф. Ночью можете проверить одного игрока на принадлежность к мафии.",
            Role.MANIAC: "Вы - маньяк. Ночью вы можете убить, всех не выдавая себя.",
            Role.whore: "Вы - путана. Ночью можете провести ночь с игроком, защищая его от голосования днём.",
            Role.DON: "Вы - дон мафии! Ночью мафия предлагает вам кандидатов на убийство, а вы принимаете окончательное решение.",
            Role.JOURNALIST: "Вы - журналист. Ночью можете подслушать разговор двух игроков и узнать, общались ли они."
        }

    def get_role_description(self, role: Role) -> str:
        return self.role_descriptions.get(role, "")

    def assign_roles(self, player_ids: List[int]) -> Dict[int, Role]:
        """Распределение ролей между игроками"""
        random.shuffle(player_ids)
        num_players = len(player_ids)
        roles = self._generate_role_distribution(num_players)
        random.shuffle(roles)

        return {player_id: role for player_id, role in zip(player_ids, roles)}

    def _generate_role_distribution(self, num_players: int) -> List[Role]:
        """Генерация распределения ролей в зависимости от количества игроков"""
        if num_players >= 20:
            return [Role.MAFIA] * 4 + [Role.DON, Role.DOCTOR, Role.SHERIFF, Role.MANIAC, Role.whore, Role.JOURNALIST] + [Role.CIVILIAN] * (num_players - 10)
        elif num_players >= 16:
            return [Role.MAFIA] * 3 + [Role.DON, Role.DOCTOR, Role.SHERIFF, Role.MANIAC, Role.whore] + [Role.CIVILIAN] * (num_players - 8)
        elif num_players >= 12:
            return [Role.MAFIA] * 3 + [Role.DON, Role.DOCTOR, Role.SHERIFF, Role.MANIAC, Role.whore] + [Role.CIVILIAN] * (num_players - 7)
        elif num_players >= 10:
            return [Role.MAFIA] * 2 + [Role.DON, Role.DOCTOR, Role.SHERIFF, Role.whore] + [Role.CIVILIAN] * (num_players - 6)
        elif num_players >= 8:
            return [Role.MAFIA] * 2 + [Role.DON, Role.DOCTOR, Role.SHERIFF] + [Role.CIVILIAN] * (num_players - 5)
        elif num_players >= 6:
            return [Role.MAFIA] * 2 + [Role.DOCTOR, Role.SHERIFF] + [Role.CIVILIAN] * (num_players - 4)
        elif num_players >= 4:
            return [Role.MAFIA, Role.DOCTOR, Role.SHERIFF] + [Role.CIVILIAN] * (num_players - 3)
        else:
            return [Role.MAFIA] + [Role.CIVILIAN] * (num_players - 1)

    def get_alive_players(self, players: Dict[int, Dict]) -> List[int]:
        """Получить список ID живых игроков"""
        return [player_id for player_id, player_data in players.items() if player_data.get('alive', True)]

    def get_mafia_players(self, players: Dict[int, Dict]) -> List[int]:
        """Получить список ID игроков мафии (включая дона)"""
        return [player_id for player_id, player_data in players.items()
                if player_data.get('role') in [Role.MAFIA, Role.DON] and player_data.get('alive', True)]

    def get_don_player(self, players: Dict[int, Dict]) -> int:
        """Получить ID дона мафии"""
        for player_id, player_data in players.items():
            if player_data.get('role') == Role.DON and player_data.get('alive', True):
                return player_id
        return None

    def get_special_roles(self) -> List[Role]:
        """Получить список специальных ролей (которые действуют ночью)"""
        return [Role.MAFIA, Role.DOCTOR, Role.SHERIFF, Role.MANIAC, Role.whore, Role.DON, Role.JOURNALIST]

    def is_special_role(self, role: Role) -> bool:
        """Проверить, является ли роль специальной"""
        return role in self.get_special_roles()

    def check_win_condition(self, players: Dict[int, Dict]) -> str:
        """Проверка условий победы"""
        alive_players = self.get_alive_players(players)
        mafia_players = self.get_mafia_players(players)

        if not mafia_players:
            return "Мирные жители"  # Мафии не осталось - победа мирных

        if len(mafia_players) >= len(alive_players) - len(mafia_players):
            return "Мафия"  # Мафия преобладает - победа мафии

        return ""  # Игра продолжается