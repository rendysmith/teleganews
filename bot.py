# bot.py
import asyncio
import logging
import os
import time

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, CallbackQuery
from dotenv import load_dotenv

from utils.db_loader import read_data_from_db
from models.mdl_tables import Topics

load_dotenv()

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден. Проверьте файл .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

@router.message(CommandStart())
async def handle_start(message: types.Message):
    #user_id = message.from_user.id
    # status, users_ids = await read_data_from_db('white_list_users', 100, 1)
    # user_lists = [i.user_id for i in users_ids]
    # if user_id not in user_lists:
    #     await message.answer("Ваш доступ ограничен. Обратитесь к администратору.")

    status, topics = await read_data_from_db(Topics, 100, 1)
    topic_lists = [i.topic for i in topics]

    inline_keyboard = []

    for topic in topic_lists:
        inline_keyboard.append([types.InlineKeyboardButton(text=topic, callback_data=f"topic:{topic}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    await message.answer("Выбери тему:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("topic:"))
async def handle_choice_topic(callback: CallbackQuery, state: FSMContext):
    topic = callback.data.split(":")[1]
    print(topic)

    await state.update_data(topic=topic)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text='за 14 дней', callback_data=f"days:14")],
        [types.InlineKeyboardButton(text='за 30 дней', callback_data=f"days:30")]
    ])

    await callback.message.answer('Кол-во дней истории:', reply_markup=keyboard)

@router.callback_query(F.data.startswith("days:"))
async def handle_choice_topic(callback: CallbackQuery, state: FSMContext):
    days = int(callback.data.split(":")[1])
    print(days)

    data = await state.get_data()  # получаем всё
    print(data)
    topic = data['topic']

    start_time = time.time() - (days * 24 * 3600)
    await callback.message.answer(f'Тема: {topic} за последние {days} дней.')






dp.include_router(router)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())