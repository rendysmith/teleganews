import asyncio
import sys
from datetime import datetime, timedelta, date
import os, re

import traceback

import difflib as dif
import time

from sqlalchemy import or_

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


from utils.db_loader import read_data_from_db_filter_limit_universal
from models.mdl_tables import Session, Channels

current_path = os.path.dirname(os.path.dirname(__file__))
#csv_path = os.path.join(current_path, "channel_list.csv")
dotenv_path = os.path.join(current_path, ".env")

load_dotenv(dotenv_path)

def diff(a, b):
    s = dif.SequenceMatcher(None, a, b)
    return s.ratio()

async def get_df(service):
    df = await read_table_id(service, SS_ID,'channel_list')
    print(df)
    channels = df["channels"].to_list()
    return list(set(channels))

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
                            txt = f"-- Error 420: {api_id} {number_phone}\n{str(fw)}"
                            traceback.print_exc()
                            errors = True

                        except UserAlreadyParticipant:
                            chat = await client.get_chat(channel)

                    else:
                        base_url = 'https://t.me/'
                        chat = await client.get_chat(channel)

                    # Выводим текст последних сообщений
                    msg_dates = []
                    async for message in client.get_chat_history(chat_id=chat.id, limit=100):
                        message_date = message.date
                        current_date = datetime.now()
                        week_ago = current_date - timedelta(days=30)

                        if message_date < week_ago:
                            print('msg > 30 дней')
                            continue

                        message_id = message.id
                        msg = message.text if message.text is not None else message.caption






                except PeerIdInvalid as pe:
                    txt = f"-- Error 400: {api_id} {number_phone}\n{str(pe)}\nchannel: @{channel}"
                    await append_data_to_sheet_cell(service,
                                                    SS_ID,
                                                    'channel_list',
                                                    'status',
                                                    idx_ch + 2,
                                                    str(pe))
                    traceback.print_exc()
                    errors = True

                except UsernameNotOccupied as uno:
                    txt = f"-- Error 400: {api_id} {number_phone}\n{str(uno)}\nchannel: @{channel}"
                    await append_data_to_sheet_cell(service,
                                                    SS_ID,
                                                    'channel_list',
                                                    'status',
                                                    idx_ch + 2,
                                                    str(uno))
                    traceback.print_exc()
                    errors = True

                except UsernameInvalid as ui:
                    txt = f"-- Error 400: {api_id} {number_phone}\n{str(ui)}\nchannel: @{channel}"
                    await append_data_to_sheet_cell(service,
                                                    SS_ID,
                                                    'channel_list',
                                                    'status',
                                                    idx_ch + 2,
                                                    str(ui))
                    traceback.print_exc()
                    errors = True

                except InviteHashExpired as ie:
                    txt = f"-- Error 400: {api_id} {number_phone}\n{str(ui)}\nchannel: @{channel}"
                    await append_data_to_sheet_cell(service,
                                                    SS_ID,
                                                    'channel_list',
                                                    'status',
                                                    idx_ch + 2,
                                                    str(ie))
                    traceback.print_exc()
                    errors = True

                except FloodTestPhoneWait as fe:
                    txt = f"-- Error 420: {api_id} {number_phone}\n{str(fe)}"
                    traceback.print_exc()
                    errors = True

                except FloodWait as fw:
                    txt = f"-- Error 420: {api_id} {number_phone}\n{str(fw)}"
                    traceback.print_exc()
                    errors = True

                except Exception as e:
                    txt_error = traceback.format_exc()
                    txt = (
                        f"-- Ошибка при получении сообщений API_ID {api_id} {number_phone}\n"
                        f"-- {str(e)}\n"
                        f"-- {txt_error}"
                    )

                    print(txt)
                    traceback.print_exc()
                    errors = True

                finally:
                    if errors:
                        await send_msg(api_token, admin_id, txt)
                        wait_seconds = extract_flood_wait_seconds(txt)

                        if wait_seconds is not None:
                            txt_error = f"!!! Временный бан, время ожидания: {wait_seconds} с."
                            await send_msg(api_token, admin_id, txt_error)

                            idx_api = session_df[session_df['api_id'] == api_id].index[0]
                            await append_data_to_sheet_cell(service,
                                                            SS_ID,
                                                            'sessions',
                                                            'block_time',
                                                            idx_api + 2,
                                                            time.time() + wait_seconds)

                            return

                        else:
                            print("Число не найдено в тексте.")

                await asyncio.sleep(as_sl)

        except FloodWait as fw:
            await send_msg(api_token, admin_id, fw)
            wait_seconds = extract_flood_wait_seconds(fw)

            if wait_seconds is not None:
                txt_error = f"!!! Временный бан, время ожидания: {wait_seconds} с."
                await send_msg(api_token, admin_id, txt_error)
                idx_api = session_df[session_df['api_id'] == api_id].index[0]
                await append_data_to_sheet_cell(service,
                                                SS_ID,
                                                'sessions',
                                                'block_time',
                                                idx_api + 2,
                                                time.time() + wait_seconds)

                sys.exit(0)

    return

async def tststs():
    # Получаем список пользователей
    service = await get_service()
    df = await read_table_id(service, SS_ID, 'sets')
    print(df)

    msg = "python test"

    for idx, row in df.iterrows():
        print('\n---------------------------------------------')
        chat_id = row["user_id"]
        print(chat_id)

        print(row["white_list_any"])

        white_list_any = await convert_to_list(row["white_list_any"])
        white_list_all = await convert_to_list(row["white_list_all"])
        black_list_any = await convert_to_list(row["black_list_any"])
        black_list_all = await convert_to_list(row["black_list_all"])

        if (
                not white_list_any and
                not white_list_all and
                not black_list_any and
                not black_list_all
        ):
            print(
                f"--- {chat_id} Поисковые настройки пустые! Пропускаем пользователя."
            )
            continue

        if white_list_any:
            print(white_list_any)

        wlan = True if not white_list_any else any(white.lower() in msg.lower() for white in white_list_any)
        print(wlan)

        wlal = True if not white_list_all else any(white.lower() in msg.lower() for white in white_list_all)
        print(wlal)

        blan = True if not black_list_any else all(black.lower() not in msg.lower() for black in black_list_any)
        print(blan)

        blal = True if not black_list_all else all(black.lower() not in msg.lower() for black in black_list_all)
        print(blal)

        if wlan and wlal and blan and blal:
            print(f"+++++++++++++RESEND=POST+{chat_id}+++++++++++++")
            #await send_msg(api_token, chat_id, msg)

        else:
            print('SKIP')



if "__main__" in __name__:
    #asyncio.run(tststs())

    asyncio.run(get_parser_data())
