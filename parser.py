import asyncio
import sys
from datetime import datetime, timedelta
import os, re

import traceback

import difflib as dif
import time

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

#from utils.central_module import convert_to_list, get_local_ip, send_msg
from utils.db_loader import read_data_from_db, update_data_in_db
from models.mdl_tables import Session

current_path = os.path.dirname(os.path.dirname(__file__))
#csv_path = os.path.join(current_path, "channel_list.csv")
dotenv_path = os.path.join(current_path, ".env")

load_dotenv(dotenv_path)


# admin_id = os.environ.get("admin_id")
# api_token = os.environ.get("api_token")
# # api_id = os.environ.get("api_id")
# # api_hash = os.environ.get('api_hash')
# # session_string = os.environ.get('session_string')
# username = os.environ.get("username")
#
# time_now = time.time()
# current_date_str = datetime.now().strftime("%d.%m.%Y")
#
# timer_sleeper = 8 * 3600

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
    status, session_df = await read_data_from_db(Session, 100, 1)

    for session in session_df:
        if session.session == None:
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















    session_df = await read_table_id(service, SS_ID, 'sessions')
    print(session_df)

    if session_df.empty:
        txt_error = f"! Не получены данные сессий, проблема с GS."
        print(txt_error)
        await send_msg(api_token, admin_id, txt_error)
        sys.exit(0)

    session_df = session_df[session_df['host'] == local_ip]
    if session_df.empty:
        txt_error = f"!! На данном хосте не указаны сессии. {local_ip}"
        print(txt_error)
        await send_msg(api_token, admin_id, txt_error)
        sys.exit(0)

    session_df['block_time'] = session_df['block_time'].astype(int)
    session_df = session_df[session_df['block_time'] < time_now]

    if session_df.empty:
        txt_error = f"!!! Все сессии во временном бане. {local_ip}"
        print(txt_error)
        await send_msg(api_token, admin_id, txt_error)
        sys.exit(0)

    session_strings = session_df.to_dict('list')
    len_ses = len(session_strings[next(iter(session_strings))])
    print(f"- len_ses: {len_ses}")

    # Получаем список пользователей
    df = await read_table_id(service, SS_ID, 'sets')
    print(df)

    # Получаем список каналов
    CHAN_df = await read_table_id(service, SS_ID, 'channel_list')
    CHANNELS_df = CHAN_df[CHAN_df['host'] == local_ip]
    CHANNELS_df = CHANNELS_df[CHANNELS_df['pars_date'] != current_date_str]
    CHANNELS = CHANNELS_df['channels'].tolist()
    random.shuffle(CHANNELS)

    len_df = len(CHANNELS)
    print("len_df:", len_df)
    if len_df == 0:
        sys.exit(0)

    rnd_rime = int(timer_sleeper / len_df)
    print('rnd_rime:', rnd_rime)

    msgs_df = await read_table_id(service, SS_ID, 'bot_msg')

    comments = []

    for _idx_, channel in enumerate(CHANNELS):
        if _idx_ == 6: #опрашивать 7 каналов за раз.
            return

        idx_ch = CHAN_df[CHAN_df['channels'] == channel].index[0]

        errors = False
        num_ch = CHANNELS.index(channel)
        as_sl = random.randint(120, 200)
        print(
            f"\n- Channel #{num_ch}: Получение новых сообщений из канала @{channel} (ожидание до {as_sl})"
        )

        if len_ses == 1:
            idx_ses = 0
        else:
            idx_ses = random.randint(0, len_ses - 1)

        bot_name = session_strings['bot_name'][idx_ses]
        api_id = session_strings['api_id'][idx_ses]
        api_hash = session_strings['api_hash'][idx_ses]
        session_string = session_strings['session_string'][idx_ses]
        number_phone = session_strings['number_phone'][idx_ses]
        #print(api_id, number_phone)

        tag = str(api_id)[:3]

        try:
            async with Client(
                name=bot_name,
                api_id=api_id,
                api_hash=api_hash,
                session_string=session_string,
                in_memory=True,
            ) as client:

                print(f"\nConnect {tag}: -------------------> {time.ctime()}")
                try:

                    msgs_df['unix_date'] = msgs_df['unix_date'].astype(int)
                    msgs_df = msgs_df[msgs_df['unix_date'] + (30 * 24 * 3600) > time_now]

                    if len(msgs_df) != 0:
                        msgs = msgs_df['message'].tolist()

                    else:
                        msgs = []

                    # Получаем последние 10 сообщений
                    # messages = client.get_chat_history(chat_id=chat.id, limit=10)

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
                    async for message in client.get_chat_history(chat_id=chat.id, limit=20):
                        message_date = message.date
                        msg_dates.append(message_date)
                        current_date = datetime.now()
                        week_ago = current_date - timedelta(days=7)

                        if message_date < week_ago:
                            # Сообщение старше недели, пропускаем его
                            continue

                        formatted_date = message_date.strftime("%d.%m.%Y %H:%M:%S")
                        message_id = message.id
                        link_msg = f"{base_url}{channel}/{message_id}"
                        msg = message.text

                        if msg is None:
                            print(f"--- Сообщение {msg}, пропускаем его\n{link_msg}")
                            continue

                        #msg_hash = await hash_and_compare(msg)

                        if msg in msgs:
                            print("--- Такое сообщение уже есть в базе, пропускаем его")
                            continue

                        unix_date = str(int(time.time()))

                        for idx, row in df.iterrows():
                            chat_id = row["user_id"]
                            try:
                                white_list_any = await convert_to_list(row["white_list_any"])
                            except:
                                white_list_any = []

                            try:
                                white_list_all = await convert_to_list(row["white_list_all"])
                            except:
                                white_list_all = []

                            try:
                                black_list_any = await convert_to_list(row["black_list_any"])
                            except:
                                black_list_any = []

                            try:
                                black_list_all = await convert_to_list(row["black_list_all"])
                            except:
                                black_list_all = []

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

                            wlan = (
                                True
                                if not white_list_any
                                else any(
                                    white.lower() in msg.lower() for white in white_list_any
                                )
                            )
                            wlal = (
                                True
                                if not white_list_all
                                else all(
                                    white.lower() in msg.lower() for white in white_list_all
                                )
                            )
                            blan = (
                                True
                                if not black_list_any
                                else any(
                                    black.lower() not in msg.lower()
                                    for black in black_list_any
                                )
                            )
                            blal = (
                                True
                                if not black_list_all
                                else all(
                                    black.lower() not in msg.lower()
                                    for black in black_list_all
                                )
                            )

                            if wlan and wlal and blan and blal:
                                print(f"+++++++++++++RESEND=POST+{chat_id}+++++++++++++")

                                #order = moderator(msg)

                                # channel_text = channel.replace("_", r"\_")
                                text = f"Link: {base_url}{channel}/{message_id}\nDate: {formatted_date} ({tag})\n\n{msg}"
                                try:
                                    await send_msg(api_token, chat_id, text)

                                except Exception as e:
                                    print(f"Error Chat_ID: {chat_id}")
                                    if (
                                        "Telegram server says - Forbidden: bot was blocked by the user"
                                        in str(e)
                                    ):

                                        columns_block = ["white_list_any",
                                                         "white_list_all",
                                                         "black_list_any",
                                                         "black_list_all"]

                                        datas_block = ['bot was blocked by the user'] * 4

                                        idx_user = df[df['user_id'] == chat_id].index[0]
                                        await append_data_to_sheet_cells(service,
                                                                         SS_ID,
                                                                         'sets',
                                                                         columns_block,
                                                                         idx_user + 2,
                                                                         datas_block)
                                        continue

                                await asyncio.sleep(5)

                                data_list = {"unix_date": unix_date,
                                             "channel": channel,
                                             "message_id": message_id}
                                await append_data_to_sheet_scope(service, SS_ID, 'channel_stat', data_list)

                                data_list2 = {"unix_date": unix_date,
                                              "message": msg}

                                if msg in comments:
                                    continue

                                else:
                                    await append_data_to_sheet_scope(service, SS_ID, "bot_msg", data_list2)
                                    comments.append(msg)

                                print(f"+++ Double Commit! {time.ctime()}")

                            else:
                                print(
                                    f"--- {chat_id} No match {base_url}{channel}/{message_id}, next..."
                                )

                        now = datetime.now().hour
                        if now == 1:
                            #await delete_data_pars()
                            print("--- Delete Commits!")


                    if len(msg_dates) == 0:
                        columns = ["last_date", "pars_date", "host", "status"]
                        datas = ["None", current_date_str, "None", "No msg"]

                        await append_data_to_sheet_cells(service,
                                                         SS_ID,
                                                         'channel_list',
                                                         columns,
                                                         idx_ch + 2,
                                                         datas)

                        continue

                    record_date = max(msg_dates).strftime("%Y.%m.%d")
                    columns = ["last_date", "pars_date"]
                    datas = [record_date, current_date_str]

                    await append_data_to_sheet_cells(service,
                                                    SS_ID,
                                                    'channel_list',
                                                     columns,
                                                     idx_ch + 2,
                                                     datas)

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
