import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from news_fetcher import get_news_and_analyze
from db import init_db, get_api_key, save_api_key

# Токен вашего бота от @BotFather
TELEGRAM_TOKEN = '7037507472:AAFB_JU964RA79QUCiL_-1McLw8G6cIXbZg'

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()


# Определение состояний для FSM (Finite State Machine)
class NewsStates(StatesGroup):
    waiting_for_company = State()


# Обработчик команды /start
@dp.message(Command("start"))
async def start_command(message: Message):
    await message.answer("Привет! Отправь мне свой API-ключ Tinkoff Инвестиций для начала работы.")


# Обработчик для сохранения API-ключа
@dp.message(lambda message: not message.text.startswith('/'), state=None)
async def save_key(message: Message, state: FSMContext):
    user_id = message.from_user.id
    api_key = message.text.strip()
    save_api_key(user_id, api_key)
    await message.answer("API-ключ сохранён! Используй команду /news для анализа новостей.")


# Обработчик команды /news
@dp.message(Command("news"))
async def news_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    api_key = get_api_key(user_id)

    if not api_key:
        await message.answer("Сначала отправь мне свой API-ключ Tinkoff Инвестиций!")
        return

    args = message.text.split()[1:]  # Убираем /news и берём аргументы
    if args:
        company = args[0]
        await show_period_buttons(message, company)
    else:
        await message.answer("Введи название компании (например, ВК или SBER):")
        await state.set_state(NewsStates.waiting_for_company)


# Обработчик ввода компании
@dp.message(NewsStates.waiting_for_company)
async def process_company(message: Message, state: FSMContext):
    company = message.text.strip()
    await show_period_buttons(message, company)
    await state.clear()  # Завершаем состояние


# Функция для отображения кнопок выбора периода
async def show_period_buttons(message: Message, company: str):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 день", callback_data=f"news_{company}_1")],
        [InlineKeyboardButton(text="7 дней", callback_data=f"news_{company}_7")],
        [InlineKeyboardButton(text="30 дней", callback_data=f"news_{company}_30")],
    ])
    await message.answer(f"Выбери период для новостей по {company}:", reply_markup=keyboard)


# Обработчик нажатия кнопок
@dp.callback_query(lambda c: c.data.startswith("news_"))
async def process_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data.split("_")
    company = data[1]
    days = int(data[2])

    # Получение и анализ новостей
    result = get_news_and_analyze(company, days)
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(user_id, f"Новости по {company} за {days} дней:\n{result}")


# Запуск бота
async def main():
    init_db()  # Инициализация базы данных
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())