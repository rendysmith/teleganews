# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код и .env
COPY bot.py .
COPY .env .

# Запуск
CMD ["python", "bot.py"]