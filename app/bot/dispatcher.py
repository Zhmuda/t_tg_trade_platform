from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.bot.handlers import backtest, history, menu, news, onboarding, strategies, trading
from app.bot.middlewares import ErrorHandlingMiddleware
from app.config import get_settings

BOT_COMMANDS = [
    BotCommand(command="start", description="Подключить/обновить токены"),
    BotCommand(command="menu", description="Открыть меню кнопок"),
    BotCommand(command="strategies", description="Список доступных стратегий"),
    BotCommand(command="backtest", description="Бэктест стратегии на истории"),
    BotCommand(command="demo", description="Запустить демо-торговлю (Sandbox)"),
    BotCommand(command="trade", description="Запустить реальную торговлю"),
    BotCommand(command="positions", description="Мои запущенные стратегии"),
    BotCommand(command="history", description="История сделок по стратегии"),
    BotCommand(command="pnl", description="Сводный P&L по всем стратегиям"),
    BotCommand(command="resume", description="Возобновить остановленную стратегию по ID"),
    BotCommand(command="stop", description="Остановить стратегию по ID"),
    BotCommand(command="stop_all", description="Остановить все мои стратегии"),
    BotCommand(command="alerts", description="Пороги уведомлений о P&L по стратегии"),
    BotCommand(command="news", description="Новостной сентимент по тикеру"),
]


def build_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    settings = get_settings()
    session = AiohttpSession(proxy=settings.outbound_proxy_url or None)
    bot = Bot(token=settings.telegram_bot_token, session=session)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(ErrorHandlingMiddleware())
    dp.callback_query.middleware(ErrorHandlingMiddleware())

    # menu router first: its "☰ Меню" text handler has no FSM-state filter and must win
    # over per-state handlers (e.g. BacktestFlow.entering_ticker) that would otherwise
    # swallow the tap as if it were free-text input to whatever flow is in progress.
    dp.include_router(menu.router)
    dp.include_router(onboarding.router)
    dp.include_router(strategies.router)
    dp.include_router(backtest.router)
    dp.include_router(trading.router)
    dp.include_router(history.router)
    dp.include_router(news.router)

    return bot, dp
