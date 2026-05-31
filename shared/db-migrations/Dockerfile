FROM python:3.12-slim
WORKDIR /app

# Install alembic + psycopg2 (sync driver for migrations)
RUN pip install --no-cache-dir alembic psycopg2-binary

# Copy migration files
COPY alembic.ini env.py script.py.mako ./
COPY versions/ ./versions/

CMD ["alembic", "upgrade", "head"]
