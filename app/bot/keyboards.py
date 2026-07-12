from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

OPEN_MENU = "☰ Меню"


def persistent_menu_keyboard() -> ReplyKeyboardMarkup:
    """The one thing that's always visible no matter how deep in a flow you are - tap it
    to get back to the main menu instead of remembering/typing a command."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=OPEN_MENU)]],
        resize_keyboard=True,
        is_persistent=True,
    )


def main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📊 Бэктест", callback_data="menu:backtest")],
        [InlineKeyboardButton(text="🟢 Демо-торговля", callback_data="menu:demo")],
        [InlineKeyboardButton(text="💰 Реальная торговля", callback_data="menu:trade")],
        [InlineKeyboardButton(text="📈 Мои позиции", callback_data="menu:positions")],
        [
            InlineKeyboardButton(text="▶️ Возобновить", callback_data="menu:resume"),
            InlineKeyboardButton(text="⏹ Остановить", callback_data="menu:stop"),
        ],
        [InlineKeyboardButton(text="📰 Новости", callback_data="menu:news")],
        [InlineKeyboardButton(text="🧩 Стратегии", callback_data="menu:strategies")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_menu_keyboard(extra_rows: list[list[InlineKeyboardButton]] | None = None) -> InlineKeyboardMarkup:
    """Attach to the terminal message of any flow - the contextual alternative to
    dumping the user back into the flat command menu after every action."""
    rows = list(extra_rows or [])
    rows.append([InlineKeyboardButton(text="🔙 В меню", callback_data="menu:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
