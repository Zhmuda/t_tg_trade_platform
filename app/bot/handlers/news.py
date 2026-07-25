from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message

from app.bot.keyboards import back_to_menu_keyboard
from app.bot.states import NewsFlow
from app.config import get_settings
from app.news.telegram_channel import fetch_channel_posts
from app.news.worker import compute_ticker_sentiment

router = Router(name="news")

_PERIODS = {"1 день": 1, "7 дней": 7, "30 дней": 30}


async def cmd_news_core(message: Message, state: FSMContext) -> None:
    """Prompt for a ticker. Never reads message.text - safe to call with a bot-authored
    message (e.g. from the menu router), unlike the /news command handler below which
    parses its own text for an optional inline ticker argument."""
    await state.set_state(NewsFlow.entering_ticker)
    await message.answer("Введите тикер или название компании (например, SBER):", reply_markup=back_to_menu_keyboard())


@router.message(Command("news"))
async def cmd_news(message: Message, state: FSMContext) -> None:
    args = message.text.split()[1:]
    if args:
        await state.update_data(ticker=args[0].upper())
        await _ask_period(message, state)
    else:
        await cmd_news_core(message, state)


@router.message(NewsFlow.entering_ticker)
async def enter_ticker(message: Message, state: FSMContext) -> None:
    await state.update_data(ticker=message.text.strip().upper())
    await _ask_period(message, state)


async def _ask_period(message: Message, state: FSMContext) -> None:
    await state.set_state(NewsFlow.choosing_period)
    buttons = [[InlineKeyboardButton(text=label, callback_data=f"news_period:{days}")] for label, days in _PERIODS.items()]
    await message.answer("За какой период проанализировать новости?", reply_markup=back_to_menu_keyboard(buttons))


@router.callback_query(NewsFlow.choosing_period, F.data.startswith("news_period:"))
async def choose_period(callback: CallbackQuery, state: FSMContext) -> None:
    days = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    ticker = data["ticker"]
    await callback.message.answer(f"Анализирую новости по {ticker} за {days} дн., подождите...")

    retry_buttons = [[InlineKeyboardButton(text="🔁 Другой тикер", callback_data="menu:news")]]

    settings = get_settings()
    channels = settings.news_telegram_channel_list
    channel_posts = await fetch_channel_posts(channels, lookback_minutes=days * 24 * 60) if channels else []

    result = await compute_ticker_sentiment(ticker, days=days, channel_posts=channel_posts)
    if result is None:
        if not settings.newsapi_key:
            reason = "не задан NEWSAPI_KEY в .env"
        elif not settings.gemini_api_key:
            reason = "не задан GEMINI_API_KEY в .env"
        else:
            reason = "новостей за этот период не нашлось, либо не удалось получить оценку от Gemini — подробности в логах контейнера"
        await callback.message.answer(
            f"Не удалось посчитать сентимент по {ticker}: {reason}.", reply_markup=back_to_menu_keyboard(retry_buttons)
        )
        return

    avg_score, sample_size = result
    if avg_score > 0.05:
        verdict = f"📈 ПОЗИТИВНЫЙ ({avg_score:.2f})"
    elif avg_score < -0.05:
        verdict = f"📉 НЕГАТИВНЫЙ ({avg_score:.2f})"
    else:
        verdict = f"⚖ НЕЙТРАЛЬНЫЙ ({avg_score:.2f})"
    await callback.message.answer(
        f"Сентимент по {ticker} за {days} дн. (проанализировано {sample_size} новостей):\n{verdict}",
        reply_markup=back_to_menu_keyboard(retry_buttons),
    )
