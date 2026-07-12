from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards import back_to_menu_keyboard
from app.bot.states import StrategyFlow
from app.broker.client import client_context, ensure_account_id, get_rub_balance
from app.broker.instruments import resolve_ticker
from app.config import get_settings
from app.db.crypto import decrypt_token
from app.db.models import OrderDirection, StrategyInstance, StrategyStatus, TradingMode
from app.db.repository import (
    create_strategy_instance,
    delete_strategy_instance,
    get_broker_credential,
    latest_order,
    list_strategy_instances,
    todays_realized_pnl,
)
from app.db.session import get_session
from app.execution import manager
from app.strategies.registry import available_strategy_names

router = Router(name="trading")


async def _start_flow(message: Message, state: FSMContext, mode: TradingMode) -> None:
    buttons = [[InlineKeyboardButton(text=name, callback_data=f"tr_strategy:{name}")] for name in available_strategy_names()]
    await state.update_data(mode=mode.value)
    await state.set_state(StrategyFlow.choosing_strategy)
    await message.answer("Выберите стратегию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


async def cmd_demo_core(message: Message, state: FSMContext, user_id: int) -> None:
    async with get_session() as session:
        credential = await get_broker_credential(session, user_id, TradingMode.SANDBOX)
    if credential is None:
        await message.answer("Сначала подключите demo-токен через /start.")
        return
    await _start_flow(message, state, TradingMode.SANDBOX)


@router.message(Command("demo"))
async def cmd_demo(message: Message, state: FSMContext) -> None:
    await cmd_demo_core(message, state, message.from_user.id)


async def cmd_trade_core(message: Message, state: FSMContext, user_id: int) -> None:
    settings = get_settings()
    if user_id not in settings.real_trading_allowed_user_ids:
        await message.answer(
            "Реальная торговля для вас пока не разблокирована. Добавьте свой Telegram ID "
            "в REAL_TRADING_ALLOWLIST в .env после того, как проверите стратегию в /backtest и /demo."
        )
        return
    async with get_session() as session:
        credential = await get_broker_credential(session, user_id, TradingMode.PRODUCTION)
    if credential is None:
        await message.answer("Сначала подключите боевой токен через /start.")
        return
    await _start_flow(message, state, TradingMode.PRODUCTION)


@router.message(Command("trade"))
async def cmd_trade(message: Message, state: FSMContext) -> None:
    await cmd_trade_core(message, state, message.from_user.id)


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
    data = await state.get_data()
    resume_instance_id = data.get("resume_instance_id")
    if resume_instance_id is not None:
        await state.clear()
        started = await manager.start(resume_instance_id)
        await message.answer(
            f"Стратегия #{resume_instance_id} возобновлена." if started else "Не удалось возобновить — попробуйте ещё раз.",
            reply_markup=back_to_menu_keyboard(),
        )
        return
    await _create_and_start(message, state, TradingMode.PRODUCTION)


async def cmd_resume_core(message: Message, user_id: int) -> None:
    async with get_session() as session:
        instances = await list_strategy_instances(session, user_id)
    stopped = [inst for inst in instances if not manager.is_running(inst.id)]
    if not stopped:
        await message.answer("Нечего возобновлять — нет остановленных стратегий.", reply_markup=back_to_menu_keyboard())
        return
    buttons = [
        [InlineKeyboardButton(text=f"#{inst.id} {inst.strategy_name} на {inst.ticker}", callback_data=f"resume_id:{inst.id}")]
        for inst in stopped
    ]
    await message.answer(
        "Какую стратегию возобновить?", reply_markup=back_to_menu_keyboard(buttons)
    )


@router.message(Command("resume"))
async def cmd_resume(message: Message, state: FSMContext) -> None:
    args = message.text.split()[1:]
    if not args or not args[0].isdigit():
        await cmd_resume_core(message, message.from_user.id)
        return
    instance_id = int(args[0])
    await _resume_instance(message, state, instance_id, message.from_user.id)


async def _resume_instance(message: Message, state: FSMContext, instance_id: int, user_id: int) -> None:
    async with get_session() as session:
        instance = await session.get(StrategyInstance, instance_id)
    if instance is None or instance.user_id != user_id:
        await message.answer("Стратегия с таким ID не найдена среди ваших.")
        return
    if manager.is_running(instance_id):
        await message.answer(f"Стратегия #{instance_id} уже работает.")
        return

    if instance.mode == TradingMode.PRODUCTION:
        await state.update_data(resume_instance_id=instance_id)
        await state.set_state(StrategyFlow.confirming_real)
        await message.answer(
            f"⚠ Вы возобновляете РЕАЛЬНУЮ торговлю: {instance.strategy_name} на {instance.ticker}.\n"
            "Для подтверждения отправьте одним сообщением: ПОДТВЕРЖДАЮ"
        )
        return

    started = await manager.start(instance_id)
    await message.answer(
        f"Стратегия #{instance_id} ({instance.strategy_name} на {instance.ticker}, {instance.mode.value}) возобновлена."
        if started
        else "Не удалось возобновить — попробуйте ещё раз.",
        reply_markup=back_to_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("resume_id:"))
async def resume_via_button(callback: CallbackQuery, state: FSMContext) -> None:
    instance_id = int(callback.data.split(":", 1)[1])
    await callback.answer()
    await _resume_instance(callback.message, state, instance_id, callback.from_user.id)


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
    buttons = [[InlineKeyboardButton(text="📈 Мои позиции", callback_data="menu:positions")]]
    if started:
        await message.answer(
            f"Стратегия «{strategy_name}» на {ticker} запущена в режиме {label}. ID: {instance.id}",
            reply_markup=back_to_menu_keyboard(buttons),
        )
    else:
        await message.answer(
            "Не удалось запустить стратегию — попробуйте /positions, затем /stop и повторите.",
            reply_markup=back_to_menu_keyboard(),
        )


async def _account_rub_balance(user_id: int, mode: TradingMode) -> float | None:
    async with get_session() as session:
        credential = await get_broker_credential(session, user_id, mode)
    if credential is None:
        return None
    try:
        token = decrypt_token(credential.encrypted_token)
        async with client_context(token, mode) as client:
            account_id = await ensure_account_id(client, mode, credential.account_id)
            positions_response = await client.operations.get_positions(account_id=account_id)
            return get_rub_balance(positions_response)
    except Exception:
        return None


async def cmd_positions_core(message: Message, user_id: int) -> None:
    async with get_session() as session:
        instances = await list_strategy_instances(session, user_id)
    if not instances:
        await message.answer(
            "У вас нет стратегий. Используйте /demo или /trade, чтобы запустить.",
            reply_markup=back_to_menu_keyboard(),
        )
        return

    balance_cache: dict[TradingMode, float | None] = {}
    for inst in instances:
        running = manager.is_running(inst.id)
        status = "работает" if running else "остановлена"

        async with get_session() as session:
            order = await latest_order(session, inst.id)
            realized_pnl = await todays_realized_pnl(session, inst.id)

        if order is not None and order.direction == OrderDirection.BUY:
            position_line = f"открыта позиция: {order.lots} лот(ов) по {order.price:.2f} руб. (куплено)"
        else:
            position_line = "позиции нет — сейчас в деньгах, ждёт сигнала на вход"

        if inst.mode not in balance_cache:
            balance_cache[inst.mode] = await _account_rub_balance(user_id, inst.mode)
        balance = balance_cache[inst.mode]
        balance_line = f"свободный кэш на счёте: {balance:,.2f} руб." if balance is not None else "баланс счёта: н/д"

        text = (
            f"#{inst.id}: {inst.strategy_name} на {inst.ticker} ({inst.mode.value}) — {status}\n"
            f"  {position_line}\n"
            f"  Реализованный P&L за сегодня: {realized_pnl:+.2f} руб.\n"
            f"  {balance_line}"
        )
        if running:
            buttons = [[InlineKeyboardButton(text="⏹ Стоп", callback_data=f"stop_id:{inst.id}")]]
        else:
            buttons = [
                [
                    InlineKeyboardButton(text="▶️ Возобновить", callback_data=f"resume_id:{inst.id}"),
                    InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_ask:{inst.id}"),
                ]
            ]
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await message.answer("Готово.", reply_markup=back_to_menu_keyboard())


@router.message(Command("positions"))
async def cmd_positions(message: Message) -> None:
    await cmd_positions_core(message, message.from_user.id)


async def cmd_stop_core(message: Message, user_id: int) -> None:
    async with get_session() as session:
        instances = await list_strategy_instances(session, user_id)
    running = [inst for inst in instances if manager.is_running(inst.id)]
    if not running:
        await message.answer("У вас нет запущенных стратегий.", reply_markup=back_to_menu_keyboard())
        return
    buttons = [
        [InlineKeyboardButton(text=f"#{inst.id} {inst.strategy_name} на {inst.ticker}", callback_data=f"stop_id:{inst.id}")]
        for inst in running
    ]
    await message.answer("Какую стратегию остановить?", reply_markup=back_to_menu_keyboard(buttons))


@router.message(Command("stop"))
async def cmd_stop(message: Message) -> None:
    args = message.text.split()[1:]
    if not args or not args[0].isdigit():
        await cmd_stop_core(message, message.from_user.id)
        return
    instance_id = int(args[0])
    await _stop_instance(message, instance_id, message.from_user.id)


async def _stop_instance(message: Message, instance_id: int, user_id: int) -> None:
    async with get_session() as session:
        instance = await session.get(StrategyInstance, instance_id)
    if instance is None or instance.user_id != user_id:
        await message.answer("Стратегия с таким ID не найдена среди ваших.")
        return

    stopped = await manager.stop(instance_id)
    await message.answer(
        f"Стратегия #{instance_id} остановлена." if stopped else "Эта стратегия и так не была запущена.",
        reply_markup=back_to_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("stop_id:"))
async def stop_via_button(callback: CallbackQuery) -> None:
    instance_id = int(callback.data.split(":", 1)[1])
    await callback.answer()
    await _stop_instance(callback.message, instance_id, callback.from_user.id)


@router.message(Command("stop_all"))
async def cmd_stop_all(message: Message) -> None:
    async with get_session() as session:
        instances = await list_strategy_instances(session, message.from_user.id, status=StrategyStatus.RUNNING)
    count = 0
    for inst in instances:
        if await manager.stop(inst.id):
            count += 1
    await message.answer(f"Остановлено ваших стратегий: {count}.", reply_markup=back_to_menu_keyboard())


@router.callback_query(F.data.startswith("delete_ask:"))
async def delete_ask(callback: CallbackQuery) -> None:
    instance_id = int(callback.data.split(":", 1)[1])
    await callback.answer()
    buttons = [
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_confirm:{instance_id}"),
            InlineKeyboardButton(text="✖️ Отмена", callback_data="menu:positions"),
        ]
    ]
    await callback.message.answer(
        f"Удалить стратегию #{instance_id} вместе с историей её ордеров/сделок? Это необратимо.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("delete_confirm:"))
async def delete_confirm(callback: CallbackQuery) -> None:
    instance_id = int(callback.data.split(":", 1)[1])
    user_id = callback.from_user.id
    await callback.answer()

    async with get_session() as session:
        instance = await session.get(StrategyInstance, instance_id)
        if instance is None or instance.user_id != user_id:
            await callback.message.answer("Стратегия с таким ID не найдена среди ваших.")
            return
        if manager.is_running(instance_id):
            await callback.message.answer("Сначала остановите стратегию (⏹ Стоп), потом можно удалить.")
            return
        await delete_strategy_instance(session, instance_id)

    await callback.message.answer(f"Стратегия #{instance_id} удалена.", reply_markup=back_to_menu_keyboard())
