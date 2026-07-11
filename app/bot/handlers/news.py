from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.states import NewsFlow
from app.news.worker import compute_ticker_sentiment

router = Router(name="news")

_PERIODS = {"1 день": 1, "7 дней": 7, "30 дней": 30}


@router.message(Command("news"))
async def cmd_news(message: Message, state: FSMContext) -> None:
    args = message.text.split()[1:]
    if args:
        await state.update_data(ticker=args[0].upper())
        await _ask_period(message, state)
    else:
        await state.set_state(NewsFlow.entering_ticker)
        await message.answer("Введите тикер или название компании (например, SBER):")


@router.message(NewsFlow.entering_ticker)
async def enter_ticker(message: Message, state: FSMContext) -> None:
    await state.update_data(ticker=message.text.strip())
    await _ask_period(message, state)


async def _ask_period(message: Message, state: FSMContext) -> None:
    await state.set_state(NewsFlow.choosing_period)
    buttons = [[InlineKeyboardButton(text=label, callback_data=f"news_period:{days}")] for label, days in _PERIODS.items()]
    await message.answer("За какой период проанализировать новости?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(NewsFlow.choosing_period, F.data.startswith("news_period:"))
async def choose_period(callback: CallbackQuery, state: FSMContext) -> None:
    days = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    ticker = data["ticker"]
    await callback.message.answer(f"Анализирую новости по {ticker} за {days} дн., подождите...")

    result = await compute_ticker_sentiment(ticker, days=days)
    if result is None:
        await callback.message.answer("Не нашлось новостей за этот период (или не задан NEWSAPI_KEY в .env).")
        return

    avg_score, sample_size = result
    if avg_score > 0.05:
        verdict = f"📈 ПОЗИТИВНЫЙ ({avg_score:.2f})"
    elif avg_score < -0.05:
        verdict = f"📉 НЕГАТИВНЫЙ ({avg_score:.2f})"
    else:
        verdict = f"⚖ НЕЙТРАЛЬНЫЙ ({avg_score:.2f})"
    await callback.message.answer(
        f"Сентимент по {ticker} за {days} дн. (проанализировано {sample_size} новостей):\n{verdict}"
    )
