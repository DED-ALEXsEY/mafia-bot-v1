import logging
from telegram import Update
from telegram.ext import ContextTypes
import asyncio

from .chat_manager import ChatManager, ChatType


class ChatHandlers:
    def __init__(self, chat_manager: ChatManager):
        self.chat_manager = chat_manager
        self.ai_manager = None

    def set_ai_manager(self, ai_manager):
        self.ai_manager = ai_manager

    async def handle_public_chat_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                         game, game_chat_id: int):
        """Исправлено: сообщения теперь доходят до всех живых игроков"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
        message_text = update.message.text

        # Проверяем, жив ли игрок
        if not game.players[user_id]['alive']:
            await update.message.reply_text("❌ Мёртвые игроки не могут говорить!")
            return

        # Добавляем сообщение в историю
        self.chat_manager.add_message(game_chat_id, user_id, username, message_text, ChatType.PUBLIC)

        # Отправляем сообщение ВСЕМ живым игрокам (кроме отправителя)
        alive_players = [pid for pid, data in game.players.items() if data['alive']]
        sent_count = 0

        for player_id in alive_players:
            if player_id == user_id:
                continue  # Пропускаем отправителя

            try:
                await context.bot.send_message(
                    player_id,
                    f"💬 *{username}:* {message_text}",
                    parse_mode='Markdown'
                )
                sent_count += 1
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение игроку {player_id}: {e}")

        # Удаляем оригинальное сообщение из чата (чтобы не мешало)
        try:
            await update.message.delete()
        except Exception:
            pass

    async def handle_mafia_chat_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                        game, game_chat_id: int):
        """Исправлено: сообщения мафии доходят до всех мафиози"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
        message_text = update.message.text

        # Проверяем права доступа
        if not self.chat_manager.can_player_chat_in_mafia(game_chat_id, user_id):
            await update.message.reply_text("❌ Только мафия может писать в этот чат!")
            return

        if not game.players[user_id]['alive']:
            await update.message.reply_text("❌ Мёртвые игроки не могут говорить!")
            return

        # Добавляем в историю
        self.chat_manager.add_message(game_chat_id, user_id, username, message_text, ChatType.MAFIA)

        # Отправляем всей команде мафии
        mafia_members = self.chat_manager.get_mafia_chat_members(game_chat_id)

        for mafia_id in mafia_members:
            if mafia_id == user_id:
                continue  # Пропускаем отправителя

            try:
                await context.bot.send_message(
                    mafia_id,
                    f"🔪 *{username} (мафия):* {message_text}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение мафии {mafia_id}: {e}")

        # Удаляем оригинал
        try:
            await update.message.delete()
        except Exception:
            pass

    async def show_mafia_chat_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                      game_chat_id: int):
        """Исправлено: добавлен limit параметр"""
        user_id = update.effective_user.id

        if not self.chat_manager.can_player_chat_in_mafia(game_chat_id, user_id):
            await update.message.reply_text("❌ Только мафия может просматривать этот чат!")
            return

        # Получаем историю с limit
        chat_history = self.chat_manager.get_chat_history(game_chat_id, ChatType.MAFIA, limit=15)

        if not chat_history:
            await update.message.reply_text(
                "💬 Чат мафии пуст.\n\n"
                "Напишите сообщение в этот чат ночью, чтобы начать общение!"
            )
            return

        history_text = "💬 *История чата мафии:*\n\n"
        for msg in chat_history:
            history_text += f"*{msg.username}:* {msg.message}\n"

        await update.message.reply_text(history_text, parse_mode='Markdown')

    def get_chat_help_text(self) -> str:
        return (
            "💬 *Помощь по чатам мафии:*\n\n"
            "• Днём все сообщения видны всем живым\n"
            "• Ночью только мафия общается между собой\n"
            "• Мёртвые не могут писать\n"
            "• /mchat - история чата мафии"
        )