import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseMiddleware):
    """Keeps one user's crash from taking down the whole bot process and lets them know
    something went wrong instead of the bot going silent."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception:
            logger.exception("Unhandled error while processing update: %r", event)
            try:
                if isinstance(event, Message):
                    await event.answer("Произошла ошибка при обработке команды. Попробуйте ещё раз позже.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("Произошла ошибка. Попробуйте ещё раз.", show_alert=True)
            except Exception:
                pass
