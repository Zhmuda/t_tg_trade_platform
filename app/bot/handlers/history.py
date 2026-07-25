import asyncio
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from aiogram import F, Router  # noqa: E402
from aiogram.filters import Command  # noqa: E402
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, Message  # noqa: E402

from app.bot.keyboards import back_to_menu_keyboard  # noqa: E402
from app.db.models import StrategyInstance, Trade, TradingMode  # noqa: E402
from app.db.repository import list_strategy_instances, list_trades, todays_realized_pnl, total_realized_pnl  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.execution import manager  # noqa: E402

router = Router(name="history")

_PAGE_SIZE = 10


def _format_trade(trade: Trade) -> str:
    when = trade.closed_at.strftime("%d.%m %H:%M") if trade.closed_at else "?"
    pnl = trade.pnl or 0.0
    sign = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")
    pct = ""
    if trade.entry_price:
        pct = f" ({(trade.price - trade.entry_price) / trade.entry_price * 100:+.2f}%)"
    return f"{sign} {when} · {trade.lots} лот. по {trade.price:.2f} · P&L: {pnl:+.2f} руб.{pct}"


def _render_pnl_curve_png(trades: list[Trade]) -> bytes:
    ordered = sorted(trades, key=lambda t: t.closed_at)
    cumulative = 0.0
    xs, ys = [], []
    for trade in ordered:
        cumulative += trade.pnl or 0.0
        xs.append(trade.closed_at)
        ys.append(cumulative)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(xs, ys, marker="o", markersize=3)
    ax.axhline(0, color="grey", linewidth=0.8, linestyle="--")
    ax.set_title("Накопленный P&L по сделкам")
    ax.set_xlabel("Время")
    ax.set_ylabel("P&L, руб.")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


async def _load_instance_and_trades(instance_id: int, user_id: int) -> tuple[StrategyInstance | None, list[Trade]]:
    async with get_session() as session:
        instances = await list_strategy_instances(session, user_id)
        instance = next((inst for inst in instances if inst.id == instance_id), None)
        if instance is None:
            return None, []
        trades = await list_trades(session, instance_id)
    return instance, trades


def _build_history_text(instance: StrategyInstance, trades: list[Trade], page: int) -> str:
    running = manager.is_running(instance.id)
    status = "🟢 работает" if running else "⚪ остановлена"
    total_pnl = sum(t.pnl or 0.0 for t in trades)
    wins = sum(1 for t in trades if (t.pnl or 0.0) > 0)
    win_rate = (wins / len(trades) * 100) if trades else 0.0

    lines = [
        f"📜 История стратегии #{instance.id} · {instance.strategy_name} · {instance.ticker} ({instance.mode.value}) — {status}",
        "",
        f"Всего закрытых сделок: {len(trades)} · Win rate: {win_rate:.0f}%",
        f"Суммарный P&L: {total_pnl:+.2f} руб.",
    ]

    if trades:
        start = page * _PAGE_SIZE
        page_trades = trades[start : start + _PAGE_SIZE]
        lines.append("")
        lines.append(f"Сделки {start + 1}–{start + len(page_trades)} из {len(trades)} (сначала новые):")
        for trade in page_trades:
            lines.append(_format_trade(trade))
    else:
        lines.append("")
        lines.append("Пока нет ни одной закрытой сделки — либо стратегия ещё не входила в позицию, либо ждёт продажи.")

    return "\n".join(lines)


def _history_buttons(instance_id: int, trades: list[Trade], page: int) -> list[list[InlineKeyboardButton]]:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Пред.", callback_data=f"history_page:{instance_id}:{page - 1}"))
    if (page + 1) * _PAGE_SIZE < len(trades):
        nav.append(InlineKeyboardButton(text="Ещё ▶️", callback_data=f"history_page:{instance_id}:{page + 1}"))
    return [nav] if nav else []


