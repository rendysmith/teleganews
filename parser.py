import os

# =====================================================================
# КРИТИЧЕСКИ ВАЖНО: Отключаем интернет для модели HuggingFace,
# чтобы она не зависала на 15 секунд при проверке обновлений!
os.environ['HF_HUB_OFFLINE'] = '1'
# =====================================================================

import asyncio
import logging
import sys
import traceback
import time
import random
from datetime import datetime, timedelta, date
from types import SimpleNamespace

from sqlalchemy import or_
from pyrogram import Client
from pyrogram.errors.exceptions.bad_request_400 import UserAlreadyParticipant
from pyrogram.errors.exceptions.flood_420 import FloodWait
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

from database.db_loader import (
    read_data_from_db_filter_limit_universal,
    add_data_to_db_universal,
    update_data_from_db_universal,
    delete_data_to_db_universal,
    ensure_history_unique_constraint,
)
from models.mdl_tables import Session, Channels

# Настройка логирования (чтобы видеть output в логах Docker)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger("ParserWorker")

current_path = os.path.dirname(os.path.dirname(__file__))
dotenv_path = os.path.join(current_path, ".env")
load_dotenv(dotenv_path)

logger.info("Загрузка локальной модели HuggingFace...")
local_model = SentenceTransformer('cointegrated/rubert-tiny2')


def _encode_text(text: str) -> list[float]:
    """Синхронная функция векторизации"""
    text = text.replace("\n", " ")
    return local_model.encode(text).tolist()


async def get_embedding(text):
    """Асинхронная обертка для создания эмбеддинга"""
    try:
        # Выносим тяжелую математику в отдельный поток, чтобы не вешать Pyrogram
        return await asyncio.to_thread(_encode_text, text)
    except Exception as e:
        logger.error(f"Ошибка при создании локального эмбеддинга: {e}")
        return None


async def get_session(api_id, api_hash):
    bot_name = os.environ.get("BOT_NAME", "my_bot")
    async with Client(name=bot_name, api_id=api_id, api_hash=api_hash) as client:
        session_string = await client.export_session_string()
        return session_string


async def get_parser_data():
    logger.info("▶ Start parsing iteration...")
    time_now = time.time()
    date_now = date.today()

    is_docker = os.path.exists("/.dockerenv")

    # 1. Получаем сессии
    filters = Session.block_time < time_now
    status, session_df = await read_data_from_db_filter_limit_universal('sessions', 100, 1, filters)

    sessions_list = []
    for session in session_df:
        if not session.session:
            if is_docker:
                continue  # пропускаем генерацию сессии внутри Docker
            else:
                api_id = session.api_id
                api_hash = session.api_hash
                session_string = await get_session(api_id, api_hash)

                update_data = SimpleNamespace(
                    table_name="sessions",
                    filter_column="api_id",
                    filter_value=api_id,
                    column="session",
                    new_data=session_string
                )
                await update_data_from_db_universal(update_data)
        else:
            sessions_list.append(session)

    if not sessions_list:
        logger.error("!!! Нет доступных сессий (или все во временном бане).")
        return

    # 2. Получаем каналы
    filters2 = or_(Channels.last_checked_at != date_now, Channels.last_checked_at.is_(None))
    status, channels_list = await read_data_from_db_filter_limit_universal('channels', 100, 1, filters2)

    if not channels_list:
        logger.info("Нет каналов для проверки (или все уже проверены сегодня).")
        return

    # Превращаем в список и перемешиваем
    channels_list = list(channels_list)
    random.shuffle(channels_list)

    # 3. Начинаем парсинг
    for _idx_, channel_data in enumerate(channels_list):
        if _idx_ >= 7:  # Опрашивать не более 7 каналов за одну итерацию
            logger.info("Batch limit reached (7 channels). Finishing job.")
            return

        channel = channel_data.channel
        idx_ses = random.randrange(0, len(sessions_list))

        bot_name = sessions_list[idx_ses].user_name
        api_id = sessions_list[idx_ses].api_id
        api_hash = sessions_list[idx_ses].api_hash
        session_string = sessions_list[idx_ses].session

        try:
            async with Client(
                    name=bot_name,
                    api_id=api_id,
                    api_hash=api_hash,
                    session_string=session_string,
                    in_memory=True,
            ) as client:

                logger.info(f"\nConnect {bot_name}: --------- https://t.me/{channel} ----------> {time.ctime()}")

                try:
                    if 't.me/+' in channel:
                        try:
                            chat = await client.join_chat(channel)
                        except FloodWait as fw:
                            logger.warning(f"-- Error 420 (FloodWait): {api_id}\n{str(fw)}")
                            continue
                        except UserAlreadyParticipant:
                            chat = await client.get_chat(channel)
                    else:
                        chat = await client.get_chat(channel)

                    # ПАРСИМ ИСТОРИЮ
                    async for message in client.get_chat_history(chat_id=chat.id, limit=100):
                        message_date = message.date
                        week_ago = datetime.now() - timedelta(days=30)

                        if message_date < week_ago:
                            logger.info(f'Дошли до старых сообщений (> 30 дней) в канале {channel}. Стоп.')
                            break

                        message_id = message.id
                        msg = message.text if message.text else message.caption

                        if not msg:
                            continue

                        # Получаем эмбеддинг
                        msg_emb = await get_embedding(msg)

                        # ЗАЩИТА ОТ NULL ВЕКТОРОВ В БД!
                        if msg_emb is None:
                            logger.warning(f"Пропуск сообщения {message_id}: ошибка генерации вектора")
                            continue

                        rec_datas = SimpleNamespace(
                            table_name='history',
                            datas={
                                'date': message_date,
                                'channel': channel,
                                'message_id': message_id,
                                'message': msg,
                                'message_emb': msg_emb
                            }
                        )

                        # База сама отсечет дубли (UniqueConstraint) и вернет 'Дубликат проигнорирован'
                        status4, result4 = await add_data_to_db_universal(rec_datas)

                        # Выводим в лог только если это реально новое сообщение
                        if status4 and "Дубликат" not in result4:
                            logger.info(f"Добавлено новое сообщение {message_id}")

                        await asyncio.sleep(1)  # Не спамим Телеграм API

                except Exception as Ex1:
                    logger.warning(f'Ошибка обработки канала {channel}: {Ex1}')

            # 4. Обновляем статус канала (проверено сегодня)
            update_data = SimpleNamespace(
                table_name="channels",
                column="last_checked_at",
                filter_column="channel",
                filter_value=channel,
                new_data=date_now
            )
            status5, result5 = await update_data_from_db_universal(update_data)
            logger.info(f"Обновлена дата проверки для {channel}: {status5} {result5}")

        except Exception as Ex2:
            logger.error(f'Ошибка сессии {bot_name}: {Ex2}')
            await asyncio.sleep(5)

    # 5. Очистка старых данных из БД (старше 60 дней)
    delete_datas = SimpleNamespace(
        table_name='history',
        datas={'days': 60}
    )
    status6, result6 = await delete_data_to_db_universal(delete_datas)
    logger.info(f"Очистка старых записей (2 месяца): {status6} {result6}")


async def main():
    logger.info("Запуск контейнера парсера...")

    await ensure_history_unique_constraint()

    # Инициализируем планировщик
    scheduler = AsyncIOScheduler()
    scheduler.add_job(get_parser_data, "interval", hours=1)
    scheduler.start()
    logger.info("Планировщик запущен. Ожидание задач...")

    logger.info("Выполняю первичный запуск при старте...")
    await get_parser_data()

    # Бесконечное ожидание
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка парсера...")