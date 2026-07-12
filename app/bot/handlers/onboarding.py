from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards import persistent_menu_keyboard
from app.bot.states import TokenStates
from app.db.models import TradingMode
from app.db.repository import get_or_create_user, save_broker_credential
from app.db.session import get_session

router = Router(name="onboarding")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    async with get_session() as session:
        await get_or_create_user(session, message.from_user.id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Настроить demo-токен (Sandbox)", callback_data="set_token:sandbox")],
            [InlineKeyboardButton(text="Настроить боевой токен (Production)", callback_data="set_token:production")],
        ]
    )
    await message.answer(
        "Привет! Это торговый бот для Т-Инвестиций.\n\n"
        "Сначала подключите токен. Рекомендую начать с demo (Sandbox) — виртуальные деньги "
        "на реальных котировках, чтобы спокойно проверить стратегию перед реальными деньгами.",
        reply_markup=keyboard,
    )
    await message.answer(
        "Кнопка «☰ Меню» снизу всегда открывает список действий — не нужно помнить команды.",
        reply_markup=persistent_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("set_token:"))
async def choose_token_mode(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.split(":", 1)[1]
    await state.update_data(mode=mode)
    await state.set_state(TokenStates.waiting_for_token)
    await callback.answer()
    label = "Sandbox (demo)" if mode == "sandbox" else "Production (боевой)"
    await callback.message.answer(
        f"Пришлите токен Т-Инвестиций для режима {label}.\n"
        "Получить его можно в приложении Т-Инвестиции: Настройки → Токены.\n"
        "Сообщение с токеном будет удалено из чата сразу после сохранения."
    )


@router.message(TokenStates.waiting_for_token)
async def save_token(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    mode = TradingMode(data["mode"])
    token = message.text.strip()

    async with get_session() as session:
        await save_broker_credential(session, message.from_user.id, mode, token)

    await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(f"Токен для режима {mode.value} сохранён в зашифрованном виде.")
