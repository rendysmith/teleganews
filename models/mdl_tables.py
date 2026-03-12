from sqlalchemy import Column, Integer, String, DateTime, Date, Index, UniqueConstraint, func
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class Prompt(Base):
    """
    Таблица с промптами
    """
    __tablename__ = 'prompts'
    __table_args__ = {"schema": "public"}  # Перенесено в общую схему для консистентности

    prompt_id = Column(Integer, primary_key=True, autoincrement=True)
    project_name = Column(String, nullable=False, index=True)
    prompt = Column(String, nullable=False)  # Убрал индекс, большие тексты не индексируют


class Session(Base):
    """
    Таблица с сессиями Telegram (Pyrogram/Telethon)
    """
    __tablename__ = "sessions"
    __table_args__ = {"schema": "tg_ai"}

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(String, nullable=False, index=True)
    api_id = Column(String, nullable=False, index=True)
    api_hash = Column(String, nullable=False)

    # ИСПРАВЛЕНИЕ: Сессия Pyrogram - это строка (Base64), а не DateTime!
    session = Column(String, nullable=True)
    block_time = Column(Integer, nullable=True, index=True)


class Channels(Base):
    """
    Таблица с каналами для парсинга
    """
    __tablename__ = "channels"
    __table_args__ = {"schema": "tg_ai"}

    channel_id = Column(Integer, primary_key=True, autoincrement=True)
    channel = Column(String, nullable=False, index=True)
    last_checked_at = Column(Date, nullable=True, index=True)  # nullable=True для новых каналов


class Topics(Base):
    """
    Таблица с темами для бота
    """
    __tablename__ = "topics"
    __table_args__ = {"schema": "tg_ai"}

    topic_id = Column(Integer, primary_key=True, autoincrement=True)
    topic = Column(String, nullable=False, index=True)
    description = Column(String, nullable=False)


class History(Base):
    """
    Таблица с историей сообщений и векторами
    """
    __tablename__ = "history"

    history_id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, index=True)
    channel = Column(String, nullable=False, index=True)
    message_id = Column(Integer, nullable=False, index=True)
    message = Column(String, nullable=False)
    message_emb = Column(Vector(312), nullable=False)

    # НОВАЯ КОЛОНКА: Дата записи в нашу базу
    # server_default=func.now() заставляет базу саму ставить время при вставке
    created_at = Column(DateTime, server_default=func.now(), index=True)

    __table_args__ = (
        # 1. HNSW Индекс для pgvector - критично для производительности косинусного поиска!
        Index(
            'hnsw_idx_history_emb',
            'message_emb',
            postgresql_using='hnsw',
            postgresql_with={'m': 16, 'ef_construction': 64},
            postgresql_ops={'message_emb': 'vector_cosine_ops'}
        ),
        # 2. Защита от дубликатов на уровне БД (заменяет костыль с выгрузкой 2000 ID в память парсера)
        UniqueConstraint('channel', 'message_id', name='uq_channel_message'),
        {"schema": "tg_ai"}
    )