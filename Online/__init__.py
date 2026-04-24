from .hybrid_online import HybridOnlineManager, RoomManager, MatchmakingSystem
import logging

# Настройка логирования для всего пакета
logging.getLogger(__name__).addHandler(logging.NullHandler())

__version__ = "1.0.0"
__author__ = "DED ALEXsEY"

__all__ = ['HybridOnlineManager', 'RoomManager', 'MatchmakingSystem']