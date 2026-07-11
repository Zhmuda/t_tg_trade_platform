from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Persistent bottom keyboard so common commands can be tapped instead of typed.
    Stays visible for the whole chat once sent - no need to resend on every message."""
    rows = [
        ["/backtest", "/demo"],
        ["/trade", "/news"],
        ["/positions", "/resume"],
        ["/stop", "/stop_all"],
        ["/strategies"],
    ]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label) for label in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
    )
