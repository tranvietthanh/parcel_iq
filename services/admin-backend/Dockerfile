# ────────────────────────────────────────────────────────────────
# Stage 1: Base
# ────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /workspace

# Install uv for dependency management
RUN pip install --no-cache-dir uv

# ────────────────────────────────────────────────────────────────
# Stage 2: Builder
# ────────────────────────────────────────────────────────────────
FROM base AS builder

# Copy dependency files
WORKDIR /workspace/services/admin-backend
COPY services/admin-backend/pyproject.toml services/admin-backend/uv.lock ./
COPY shared/pdf-renderer /workspace/shared/pdf-renderer

# Install dependencies (no dev packages)
RUN uv sync --frozen --no-dev

# ────────────────────────────────────────────────────────────────
# Stage 3: Runner
# ────────────────────────────────────────────────────────────────
FROM base AS runner

WORKDIR /workspace/services/admin-backend

# Copy virtual environment from builder
COPY --from=builder /workspace/services/admin-backend/.venv /workspace/services/admin-backend/.venv

# Copy application code
COPY services/admin-backend/app ./app

# Set environment variables
ENV PATH="/workspace/services/admin-backend/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8082

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8082/health')"

# Run with single worker (ClusterIP service, low concurrency)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8082", "--workers", "1"]
