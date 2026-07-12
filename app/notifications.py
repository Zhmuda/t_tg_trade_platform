import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)

_bot: Bot | None = None


def set_bot(bot: Bot) -> None:
    """Called once at startup so background code (the live execution engine, which has
    no Message/CallbackQuery to reply through) can still push messages to a user."""
    global _bot
    _bot = bot


async def notify_user(user_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    if _bot is None:
        return
    try:
        await _bot.send_message(user_id, text, reply_markup=reply_markup)
    except Exception:
        logger.exception("Не удалось отправить уведомление пользователю %s", user_id)
