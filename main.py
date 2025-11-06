# bot.py
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup
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
    user_id = message.from_user.id

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


@router.callback_query(F.data.startswith("topc:"))
async def handle_choice(callback: CallbackQuery, state: FSMContext):
    language = callback.data.split(":")[1]
    await state.update_data(language=language)

    data = await state.get_data()  # получаем всё
    print(data)

    text = data['settings']['welcome'][language]
    await callback.message.answer(text)

    button_1 = data['settings']['create_guid'][language]
    button_2 = data['settings']['connect_guid'][language]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=button_1, callback_data=f"guid:new")],
        [types.InlineKeyboardButton(text=button_2, callback_data=f"guid:connect")]
    ])

    text_2 = data['settings']['create_or_connect'][language]
    await callback.message.answer(text_2, reply_markup=keyboard)






dp.include_router(router)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())