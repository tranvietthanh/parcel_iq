FROM python:3.12-slim AS base
WORKDIR /workspace
RUN pip install uv

FROM base AS builder
WORKDIR /workspace/services/public-api
COPY services/public-api/pyproject.toml services/public-api/uv.lock ./
COPY shared/pdf-renderer /workspace/shared/pdf-renderer
RUN uv sync --frozen --no-dev

FROM base AS runner
WORKDIR /workspace/services/public-api
COPY --from=builder /workspace/services/public-api/.venv ./.venv
COPY services/public-api/app ./app
ENV PATH="/workspace/services/public-api/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
