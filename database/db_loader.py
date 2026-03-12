import os
import logging
from pathlib import Path
from typing import List, Any
from datetime import datetime, timedelta

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv

from models.mdl_tables import Base, Prompt, Session, Channels, Topics, History

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dotenv_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path)


def get_database_url() -> str:
    host = os.environ.get("POSTGRESQL_HOST")
    port = os.environ.get("POSTGRESQL_PORT")
    database = os.environ.get("POSTGRESQL_DB")
    user = os.environ.get("POSTGRESQL_USERNAME")
    password = os.environ.get("POSTGRESQL_PASSWORD")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"


DATABASE_URL = get_database_url()

# Настройка пула соединений
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

# =======================================================
# БЫСТРЫЙ И БЕЗОПАСНЫЙ ПОИСК МОДЕЛЕЙ (Вместо registry)
# =======================================================
MODELS_MAP = {
    'prompts': Prompt,
    'sessions': Session,
    'channels': Channels,
    'topics': Topics,
    'history': History
}


def get_model(table_name: str):
    """Моментально возвращает класс модели по имени таблицы"""
    return MODELS_MAP.get(table_name)


# =======================================================
# УНИВЕРСАЛЬНЫЕ CRUD ФУНКЦИИ
# =======================================================

async def read_data_from_db_filter_limit_universal(
        table_name: str,
        limit: int = 10,
        page: int = 1,
        filters=None) -> tuple[bool, List[Any] | str]:
    model = get_model(table_name)
    if not model:
        return False, f"Таблица {table_name} не найдена"

    async with SessionLocal() as session:
        try:
            query = select(model)
            if filters is not None:
                query = query.where(filters)

            query = query.limit(limit).offset((page - 1) * limit)
            result = await session.execute(query)
            results = result.scalars().all()
            return True, results

        except Exception as e:
            logger.error(f"Ошибка чтения из {table_name}: {e}")
            return False, str(e)


async def add_data_to_db_universal(datas) -> tuple[bool, str]:
    table_name = datas.table_name
    data_dict = datas.datas

    model = get_model(table_name)
    if not model:
        return False, f"Таблица {table_name} не найдена"

    async with SessionLocal() as session:
        try:
            new_record = model(**data_dict)
            session.add(new_record)
            await session.commit()
            return True, 'Данные успешно добавлены'

        except IntegrityError:
            # ОШИБКА ДУБЛИКАТА: Сработает UniqueConstraint.
            # Тихо откатываем транзакцию, это нормальное поведение для парсера.
            await session.rollback()
            return True, 'Дубликат проигнорирован базой (IntegrityError)'

        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка добавления в {table_name}: {e}")
            return False, str(e)


async def update_data_from_db_universal(datas) -> tuple[bool, str]:
    table_name = datas.table_name
    column = datas.column
    filter_column = datas.filter_column
    filter_value = datas.filter_value
    new_data = datas.new_data

    model = get_model(table_name)
    if not model:
        return False, f"Таблица {table_name} не найдена"

    async with SessionLocal() as session:
        try:
            stmt = select(model).where(getattr(model, filter_column) == filter_value)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if not record:
                return False, f"Запись с {filter_column}={filter_value} не найдена"

            setattr(record, column, new_data)
            await session.commit()
            return True, "Значение успешно обновлено"

        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка обновления в {table_name}: {e}")
            return False, str(e)


async def delete_data_to_db_universal(datas) -> tuple[bool, str]:
    table_name = datas.table_name
    data_dict = datas.datas

    model = get_model(table_name)
    if not model:
        return False, f"Таблица {table_name} не найдена"

    async with SessionLocal() as session:
        try:
            if hasattr(model, 'date'):
                days = data_dict.get('days', 60)
                cutoff_date = datetime.now() - timedelta(days=days)
                delete_query = delete(model).where(model.date < cutoff_date)

                result = await session.execute(delete_query)
                await session.commit()
                return True, f'Удалено {result.rowcount} записей старше {days} дней.'
            else:
                return False, f'В таблице {table_name} нет колонки "date"'

        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка удаления из {table_name}: {e}")
            return False, str(e)