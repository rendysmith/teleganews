# bot.py
import asyncio
import logging
import os

import pandas as pd

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, CallbackQuery
from aiogram import F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from dotenv import load_dotenv

from utils.gs_editor import read_table_id, get_service

load_dotenv()

logging.basicConfig(level=logging.INFO)

SS_ID = os.getenv("SS_ID")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден. Проверьте файл .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

async def translation(df):
    translations = {
        row['command']: {
            'RU': row['RU'],
            'EN': row['EN']
        }
        for _, row in df.iterrows()
    }

    return translations



@router.message(CommandStart())
async def handle_start(message: types.Message, state: FSMContext):
    service = await get_service()
    df = await read_table_id(service, SS_ID, 'settings')
    df = df[df['command'] != ""]
    print(df)

    await state.update_data(settings=await translation(df))

    language_idx = df[df['command'] == 'language'].index[0]
    row = df.loc[language_idx].to_list()
    print(row)

    list_ILKB = []

    for i in row[1:]:
        list_ILKB.append(types.InlineKeyboardButton(text=i, callback_data=f"choice:{i}"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        list_ILKB
    ])
    await message.answer("Select a language?", reply_markup=keyboard)


@router.callback_query(F.data.startswith("choice:"))
async def handle_choice(callback: CallbackQuery, state: FSMContext):
    language = callback.data.split(":")[1]

    await state.update_data(language=language)

    data = await state.get_data()  # получаем всё
    print(data)

    text = data['settings']['welcome'][language]
    await callback.message.edit_text(text)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        list_ILKB
    ])
    await message.answer("Select a language?", reply_markup=keyboard)




dp.include_router(router)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())