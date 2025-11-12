# bot.py
import asyncio
import logging
import os
import time
from datetime import datetime, timedelta

import httpx
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, CallbackQuery
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

from utils.db_loader import read_data_from_db_filter_limit_universal
from models.mdl_tables import Topics, History

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

    status, topics = await read_data_from_db_filter_limit_universal('topics', 100, 1)#            read_data_from_db(Topics, 100, 1)
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

    start_time = datetime.now() - timedelta(days=days)
    await callback.message.answer(f'Тема: "{topic}" за последние {days} дней.')

    filters = History.date > start_time
    status, history = await read_data_from_db_filter_limit_universal('history', 100, 1, filters)#            read_data_from_db(Topics, 100, 1)
    short_history = [f"{i.message}\nlink: 'https://t.me/{i.channel}/{i.message_id}'" for i in history]
    #print(short_history)

    prompt = f"""
    Ты опытный копирайтер с многолетним стажем.
    Твоя задача внимательно прочитать сообщения из социальных сетей которые представлены в виде списка
    --------------------НАЧАЛО СООБЩЕНИЙ--------------------------
    {short_history}
    --------------------КОНЕЦ СООБЩЕНИЙ---------------------------
    Далее ты должен найти статьи которые бы касались тематике "{topic}" и сделать следующее.
    - выдать короткие саммари, что случилось и ссылки.
    - Информация не должна дублироваться (хотя бы большая часть).
    
    """

    auth = HTTPBasicAuth('anku@sidorinlab.ru', 'pass')
    url = f"http://109.107.170.211:8000/api/v1/start_generation"
    data = {
        "prompt": prompt
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, json=data, auth=auth)

        if response.status_code == 200:
            result = response.json()['result'][1]
            print(result)
            await callback.message.answer(result)

        else:
            await callback.message.answer(response.status_code)















dp.include_router(router)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())