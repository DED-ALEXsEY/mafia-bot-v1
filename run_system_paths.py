import sys
import os
import threading
import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("runner")

# ---------------------------------------------------------
# Load env
# ---------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
MAFIA_PATH = PROJECT_ROOT / "mafia_game"
LLAMA_PATH = PROJECT_ROOT / "AI"
ONLINE_PATH = PROJECT_ROOT / "Online"


def add_path_once(path: Path) -> None:
    p = str(path.resolve())
    if p not in sys.path:
        sys.path.insert(0, p)


add_path_once(MAFIA_PATH)
add_path_once(LLAMA_PATH)
add_path_once(ONLINE_PATH)

# Теперь можно импортировать проект
from game import MafiaBot  # noqa: E402


# ---------------------------------------------------------
# Config (from env)
# ---------------------------------------------------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

RAW_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2").strip()
START_FALLBACK_SERVER = os.getenv("START_FALLBACK_SERVER", "1").strip() not in ("0", "false", "False")


def normalize_local_base_url(raw_url: str) -> str:
    """
    Делаем ЕДИНУЮ точку, куда будут попадать:
      - проверка Ollama
      - Flask-заглушка
      - (по возможности) интеграция через env OLLAMA_BASE_URL

    Почему 127.0.0.1:
      - Flask безопасно и предсказуемо биндится локально
      - 'localhost' иногда резолвится странно (IPv6 ::1) и ломает проверки
    """
    p = urlparse(raw_url if "://" in raw_url else f"http://{raw_url}")
    port = p.port or 11434
    return f"http://127.0.0.1:{port}"


# Вот она — “одна точка”
EFFECTIVE_LLM_URL = normalize_local_base_url(RAW_OLLAMA_BASE_URL)

# Пробрасываем дальше, чтобы другие модули могли использовать ту же точку
os.environ["OLLAMA_BASE_URL"] = EFFECTIVE_LLM_URL


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def is_llm_endpoint_alive(base_url: str) -> bool:
    """
    Быстрая проверка эндпоинта (Ollama или заглушка):
    1) GET /api/tags — лёгкий запрос для Ollama
    2) POST /api/generate — fallback (может зависеть от модели)
    """
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=3)
        if r.status_code == 200:
            return True
    except Exception:
        pass

    try:
        r = requests.post(
            f"{base_url}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": "ping", "stream": False},
            timeout=5,
        )
        return r.status_code == 200
    except Exception:
        return False


def run_llama_fallback_server_on(base_url: str) -> None:
    """
    Запускаем Flask-заглушку ТАМ ЖЕ, где делаем проверку: EFFECTIVE_LLM_URL.
    То есть проверка и заглушка всегда совпадают.
    """
    try:
        from llama_server import app  # импорт внутри потока

        p = urlparse(base_url)
        host = p.hostname or "127.0.0.1"
        port = p.port or 11434

        # Важно: биндимся на 127.0.0.1, чтобы гарантировать локальный запуск
        bind_host = "127.0.0.1"

        logger.warning("🦙 LLM не отвечает. Стартую Flask-заглушку на %s:%s", bind_host, port)
        app.run(host=bind_host, port=port, debug=False, use_reloader=False)
    except Exception:
        logger.exception("❌ Ошибка запуска Flask-заглушки")


async def run_mafia_bot(token: str) -> None:
    bot = MafiaBot(token)
    logger.info("🤖 Бот мафии запускается (polling)...")

    try:
        await bot.application.initialize()
        await bot.application.start()
        await bot.application.updater.start_polling(drop_pending_updates=True)

        logger.info("✅ Polling запущен. Для остановки нажми Ctrl+C.")
        await asyncio.Event().wait()

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("⏹ Остановка бота...")

    except Exception:
        logger.exception("❌ Ошибка работы бота")

    finally:
        try:
            await bot.application.updater.stop()
        except Exception:
            pass
        try:
            await bot.application.stop()
        except Exception:
            pass
        try:
            await bot.application.shutdown()
        except Exception:
            pass


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
async def main() -> None:
    logger.info("🎮 Запуск системы из разных папок...")

    for p in (MAFIA_PATH, LLAMA_PATH, ONLINE_PATH):
        if not p.exists():
            logger.error("❌ Папка не найдена: %s", p)
            return

    if not BOT_TOKEN:
        logger.error("❌ Укажи TELEGRAM_BOT_TOKEN в .env")
        return

    logger.info("🔌 Единая точка LLM: %s", EFFECTIVE_LLM_URL)

    alive = await asyncio.to_thread(is_llm_endpoint_alive, EFFECTIVE_LLM_URL)
    if alive:
        logger.info("✅ LLM эндпоинт отвечает по %s (Ollama или уже поднятая заглушка)", EFFECTIVE_LLM_URL)
    else:
        if START_FALLBACK_SERVER:
            logger.warning("⚠️  LLM эндпоинт не отвечает по %s", EFFECTIVE_LLM_URL)

            t = threading.Thread(
                target=run_llama_fallback_server_on,
                args=(EFFECTIVE_LLM_URL,),
                daemon=True,
            )
            t.start()

            # даём Flask подняться
            await asyncio.sleep(2)

            # повторная проверка — уже по той же точке
            alive2 = await asyncio.to_thread(is_llm_endpoint_alive, EFFECTIVE_LLM_URL)
            if alive2:
                logger.info("✅ Заглушка поднялась и отвечает по %s", EFFECTIVE_LLM_URL)
            else:
                logger.warning("⚠️  Заглушка не ответила по %s (проверь llama_server.py)", EFFECTIVE_LLM_URL)
        else:
            logger.warning("⚠️  START_FALLBACK_SERVER=0 — заглушку не запускаем")

    logger.info("🚀 Запуск бота мафии...")
    await run_mafia_bot(BOT_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass