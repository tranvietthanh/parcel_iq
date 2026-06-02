FROM mcr.microsoft.com/playwright/python:v1.52.0-noble AS base
WORKDIR /workspace
RUN pip install uv

FROM base AS builder
WORKDIR /workspace/services/scraper-worker
COPY services/scraper-worker/pyproject.toml services/scraper-worker/uv.lock ./
COPY shared/py-types /workspace/shared/py-types
RUN UV_PYTHON_DOWNLOADS=never uv sync --frozen --no-dev --python /usr/bin/python3

FROM base AS runner
WORKDIR /workspace/services/scraper-worker
COPY --from=builder /workspace/services/scraper-worker/.venv ./.venv
COPY --from=builder /workspace/shared/py-types /workspace/shared/py-types
COPY services/scraper-worker/app ./app
ENV PATH="/workspace/services/scraper-worker/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Celery worker — concurrency controlled by WORKER_CONCURRENCY env var
CMD ["sh", "-c", "celery -A app.celery_app worker --queues data_acquisition_queue --concurrency ${WORKER_CONCURRENCY:-3} --loglevel info"]
