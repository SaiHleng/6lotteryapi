FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py engine.py authorized_api_template.py ./

# Runtime data (SQLite) will live in a volume
ENV DB_PATH=/data/trx_virtual.sqlite3
VOLUME ["/data"]

# The bot reads TELEGRAM_BOT_TOKEN and ALLOWED_CHAT_ID from environment
CMD ["python", "bot.py"]
