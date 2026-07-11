from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.states import StrategyFlow
from app.broker.client import client_context
from app.broker.instruments import resolve_ticker
from app.config import get_settings
from app.db.crypto import decrypt_token
from app.db.models import StrategyInstance, StrategyStatus, TradingMode
from app.db.repository import create_strategy_instance, get_broker_credential, list_strategy_instances
from app.db.session import get_session
from app.execution import manager
from app.strategies.registry import available_strategy_names

router = Router(name="trading")


async def _start_flow(message: Message, state: FSMContext, mode: TradingMode) -> None:
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"tr_strategy:{name}")] for name in available_strategy_names()]
    await state.update_data(mode=mode.value)
    await state.set_state(StrategyFlow.choosing_strategy)
    await message.answer("Выберите стратегию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.message(Command("demo"))
async def cmd_demo(message: Message, state: FSMContext) -> None:
    async with get_session() as session:
        credential = await get_broker_credential(session, message.from_user.id, TradingMode.SANDBOX)
    if credential is None:
        await message.answer("Сначала подключите demo-токен через /start.")
        return
    await _start_flow(message, state, TradingMode.SANDBOX)


@router.message(Command("trade"))
async def cmd_trade(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    if message.from_user.id not in settings.real_trading_allowed_user_ids:
        await message.answer(
            "Реальная торговля для вас пока не разблокирована. Добавьте свой Telegram ID "
            "в REAL_TRADING_ALLOWLIST в .env после того, как проверите стратегию в /backtest и /demo."
        )
        return
    async with get_session() as session:
        credential = await get_broker_credential(session, message.from_user.id, TradingMode.PRODUCTION)
    if credential is None:
        await message.answer("Сначала подключите боевой токен через /start.")
        return
    await _start_flow(message, state, TradingMode.PRODUCTION)


@router.callback_query(StrategyFlow.choosing_strategy, F.data.startswith("tr_strategy:"))
async def choose_strategy(callback: CallbackQuery, state: FSMContext) -> None:
    strategy_name = callback.data.split(":", 1)[1]
    await state.update_data(strategy_name=strategy_name)
    await state.set_state(StrategyFlow.entering_ticker)
    await callback.answer()
    await callback.message.answer("Введите тикер акции (например, SBER):")


@router.message(StrategyFlow.entering_ticker)
async def enter_ticker(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    mode = TradingMode(data["mode"])
    ticker = message.text.strip().upper()
    await state.update_data(ticker=ticker)

    if mode == TradingMode.PRODUCTION:
        await state.set_state(StrategyFlow.confirming_real)
        await message.answer(
            "⚠ Вы запускаете стратегию на РЕАЛЬНЫЕ ДЕНЬГИ.\n"
            f"Стратегия: {data['strategy_name']}, тикер: {ticker}.\n"
            "Риск-лимиты по умолчанию: макс. 1 лот на позицию, стоп-лосс 1%, тейк-профит 2%, "
            "дневной лимит убытка 3% от капитала.\n\n"
            "Для подтверждения отправьте одним сообщением: ПОДТВЕРЖДАЮ"
        )
        return

    await _create_and_start(message, state, mode)


@router.message(StrategyFlow.confirming_real, F.text == "ПОДТВЕРЖДАЮ")
async def confirm_real_trading(message: Message, state: FSMContext) -> None:
    await _create_and_start(message, state, TradingMode.PRODUCTION)


@router.message(StrategyFlow.confirming_real)
async def reject_real_trading(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Не подтверждено текстом ПОДТВЕРЖДАЮ — реальная торговля не запущена.")


async def _create_and_start(message: Message, state: FSMContext, mode: TradingMode) -> None:
    data = await state.get_data()
    await state.clear()
    user_id = message.from_user.id
    ticker = data["ticker"]
    strategy_name = data["strategy_name"]

    async with get_session() as session:
        credential = await get_broker_credential(session, user_id, mode)
    if credential is None:
        await message.answer("Токен для этого режима не найден. Настройте его через /start.")
        return
    token = decrypt_token(credential.encrypted_token)

    try:
        async with client_context(token, mode) as client:
            instrument = await resolve_ticker(client, ticker)
    except Exception as exc:
        await message.answer(f"Не удалось найти тикер {ticker}: {exc}")
        return

    async with get_session() as session:
        instance = await create_strategy_instance(
            session,
            user_id=user_id,
            strategy_name=strategy_name,
            params={},
            ticker=ticker,
            figi=instrument.figi,
            mode=mode,
        )
        started = await manager.start(instance.id)

    label = "demo (Sandbox)" if mode == TradingMode.SANDBOX else "РЕАЛЬНОЙ торговле"
    if started:
        await message.answer(f"Стратегия «{strategy_name}» на {ticker} запущена в режиме {label}. ID: {instance.id}")
    else:
        await message.answer("Не удалось запустить стратегию — попробуйте /positions, затем /stop и повторите.")


@router.message(Command("positions"))
async def cmd_positions(message: Message) -> None:
    async with get_session() as session:
        instances = await list_strategy_instances(session, message.from_user.id)
    if not instances:
        await message.answer("У вас нет стратегий. Используйте /demo или /trade, чтобы запустить.")
        return
    lines = []
    for inst in instances:
        status = "работает" if manager.is_running(inst.id) else "остановлена"
        lines.append(f"#{inst.id}: {inst.strategy_name} на {inst.ticker} ({inst.mode.value}) — {status}")
    await message.answer("\n".join(lines))


@router.message(Command("stop"))
async def cmd_stop(message: Message) -> None:
    args = message.text.split()[1:]
    if not args or not args[0].isdigit():
        await message.answer("Укажите ID стратегии: /stop 3 (номер см. в /positions)")
        return
    instance_id = int(args[0])

    async with get_session() as session:
        instance = await session.get(StrategyInstance, instance_id)
    if instance is None or instance.user_id != message.from_user.id:
        await message.answer("Стратегия с таким ID не найдена среди ваших.")
        return

    stopped = await manager.stop(instance_id)
    await message.answer(f"Стратегия #{instance_id} остановлена." if stopped else "Эта стратегия и так не была запущена.")


@router.message(Command("stop_all"))
async def cmd_stop_all(message: Message) -> None:
    async with get_session() as session:
        instances = await list_strategy_instances(session, message.from_user.id, status=StrategyStatus.RUNNING)
    count = 0
    for inst in instances:
        if await manager.stop(inst.id):
            count += 1
    await message.answer(f"Остановлено ваших стратегий: {count}.")
