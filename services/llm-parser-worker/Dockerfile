FROM python:3.12-slim AS base
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
CMD ["celery", "-A", "app.celery_app", "worker", \
     "--queues", "llm_processing_queue", \
     "--concurrency", "2", \
     "--loglevel", "info"]
