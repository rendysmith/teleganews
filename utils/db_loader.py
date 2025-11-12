import asyncio
from venv import logger

import pandas as pd
from datetime import datetime

from sqlalchemy import text, update, insert, inspect
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import os
from os.path import join, dirname, abspath

from dotenv import load_dotenv

import logging

from models.mdl_tables import Base

# Настройка логирования
logger = logging.getLogger(__name__)

current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
current_path = dirname(abspath(__file__))

dotenv_path = join(dirname(dirname(__file__)), '.env')
#print(dotenv_path)
# print('Размести .env тут', dirname(dirname(__file__)))
load_dotenv(dotenv_path)

def pool_conn():
    host = os.environ.get("POSTGRESQL_HOST")
    port = os.environ.get("POSTGRESQL_PORT")
    database = os.environ.get("POSTGRESQL_DB")
    user = os.environ.get("POSTGRESQL_USERNAME")
    password = os.environ.get("POSTGRESQL_PASSWORD")
    DATABASE_URL = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
    return DATABASE_URL

engine = create_async_engine(
    pool_conn(),
    pool_size=2,  # Максимальное количество постоянных соединений
    max_overflow=5,  # Максимальное количество "лишних" соединений
)

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def read_data_from_db_filter_limit_universal(table_name: str, limit, page, filters=None):
    """
    :param table_name: name of table STR
    :param limit:
    :param page:
    :param filters:
    :return:
    """
    async with SessionLocal() as session:
        try:
            model = None
            for mapper in Base.registry.mappers:
                if mapper.class_.__tablename__ == table_name:
                    model = mapper.class_
                    break

            if not model:
                raise ValueError(f"Table '{table_name}' not found")

            query = select(model).limit(limit).offset((page - 1) * limit)

            if filters is not None:
                query = query.where(filters)

            result = await session.execute(query)
            results = result.scalars().all()
            return True, results

        except Exception as Ex:
            return False, Ex


async def add_data_to_db_universal(datas):
    table_name = datas.table_name
    data_dict = datas.datas

    async with SessionLocal() as session:
        async with session.begin():
            try:
                model = None
                for mapper in Base.registry.mappers:
                    if mapper.class_.__tablename__ == table_name:
                        model = mapper.class_
                        break

                if not model:
                    txt =  f"Таблица {table_name} не найдена"
                    #print(txt)
                    return True, txt

                    # Проверка полей
                for field in data_dict.keys():
                    if not hasattr(model, field):
                        txt = f"Поле {field} не существует в таблице {table_name}"
                        #print(txt)
                        True, txt

                #print("Model:", model)
                _datas_ = model(**data_dict)
                #print("_datas_:", _datas_)

                session.add(_datas_)
                await session.commit()
                return True, 'Данные успешно добавлены в базу данных.'

            except Exception as Ex:
                await session.rollback()
                return False, Ex

async def update_data_from_db_universal(datas):
    table_name = datas.table_name
    column = datas.column
    filter_column = datas.filter_column  # добавляем фильтр-колонку (например channel)
    filter_value = datas.filter_value    # и её значение
    new_data = datas.new_data

    async with SessionLocal() as session:
        async with session.begin():
            try:
                model = None
                for mapper in Base.registry.mappers:
                    if mapper.class_.__tablename__ == table_name:
                        model = mapper.class_
                        break

                if not model:
                    return False, f"Таблица {table_name} не найдена"

                if not hasattr(model, column):
                    return False, f"Колонка {column} не существует"

                if not hasattr(model, filter_column):
                    return False, f"Колонка фильтра {filter_column} не существует"

                # Находим запись по фильтру
                stmt = select(model).where(getattr(model, filter_column) == filter_value)
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()

                if not record:
                    return False, f"Запись с {filter_column}={filter_value} не найдена"

                primary_keys = [pk.name for pk in inspect(model).primary_key]
                if column in primary_keys:
                    return False, "Нельзя изменять первичный ключ"

                setattr(record, column, new_data)
                session.add(record)
                await session.commit()
                return True, "Значение успешно обновлено"

            except Exception as e:
                await session.rollback()
                return False, f"Ошибка: {str(e)}"


if "__main__" in __name__:
    from models.mdl_tables import Topics, Base

    a = asyncio.run(read_data_from_db_filter_limit_universal(Topics, 100, 1))
    print(a)
