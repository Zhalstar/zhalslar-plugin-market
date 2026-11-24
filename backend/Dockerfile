FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_HTTP_TIMEOUT=120 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv
COPY backend/pyproject.toml backend/uv.lock /app/backend/
RUN uv sync --project /app/backend --frozen --no-dev --no-install-project --no-python-downloads --no-cache

COPY backend/app /app/backend/app
COPY backend/alembic.ini /app/backend/alembic.ini
COPY backend/migrations /app/backend/migrations
COPY config /app/config
COPY market.json /app/market.json

RUN mkdir -p /data/assets /data/packages && chown -R 10001:10001 /data
USER 10001:10001

ENV MARKET_CONFIG="/app/config/config.yaml" \
    MARKET_SEED_FILE="/app/market.json" \
    STORAGE_DIRECTORY="/data/assets" \
    PACKAGES_DIRECTORY="/data/packages"

EXPOSE 8000

CMD ["sh", "-c", "cd /app/backend && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

