import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, List, Optional

import httpx
from sentence_transformers import SentenceTransformer
from sqlalchemy import select

# Импорты LangChain
from langchain_core.language_models.llms import LLM
from langchain_core.callbacks.manager import AsyncCallbackManagerForLLMRun
from langchain_core.prompts import PromptTemplate

from models.mdl_tables import History
from database.db_loader import SessionLocal

logger = logging.getLogger(__name__)

# 1. Загрузка локальной модели (Retriever)
print("Загружаю модель cointegrated/rubert-tiny2...")
local_model = SentenceTransformer('cointegrated/rubert-tiny2')


def _encode_text(text: str) -> list[float]:
    """Выносим кодирование для запуска в отдельном потоке"""
    return local_model.encode(text).tolist()


# =======================================================
# 2. LANGCHAIN: КАСТОМНАЯ LLM ПОД ТВОЙ ПРОКСИ
# =======================================================
class TgProxyLLM(LLM):
    """
    Кастомный класс LLM для LangChain, который умеет общаться
    с твоим специфичным прокси-сервером через Basic Auth.
    """
    url: str
    login: str
    password: str

    @property
    def _llm_type(self) -> str:
        return "tg_proxy_llm"

    def _call(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError("Синхронный вызов не поддерживается. Используйте ainvoke()")

    async def _acall(
            self,
            prompt: str,
            stop: Optional[List[str]] = None,
            run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
            **kwargs: Any,
    ) -> str:
        # Здесь спрятана вся логика с ретраями, которую мы убрали из bot.py
        auth = (self.login, self.password)
        payload = {"prompt": prompt}

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(self.url, json=payload, auth=auth)

                    if response.status_code == 200:
                        return response.json()['result'][1]

                    elif response.status_code in [500, 502, 503, 504]:
                        retry_count += 1
                        logger.warning(f"Ошибка прокси {response.status_code}. Попытка {retry_count}...")
                        await asyncio.sleep(2 ** retry_count)
                        continue
                    else:
                        return f"Ошибка API прокси. Код: {response.status_code}"

            except httpx.TimeoutException:
                retry_count += 1
                logger.warning(f"Таймаут прокси. Попытка {retry_count}...")
                await asyncio.sleep(2 ** retry_count)

        return "Время ожидания истекло. Сервер генерации недоступен."


# =======================================================
# 3. ПОИСК В БАЗЕ (RETRIEVER)
# =======================================================
async def get_context_from_db(query_text: str, days: int = 14, limit: int = 30) -> str:
    """
    Ищет новости и сразу возвращает готовый текст контекста для LangChain.
    """
    query_vector = await asyncio.to_thread(_encode_text, query_text)
    start_date = datetime.now() - timedelta(days=days)

    async with SessionLocal() as session:
        stmt = (
            select(History)
            .where(History.date >= start_date)
            .order_by(History.message_emb.cosine_distance(query_vector))
            .limit(limit)
        )
        result = await session.execute(stmt)
        posts = result.scalars().all()

        # Собираем контекст в одну строку
        context_list = [f"{i.message}\nlink: 'https://t.me/{i.channel}/{i.message_id}'" for i in posts]
        return "\n\n".join(context_list)


# =======================================================
# 4. LANGCHAIN: СБОРКА ЦЕПОЧКИ (LCEL CHAIN)
# =======================================================
def get_rag_chain(prompt_template_str: str):
    """
    Собирает современную цепочку генерации ответа.
    """
    # Инициализируем наш LLM
    llm = TgProxyLLM(
        url=os.getenv("GENERATOR_API_URL", "http://109.107.170.211:8000/api/v1/start_generation"),
        login=os.getenv("LOGIN_GEN"),
        password=os.getenv("PASS_GEN")
    )

    # Создаем шаблон промпта из строки, которую мы достали из БД
    # Ожидается, что там есть {short_history} и {topic}
    prompt = PromptTemplate.from_template(prompt_template_str)

    # LangChain Expression Language (Магия объединения)
    chain = prompt | llm

    return chain