async def cmd_history_core(message: Message, user_id: int) -> None:
    async with get_session() as session:
        instances = await list_strategy_instances(session, user_id)
    if not instances:
        await message.answer("У вас нет стратегий. Используйте /demo или /trade, чтобы запустить.")
        return

    buttons = []
    for inst in instances:
        async with get_session() as session:
            trades = await list_trades(session, inst.id)
        total_pnl = sum(t.pnl or 0.0 for t in trades)
        label = f"#{inst.id} {inst.strategy_name} · {inst.ticker} ({inst.mode.value}) — {len(trades)} сделок, {total_pnl:+.0f} руб."
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"history_id:{inst.id}")])

    await message.answer("Выберите стратегию, чтобы посмотреть историю сделок:", reply_markup=back_to_menu_keyboard(buttons))


@router.message(Command("history"))
async def cmd_history(message: Message) -> None:
    args = message.text.split()[1:]
    if args and args[0].isdigit():
        await _show_instance_history(message, int(args[0]), message.from_user.id)
        return
    await cmd_history_core(message, message.from_user.id)


async def _show_instance_history(message: Message, instance_id: int, user_id: int) -> None:
    instance, trades = await _load_instance_and_trades(instance_id, user_id)
    if instance is None:
        await message.answer("Стратегия с таким ID не найдена среди ваших.")
        return

    text = _build_history_text(instance, trades, page=0)
    buttons = _history_buttons(instance_id, trades, page=0)

    if trades:
        png = await asyncio.to_thread(_render_pnl_curve_png, trades)
        await message.answer_photo(
            BufferedInputFile(png, filename="pnl_curve.png"),
            caption=text,
            reply_markup=back_to_menu_keyboard(buttons),
        )
    else:
        await message.answer(text, reply_markup=back_to_menu_keyboard(buttons))


@router.callback_query(F.data.startswith("history_id:"))
async def history_via_button(callback: CallbackQuery) -> None:
    instance_id = int(callback.data.split(":", 1)[1])
    await callback.answer()
    await _show_instance_history(callback.message, instance_id, callback.from_user.id)


@router.callback_query(F.data.startswith("history_page:"))
async def history_page_via_button(callback: CallbackQuery) -> None:
    _, instance_id_str, page_str = callback.data.split(":")
    instance_id, page = int(instance_id_str), int(page_str)
    await callback.answer()

    instance, trades = await _load_instance_and_trades(instance_id, callback.from_user.id)
    if instance is None:
        await callback.message.answer("Стратегия с таким ID не найдена среди ваших.")
        return

    text = _build_history_text(instance, trades, page=page)
    buttons = _history_buttons(instance_id, trades, page=page)
    # Pagination buttons only ever appear once a photo (the P&L curve) has already been
    # sent (page 0 requires trades to exist), so the message being paginated always has a
    # caption to edit rather than plain text.
    await callback.message.edit_caption(caption=text, reply_markup=back_to_menu_keyboard(buttons))


async def cmd_pnl_core(message: Message, user_id: int) -> None:
    async with get_session() as session:
        instances = await list_strategy_instances(session, user_id)
    if not instances:
        await message.answer("У вас нет стратегий. Используйте /demo или /trade, чтобы запустить.")
        return

    totals = {
        TradingMode.SANDBOX: {"total": 0.0, "today": 0.0, "count": 0},
        TradingMode.PRODUCTION: {"total": 0.0, "today": 0.0, "count": 0},
    }
    for inst in instances:
        async with get_session() as session:
            total = await total_realized_pnl(session, inst.id)
            today = await todays_realized_pnl(session, inst.id)
        bucket = totals[inst.mode]
        bucket["total"] += total
        bucket["today"] += today
        bucket["count"] += 1

    def section(label: str, bucket: dict) -> str:
        return (
            f"{label}\n"
            f"  Всего: {bucket['total']:+.2f} руб.\n"
            f"  Сегодня: {bucket['today']:+.2f} руб.\n"
            f"  Стратегий: {bucket['count']}"
        )

    lines = [
        "💰 Сводный P&L по всем стратегиям",
        "",
        section("🟢 Demo (sandbox):", totals[TradingMode.SANDBOX]),
        "",
        section("💵 Реальная торговля:", totals[TradingMode.PRODUCTION]),
    ]
    await message.answer("\n".join(lines), reply_markup=back_to_menu_keyboard())


@router.message(Command("pnl"))
async def cmd_pnl(message: Message) -> None:
    await cmd_pnl_core(message, message.from_user.id)
