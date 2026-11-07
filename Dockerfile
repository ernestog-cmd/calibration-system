FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
# The PostgreSQL driver is only needed inside the container; local development uses SQLite
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts

RUN useradd --create-home appuser \
    && mkdir -p /data/uploads \
    && chown -R appuser:appuser /app /data

USER appuser

ENV UPLOAD_DIR=/data/uploads

EXPOSE 8000

# One process only: the scheduler runs inside it, so more workers would repeat the daily job
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]