from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.strategies.registry import available_strategy_names

router = Router(name="strategies")

_DESCRIPTIONS = {
    "sma_cross": "Пересечение скользящих средних — трендовая",
    "sma_cross_test": "То же самое, но с короткими окнами (2/5) — для быстрой проверки, не для реальной торговли",
    "rsi_reversion": "RSI mean-reversion — вход на перепроданности/перекупленности",
    "macd_momentum": "MACD momentum — вход по импульсу",
    "bollinger_breakout": "Пробой полос Боллинджера",
}


@router.message(Command("strategies"))
async def cmd_strategies(message: Message) -> None:
    lines = ["Доступные стратегии:"]
    for name in available_strategy_names():
        lines.append(f"• {name} — {_DESCRIPTIONS.get(name, '')}")
    lines.append(
        "\nИспользуются в /backtest, /demo и /trade. В /demo и /trade можно включить фильтр по "
        "новостному сентименту (NewsAPI + Telegram-каналы) — тогда стратегия не будет покупать, пока "
        "по тикеру заметно негативный новостной фон. Ни одна стратегия не гарантирует прибыль — "
        "сначала проверьте её на /backtest и в /demo."
    )
    buttons = [[InlineKeyboardButton(text="📊 Бэктест", callback_data="menu:backtest")]]
    await message.answer("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
