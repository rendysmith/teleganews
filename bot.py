import asyncio
import os
import logging

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, CallbackQuery
from aiogram.client.default import DefaultBotProperties

from dotenv import load_dotenv

from database.db_loader import read_data_from_db_filter_limit_universal
from models.mdl_tables import Prompt, Topics

# Импортируем наши новые крутые функции на базе LangChain
from services.search_news import get_context_from_db, get_rag_chain

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден. Проверьте файл .env")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()
router = Router()


@router.message(CommandStart())
async def handle_start(message: types.Message):
    topic_lists = []

    # Пытаемся получить темы из БД с ретраями
    for _ in range(5):
        status, topics = await read_data_from_db_filter_limit_universal('topics', 100, 1)
        if status:
            topic_lists = [i.topic for i in topics]
            break
        await asyncio.sleep(5)

    if not topic_lists:
        await message.answer("Не удалось получить данные из базы данных. Попробуйте позже.")
        return

    # Динамически собираем клавиатуру
    inline_keyboard = [[types.InlineKeyboardButton(text=topic, callback_data=f"topic:{topic}")]
                       for topic in topic_lists
                       ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

    await message.answer("Выбери тему:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("topic:"))
async def handle_choice_topic(callback: CallbackQuery, state: FSMContext):
    topic = callback.data.split(":")[1]

    # Сохраняем выбор в машину состояний (FSM)
    await state.update_data(topic=topic)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text='за 14 дней', callback_data="days:14")],
                         [types.InlineKeyboardButton(text='за 30 дней', callback_data="days:30")]
                         ])

    # Изменяем текущее сообщение вместо отправки нового
    await callback.message.edit_text(f'Выбрана тема: *{topic}*\nВыберите период истории:', reply_markup=keyboard)


@router.callback_query(F.data.startswith("days:"))
async def handle_choice_days(callback: CallbackQuery, state: FSMContext):
    days = int(callback.data.split(":")[1])

    data = await state.get_data()
    topic_name = data.get('topic')

    if not topic_name:
        await callback.answer("Ошибка сессии. Начните заново через /start", show_alert=True)
        return

    # =========================================================
    # UX ФИШКА: Сразу даем пользователю обратную связь!
    # =========================================================
    wait_msg = await callback.message.edit_text(
        f'⏳ *Анализирую тему "{topic_name}" за {days} дней.*\n\n'
        f'Ищу релевантные посты и генерирую сводку. '
        f'Обычно это занимает 1-2 минуты...'
    )

    try:
        # 1. Достаем полное описание темы из БД
        filter_topic = Topics.topic == topic_name
        status, full_topic = await read_data_from_db_filter_limit_universal('topics', 1, 1, filter_topic)
        topic_description = full_topic[0].description

        # 2. Ищем новости в векторе (LangChain Retriever)
        context_text = await get_context_from_db(topic_description, days=days)

        if not context_text.strip():
            await wait_msg.edit_text(
                f"За последние {days} дней релевантных новостей по теме '{topic_name}' не найдено.")
            return

        # 3. Достаем промпт из БД
        filter_prompt = Prompt.project_name == 'tg_news'
        status, prompt_context = await read_data_from_db_filter_limit_universal('prompts', 1, 1, filter_prompt)
        prompt_template_str = prompt_context[0].prompt

        # 4. СОБИРАЕМ И ЗАПУСКАЕМ ЦЕПОЧКУ LANGCHAIN (LCEL)
        chain = get_rag_chain(prompt_template_str)

        # Запускаем генерацию асинхронно
        result_text = await chain.ainvoke({
            "short_history": context_text,
            "topic": topic_description
        })

        # 5. Заменяем сообщение ожидания на готовый результат от ИИ
        await wait_msg.edit_text(result_text)

    except Exception as e:
        logger.error(f"Непредвиденная ошибка в процессе RAG: {e}")
        await wait_msg.edit_text(
            "Произошла ошибка при обращении к нейросети. Попробуйте выбрать другой период или тему.")


dp.include_router(router)


async def main():
    logger.info("Бот запущен и готов к работе!")
    # Игнорируем старые апдейты при старте
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())