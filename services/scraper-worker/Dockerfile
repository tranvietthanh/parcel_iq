FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy AS base
WORKDIR /app
RUN pip install uv

FROM base AS builder
COPY pyproject.toml uv.lock ./
COPY ../../shared/py-types /shared/py-types
RUN uv sync --frozen --no-dev

FROM base AS runner
COPY --from=builder /app/.venv ./.venv
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Celery worker — concurrency controlled by WORKER_CONCURRENCY env var
CMD ["sh", "-c", "celery -A app.celery_app worker --queues data_acquisition_queue --concurrency ${WORKER_CONCURRENCY:-3} --loglevel info"]
