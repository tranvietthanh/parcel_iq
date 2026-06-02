FROM python:3.12-slim AS base
WORKDIR /workspace
RUN pip install uv

FROM base AS builder
WORKDIR /workspace/services/llm-parser-worker
COPY services/llm-parser-worker/pyproject.toml services/llm-parser-worker/uv.lock ./
COPY shared/py-types /workspace/shared/py-types
RUN uv sync --frozen --no-dev

FROM base AS runner
WORKDIR /workspace/services/llm-parser-worker
COPY --from=builder /workspace/services/llm-parser-worker/.venv ./.venv
COPY --from=builder /workspace/shared/py-types /workspace/shared/py-types
COPY services/llm-parser-worker/app ./app
ENV PATH="/workspace/services/llm-parser-worker/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
CMD ["celery", "-A", "app.celery_app", "worker", \
     "--queues", "llm_processing_queue", \
     "--concurrency", "2", \
     "--loglevel", "info"]
