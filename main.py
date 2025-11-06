# bot.py
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import CommandStart
from dotenv import load_dotenv

from utils.db_loader import read_data_from_db

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

    status, users_ids = await read_data_from_db('white_list_users', 100, 1)



    user_lists = [i.user_id for i in users_ids]


    if user_id not in user_lists:
        await message.answer("Ваш доступ ограничен. Обратитесь к администратору.")



dp.include_router(router)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())