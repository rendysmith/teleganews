import asyncio
import sys
from datetime import datetime, timedelta, date
import os, re

import traceback

import difflib as dif
import time

from selenium.webdriver.common.devtools.v139.runtime import await_promise
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


from utils.db_loader import read_data_from_db_filter_limit_universal, add_data_to_db_universal
from models.mdl_tables import Session, Channels, History

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
    time_now = time.time()
    date_now = date.today()
    is_docker = os.path.exists("/.dockerenv")
    print(is_docker)

    filters = Session.block_time < time_now #если временная блокировка акка
    status, session_df = await read_data_from_db_filter_limit_universal('sessions', 100, 1, filters)
    print(status)
    print(session_df)

    sessionS = []
    for session in session_df:
        if session.session == None:
            if is_docker:
                continue  # пропускаем в Docker

            else:
                api_id = session.api_id
                api_hash = session.api_hash
                session_string = await get_session(api_id, api_hash)
                print(session_string)

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
        if _idx_ == 6: #опрашивать 7 каналов за раз.
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

                        except FloodWait:
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
                            continue

                        message_id = message.id
                        msg = message.text if message.text is not None else message.caption

                        #print(f'MSG = {msg}')
                        if msg is None:
                            continue

                        filters3 = and_(History.channel == channel,
                                       History.message_id == message_id)

                        status3, result3 = await read_data_from_db_filter_limit_universal('history', 1, 1, filters3)
                        print(status3)
                        print(f"result3 = {result3}")

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
                        print("status4:", status4)
                        print("result4:", result4)

                        await asyncio.sleep(1)

                except Exception as Ex1:
                    print(f'Error1: {Ex1}')



        except Exception as Ex2:
            print(f'Error2: {Ex2}')
            await asyncio.sleep(5)












    #
    #
    #
    #             except PeerIdInvalid as pe:
    #                 txt = f"-- Error 400: {api_id}\n{str(pe)}\nchannel: @{channel}"
    #                 await append_data_to_sheet_cell(service,
    #                                                 SS_ID,
    #                                                 'channel_list',
    #                                                 'status',
    #                                                 idx_ch + 2,
    #                                                 str(pe))
    #                 traceback.print_exc()
    #                 errors = True
    #
    #             except UsernameNotOccupied as uno:
    #                 txt = f"-- Error 400: {api_id} {number_phone}\n{str(uno)}\nchannel: @{channel}"
    #                 await append_data_to_sheet_cell(service,
    #                                                 SS_ID,
    #                                                 'channel_list',
    #                                                 'status',
    #                                                 idx_ch + 2,
    #                                                 str(uno))
    #                 traceback.print_exc()
    #                 errors = True
    #
    #             except UsernameInvalid as ui:
    #                 txt = f"-- Error 400: {api_id} {number_phone}\n{str(ui)}\nchannel: @{channel}"
    #                 await append_data_to_sheet_cell(service,
    #                                                 SS_ID,
    #                                                 'channel_list',
    #                                                 'status',
    #                                                 idx_ch + 2,
    #                                                 str(ui))
    #                 traceback.print_exc()
    #                 errors = True
    #
    #             except InviteHashExpired as ie:
    #                 txt = f"-- Error 400: {api_id} {number_phone}\n{str(ui)}\nchannel: @{channel}"
    #                 await append_data_to_sheet_cell(service,
    #                                                 SS_ID,
    #                                                 'channel_list',
    #                                                 'status',
    #                                                 idx_ch + 2,
    #                                                 str(ie))
    #                 traceback.print_exc()
    #                 errors = True
    #
    #             except FloodTestPhoneWait as fe:
    #                 txt = f"-- Error 420: {api_id} {number_phone}\n{str(fe)}"
    #                 traceback.print_exc()
    #                 errors = True
    #
    #             except FloodWait as fw:
    #                 txt = f"-- Error 420: {api_id} {number_phone}\n{str(fw)}"
    #                 traceback.print_exc()
    #                 errors = True
    #
    #             except Exception as e:
    #                 txt_error = traceback.format_exc()
    #                 txt = (
    #                     f"-- Ошибка при получении сообщений API_ID {api_id} {number_phone}\n"
    #                     f"-- {str(e)}\n"
    #                     f"-- {txt_error}"
    #                 )
    #
    #                 print(txt)
    #                 traceback.print_exc()
    #                 errors = True
    #
    #             finally:
    #                 if errors:
    #                     await send_msg(api_token, admin_id, txt)
    #                     wait_seconds = extract_flood_wait_seconds(txt)
    #
    #                     if wait_seconds is not None:
    #                         txt_error = f"!!! Временный бан, время ожидания: {wait_seconds} с."
    #                         await send_msg(api_token, admin_id, txt_error)
    #
    #                         idx_api = session_df[session_df['api_id'] == api_id].index[0]
    #                         await append_data_to_sheet_cell(service,
    #                                                         SS_ID,
    #                                                         'sessions',
    #                                                         'block_time',
    #                                                         idx_api + 2,
    #                                                         time.time() + wait_seconds)
    #
    #                         return
    #
    #                     else:
    #                         print("Число не найдено в тексте.")
    #
    #             await asyncio.sleep(as_sl)
    #
    #     except FloodWait as fw:
    #         await send_msg(api_token, admin_id, fw)
    #         wait_seconds = extract_flood_wait_seconds(fw)
    #
    #         if wait_seconds is not None:
    #             txt_error = f"!!! Временный бан, время ожидания: {wait_seconds} с."
    #             await send_msg(api_token, admin_id, txt_error)
    #             idx_api = session_df[session_df['api_id'] == api_id].index[0]
    #             await append_data_to_sheet_cell(service,
    #                                             SS_ID,
    #                                             'sessions',
    #                                             'block_time',
    #                                             idx_api + 2,
    #                                             time.time() + wait_seconds)
    #
    #             sys.exit(0)
    #
    # return

if "__main__" in __name__:
    #asyncio.run(tststs())

    asyncio.run(get_parser_data())
