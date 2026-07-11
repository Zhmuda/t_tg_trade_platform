from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import backtest, news, onboarding, strategies, trading
from app.bot.middlewares import ErrorHandlingMiddleware
from app.config import get_settings


def build_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    settings = get_settings()
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(ErrorHandlingMiddleware())
    dp.callback_query.middleware(ErrorHandlingMiddleware())

    dp.include_router(onboarding.router)
    dp.include_router(strategies.router)
    dp.include_router(backtest.router)
    dp.include_router(trading.router)
    dp.include_router(news.router)

    return bot, dp
