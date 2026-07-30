FROM python:3.12-slim

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app ./app
COPY ./migrations ./migrations
COPY ./scripts ./scripts

# Railway injects PORT; default 8000 for local docker compose
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
