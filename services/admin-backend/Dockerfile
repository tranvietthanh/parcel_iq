# ────────────────────────────────────────────────────────────────
# Stage 1: Base
# ────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /app

# Install uv for dependency management
RUN pip install --no-cache-dir uv

# ────────────────────────────────────────────────────────────────
# Stage 2: Builder
# ────────────────────────────────────────────────────────────────
FROM base AS builder

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev packages)
RUN uv sync --frozen --no-dev

# ────────────────────────────────────────────────────────────────
# Stage 3: Runner
# ────────────────────────────────────────────────────────────────
FROM base AS runner

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY app ./app

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8082

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8082/health')"

# Run with single worker (ClusterIP service, low concurrency)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8082", "--workers", "1"]
