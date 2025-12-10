import asyncio

from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from models.mdl_tables import History
from utils.db_loader import SessionLocal

print("Загружаю модель...")
local_model = SentenceTransformer('cointegrated/rubert-tiny2')

async def search_relevant_news(query_text, limit=30):
    """
    Ищет новости, похожие на query_text по смыслу.
    """
    # 2. Превращаем запрос в вектор
    query_vector = local_model.encode(query_text).tolist()

    async with SessionLocal() as session:
        # 3. SQL запрос: Сортируем по косинусному расстоянию (cosine_distance)
        # Чем меньше дистанция, тем больше похожесть.
        stmt = select(History).order_by(
            History.message_emb.cosine_distance(query_vector)
        ).limit(limit)

        result = await session.execute(stmt)
        posts = result.scalars().all()

        return posts

if "__main__" in __name__:
    a = asyncio.run(search_relevant_news("Аналитика digital-рынка: данные, цифры, статистика"))
    print(a)

    for i in a:
        print(i.message)