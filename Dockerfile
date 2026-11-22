FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt aiohttp

COPY bot.py engine.py prediction.py strategy.py mock_api_client.py authorized_api_template.py index.html ./

ENV DB_PATH=/data/trx_virtual.sqlite3
VOLUME ["/data"]

CMD ["python", "bot.py"]
