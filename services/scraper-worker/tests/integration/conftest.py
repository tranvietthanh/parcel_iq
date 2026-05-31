"""Integration test fixtures — Redis, DB, Celery configuration."""

from __future__ import annotations

import os
from typing import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.celery_app import celery_app


@pytest.fixture(scope="session")
def db_url() -> str:
    """Database URL from environment."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://parceliq:devpassword@localhost:5432/parceliq_test",
    )


@pytest.fixture(scope="session")
def redis_url() -> str:
    """Redis URL from environment."""
    return os.getenv("REDIS_URL", "redis://localhost:6379/1")  # DB 1 for tests


@pytest.fixture(scope="session")
def db_engine(db_url: str):
    """SQLAlchemy engine for integration tests."""
    engine = create_engine(db_url, poolclass=NullPool)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_connection(db_engine):
    """Fresh DB connection per test with transaction rollback."""
    conn = db_engine.connect()
    trans = conn.begin()
    yield conn
    trans.rollback()
    conn.close()


@pytest.fixture(scope="session")
def celery_config(redis_url: str):
    """Configure Celery for integration tests.
    
    Uses task_always_eager=True to execute tasks synchronously
    without needing a separate worker process.
    """
    # Import tasks to ensure they're registered
    import app.tasks  # noqa: F401
    import app.tasks_census_refresh  # noqa: F401
    
    celery_app.conf.update(
        task_always_eager=True,  # Execute tasks synchronously in-process
        task_eager_propagates=True,  # Propagate exceptions immediately
        broker_url=redis_url,
        result_backend=redis_url,
    )
    return celery_app.conf


@pytest.fixture()
def sample_property_job() -> dict:
    """Sample property job dict for scraping tasks."""
    return {
        "property_id": "550e8400-e29b-41d4-a716-446655440000",
        "gnaf_pid": "GAVIC411711364",
        "address_string": "1 Collins Street, Melbourne VIC 3000",
        "latitude": -37.8136,
        "longitude": 144.9631,
        "lga_name": "Melbourne",
        "state": "VIC",
    }


@pytest.fixture()
def sample_nsw_property_job() -> dict:
    """Sample NSW property job for NSW Planning adapter."""
    return {
        "property_id": "550e8400-e29b-41d4-a716-446655440001",
        "gnaf_pid": "GANSW123456789",
        "address_string": "1 George Street, Sydney NSW 2000",
        "latitude": -33.8688,
        "longitude": 151.2093,
        "lga_name": "Sydney",
        "state": "NSW",
    }


@pytest.fixture()
def seed_test_property(db_connection, sample_property_job):
    """Insert a test property into the database."""
    db_connection.execute(
        text("""
            INSERT INTO properties (
                id, gnaf_pid, address_string, 
                latitude, longitude, lga_name, state,
                created_at, updated_at
            ) VALUES (
                :property_id, :gnaf_pid, :address_string,
                :latitude, :longitude, :lga_name, :state,
                NOW(), NOW()
            )
        """),
        sample_property_job,
    )
    db_connection.commit()
    yield sample_property_job
    # Cleanup handled by transaction rollback
