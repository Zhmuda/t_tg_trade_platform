from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.handlers import backtest, news, strategies, trading
from app.bot.keyboards import OPEN_MENU, main_menu_inline_keyboard

router = Router(name="menu")


async def _show_menu(message: Message) -> None:
    await message.answer("Что делаем?", reply_markup=main_menu_inline_keyboard())


@router.message(Command("menu"))
@router.message(F.text == OPEN_MENU)
async def cmd_menu(message: Message) -> None:
    await _show_menu(message)


_ROUTES = {
    "backtest": lambda message, state, user_id: backtest.cmd_backtest(message, state),
    "demo": lambda message, state, user_id: trading.cmd_demo_core(message, state, user_id),
    "trade": lambda message, state, user_id: trading.cmd_trade_core(message, state, user_id),
    "positions": lambda message, state, user_id: trading.cmd_positions_core(message, user_id),
    "resume": lambda message, state, user_id: trading.cmd_resume_core(message, user_id),
    "stop": lambda message, state, user_id: trading.cmd_stop_core(message, user_id),
    "news": lambda message, state, user_id: news.cmd_news(message, state),
    "strategies": lambda message, state, user_id: strategies.cmd_strategies(message),
}


@router.callback_query(F.data.startswith("menu:"))
async def menu_action(callback: CallbackQuery, state: FSMContext) -> None:
    action = callback.data.split(":", 1)[1]
    await callback.answer()
    if action == "open":
        await _show_menu(callback.message)
        return
    handler = _ROUTES.get(action)
    if handler is not None:
        await handler(callback.message, state, callback.from_user.id)
