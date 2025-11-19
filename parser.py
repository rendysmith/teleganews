import asyncio
import sys
from datetime import datetime, timedelta, date
import os, re

import traceback
import difflib as dif
import time

from sqlalchemy import or_, and_
from pyrogram import Client

from pyrogram.errors.exceptions.bad_request_400 import (
    PeerIdInvalid,
    UsernameNotOccupied,
    UsernameInvalid,
    UserAlreadyParticipant,
    InviteHashExpired)
from pyrogram.errors.exceptions.flood_420 import FloodTestPhoneWait, FloodWait

from dotenv import load_dotenv
import random

from types import SimpleNamespace

import asyncio
import logging
import sys
from apscheduler.schedulers.asyncio import AsyncIOScheduler


from utils.db_loader import (read_data_from_db_filter_limit_universal,
                             add_data_to_db_universal,
                             update_data_from_db_universal,
                             update_universal)

from models.mdl_tables import Session, Channels, History

# Настройка логирования (чтобы видеть output в логах Docker)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("ParserWorker")

current_path = os.path.dirname(os.path.dirname(__file__))
#csv_path = os.path.join(current_path, "channel_list.csv")
dotenv_path = os.path.join(current_path, ".env")

load_dotenv(dotenv_path)

def diff(a, b):
    s = dif.SequenceMatcher(None, a, b)
    return s.ratio()

def extract_flood_wait_seconds(error_message):
    # Используем регулярное выражение для поиска числа в строке
    match = re.search(r"wait of (\d+) seconds", error_message)
    # Если найдено совпадение, возвращаем найденное число, иначе возвращаем None
    return int(match.group(1)) if match else None

async def get_session(api_id, api_hash):
    bot_name = os.environ.get("BOT_NAME")
    async with Client(name=bot_name, api_id=api_id, api_hash=api_hash) as client:
        session_string = await client.export_session_string()
        print(session_string)
        return session_string

async def get_parser_data():
    logger.info("▶ Start parsing iteration...")
    time_now = time.time()
    date_now = date.today()

    is_docker = os.path.exists("/.dockerenv")

    filters = Session.block_time < time_now #если временная блокировка акка
    status, session_df = await read_data_from_db_filter_limit_universal('sessions', 100, 1, filters)

    sessionS = []
    for session in session_df:
        if session.session == None:
            if is_docker:
                continue  # пропускаем в Docker

            else:
                api_id = session.api_id
                api_hash = session.api_hash
                session_string = await get_session(api_id, api_hash)

                filter_params = {
                    'api_id': api_id,
                    'api_hash': api_hash
                }

                update_data = {
                    'session': session_string
                }

                await update_data_in_db(Session, filter_params, update_data)

        else:
            sessionS.append(session)

    if sessionS == []:
        txt_error = f"!!! Все сессии во временном бане."
        print(txt_error)
        return

    filters2 = or_(Channels.last_checked_at != date_now,
                   Channels.last_checked_at.is_(None))

    status, CHANNELS = await read_data_from_db_filter_limit_universal('channels', 100, 1, filters2)
    random.shuffle(CHANNELS)

    len_df = len(CHANNELS)
    print("len_df:", len_df)
    if len_df == 0:
        return

    for _idx_, channel_data in enumerate(CHANNELS):
        if _idx_ >= 7: #опрашивать 7 каналов за раз.
            logger.info("Batch limit reached (7 channels). Finishing job.")
            return

        channel = channel_data.channel

        idx_ses = random.randrange(0, len(sessionS))

        bot_name = sessionS[idx_ses].user_name
        api_id = sessionS[idx_ses].api_id
        api_hash = sessionS[idx_ses].api_hash
        session_string = sessionS[idx_ses].session

        try:
            async with Client(
                name=bot_name,
                api_id=api_id,
                api_hash=api_hash,
                session_string=session_string,
                in_memory=True,
            ) as client:

                print(f"\nConnect {bot_name}: --------- https://t.me/{channel} ----------> {time.ctime()}")
                try:
                    if 't.me/+' in channel:
                        base_url = ''
                        try:
                            chat = await client.join_chat(channel)

                        except FloodWait as fw:
                            txt = f"-- Error 420: {api_id}\n{str(fw)}"
                            traceback.print_exc()
                            errors = True

                        except UserAlreadyParticipant:
                            chat = await client.get_chat(channel)

                    else:
                        base_url = 'https://t.me/'
                        chat = await client.get_chat(channel)

                    new_datas = []
                    async for message in client.get_chat_history(chat_id=chat.id, limit=100):
                        print(f'\n**************{message.id}***************')
                        message_date = message.date
                        print(message_date)
                        current_date = datetime.now()
                        week_ago = current_date - timedelta(days=30)

                        if message_date < week_ago:
                            print('msg > 30 дней')
                            break

                        message_id = message.id
                        msg = message.text if message.text is not None else message.caption

                        #print(f'MSG = {msg}')
                        if msg is None:
                            continue

                        filters3 = and_(History.channel == channel,
                                       History.message_id == message_id)

                        status3, result3 = await read_data_from_db_filter_limit_universal('history', 1, 1, filters3)
                        print(f"3 check data: {status3}")

                        if result3 != []:
                            continue

                        rec_datas = SimpleNamespace(
                            table_name='history',  # имя таблицы
                            datas={
                                'date': message_date,
                                'channel': channel,
                                'message_id': message_id,
                                'message': msg
                            }
                        )

                        status4, result4 = await add_data_to_db_universal(rec_datas)
                        print(f"4 Add new row: {status4} {result4}")

                        await asyncio.sleep(1)

                except Exception as Ex1:
                    print(f'Error1: {Ex1}')

            update_data = SimpleNamespace(
                table_name="channels",
                column="last_checked_at",
                filter_column="channel",
                filter_value=channel,
                new_data=date_now
            )

            status5, result5 = await update_data_from_db_universal(update_data)
            print("5 update last date:", status5, result5)

        except Exception as Ex2:
            print(f'Error2: {Ex2}')
            await asyncio.sleep(5)


# --- ОБЕРТКА ДЛЯ ПЛАНИРОВЩИКА ---
async def main():
    logger.info("Запуск контейнера парсера...")

    # Инициализируем планировщик
    scheduler = AsyncIOScheduler()

    # ---------------- НАСТРОЙКА РАСПИСАНИЯ ----------------
    # Вариант А: Интервал (например, каждые 30 минут)
    scheduler.add_job(get_parser_data, "interval", minutes=30)

    # Вариант Б: Конкретное время (например, каждый день в 09:00)
    # scheduler.add_job(get_parser_data, "cron", hour=9, minute=0)
    # ------------------------------------------------------

    # Запускаем планировщик
    scheduler.start()
    logger.info("Планировщик запущен. Ожидание задач...")

    # (Опционально) Запустить один раз сразу при старте контейнера
    logger.info("Выполняю первичный запуск при старте...")
    await get_parser_data()

    # ВАЖНО: Бесконечное ожидание.
    # Без этого скрипт дойдет до конца файла, завершится, и Docker остановит контейнер.
    try:
        # Эффективный способ "спать вечно", не нагружая процессор
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass



if __name__ == "__main__":
    try:
        # Запускаем асинхронный цикл
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка парсера...")