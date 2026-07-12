import asyncio
from dataclasses import asdict
from datetime import timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, Message
from t_tech.invest import CandleInterval
from t_tech.invest.utils import now

from app.backtest.engine import run_backtest
from app.backtest.metrics import compute_metrics
from app.backtest.report import render_equity_curve_png, render_text_summary
from app.bot.keyboards import back_to_menu_keyboard
from app.bot.states import BacktestFlow
from app.broker.candles import get_candles_df
from app.broker.client import client_context
from app.broker.instruments import resolve_ticker
from app.db.crypto import decrypt_token
from app.db.models import TradingMode
from app.db.repository import get_broker_credential, save_backtest_run
from app.db.session import get_session
from app.risk.guards import RiskLimits
from app.strategies.registry import available_strategy_names, create_strategy

router = Router(name="backtest")

_PERIODS = {"7 дней": 7, "30 дней": 30, "90 дней": 90}


@router.message(Command("backtest"))
async def cmd_backtest(message: Message, state: FSMContext) -> None:
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"bt_strategy:{name}")] for name in available_strategy_names()]
    await state.set_state(BacktestFlow.choosing_strategy)
    await message.answer("Выберите стратегию для бэктеста:", reply_markup=back_to_menu_keyboard(buttons))


@router.callback_query(BacktestFlow.choosing_strategy, F.data.startswith("bt_strategy:"))
async def choose_strategy(callback: CallbackQuery, state: FSMContext) -> None:
    strategy_name = callback.data.split(":", 1)[1]
    await state.update_data(strategy_name=strategy_name)
    await state.set_state(BacktestFlow.entering_ticker)
    await callback.answer()
    await callback.message.answer("Введите тикер акции (например, SBER):")


@router.message(BacktestFlow.entering_ticker)
async def enter_ticker(message: Message, state: FSMContext) -> None:
    await state.update_data(ticker=message.text.strip().upper())
    buttons = [[InlineKeyboardButton(text=label, callback_data=f"bt_period:{days}")] for label, days in _PERIODS.items()]
    await state.set_state(BacktestFlow.choosing_period)
    await message.answer("За какой период прогнать бэктест?", reply_markup=back_to_menu_keyboard(buttons))


@router.callback_query(BacktestFlow.choosing_period, F.data.startswith("bt_period:"))
async def choose_period_and_run(callback: CallbackQuery, state: FSMContext) -> None:
    days = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    await callback.message.answer("Считаю бэктест, это может занять немного времени...")

    user_id = callback.from_user.id
    async with get_session() as session:
        credential = await get_broker_credential(session, user_id, TradingMode.SANDBOX)
    if credential is None:
        await callback.message.answer("Сначала подключите хотя бы demo-токен через /start.")
        return

    token = decrypt_token(credential.encrypted_token)
    ticker = data["ticker"]
    strategy_name = data["strategy_name"]
    to = now()
    from_ = to - timedelta(days=days)

    try:
        async with client_context(token, TradingMode.SANDBOX) as client:
            instrument = await resolve_ticker(client, ticker)
            df = await get_candles_df(client, instrument.figi, from_, to, CandleInterval.CANDLE_INTERVAL_1_MIN)
    except Exception as exc:
        await callback.message.answer(f"Не удалось получить данные по {ticker}: {exc}")
        return

    strategy = create_strategy(strategy_name)
    limits = RiskLimits()

    try:
        # run_backtest is synchronous, CPU-bound work over potentially tens of thousands
        # of bars - running it inline would block the single event loop this whole bot
        # (Telegram polling, live demo/trade order streams, everything) runs on, for as
        # long as it takes to compute. asyncio.to_thread keeps the bot responsive to other
        # users/commands while this crunches in the background.
        result = await asyncio.to_thread(run_backtest, df, strategy, limits, lot_size=instrument.lot)
    except ValueError as exc:
        await callback.message.answer(str(exc))
        return

    metrics = compute_metrics(result)
    summary = render_text_summary(strategy_name, ticker, result, metrics)
    png = await asyncio.to_thread(render_equity_curve_png, result)

    async with get_session() as session:
        await save_backtest_run(
            session,
            user_id=user_id,
            strategy_name=strategy_name,
            params=strategy.params,
            ticker=ticker,
            date_from=from_,
            date_to=to,
            metrics=asdict(metrics),
        )

    buttons = [[InlineKeyboardButton(text="🔁 Другой тикер", callback_data=f"bt_again:{strategy_name}")]]
    await callback.message.answer_photo(
        BufferedInputFile(png, filename="equity_curve.png"),
        caption=summary,
        reply_markup=back_to_menu_keyboard(buttons),
    )


@router.callback_query(F.data.startswith("bt_again:"))
async def backtest_again(callback: CallbackQuery, state: FSMContext) -> None:
    strategy_name = callback.data.split(":", 1)[1]
    await state.update_data(strategy_name=strategy_name)
    await state.set_state(BacktestFlow.entering_ticker)
    await callback.answer()
    await callback.message.answer(f"Стратегия «{strategy_name}». Введите тикер акции (например, SBER):")
