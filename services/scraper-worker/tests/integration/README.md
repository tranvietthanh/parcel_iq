# Level 3: Celery Task Queue Integration Tests

Integration tests that verify adapter execution through Celery task patterns. These tests dispatch tasks and verify end-to-end execution with mocked external APIs.

## Test Structure

```
tests/integration/
├── __init__.py
├── conftest.py              # Test fixtures (DB, Redis, Celery config)
└── test_adapter_tasks.py    # Integration test suite (8 tests)
```

## Test Coverage

### Adapter Execution Tests
- ✅ **VicPlan Adapter** - 3 spatial queries (zones, overlays, bushfire)
- ✅ **NSW Planning Adapter** - 4 service calls (zoning, heritage, flood, bushfire)
- ✅ **NBN Co Adapter** - 2-step suggest→details flow
- ✅ **ABS Census Adapter** - DB cache hit (fast path)
- ✅ **Error Handling** - Graceful adapter failure

### Celery Configuration Tests
- ✅ **Celery App Configuration** - Verifies serialization, timezone, routing
- ✅ **Scrape Property Task Registration** - Main task is registered
- ✅ **Census Refresh Task Registration** - Background task is registered

## Running Tests

### Quick Run (Eager Mode — No Worker Needed)

Tests execute synchronously in-process using `task_always_eager=True`:

```bash
cd services/scraper-worker

# Run all integration tests
uv run pytest tests/integration/ -v

# Run specific test
uv run pytest tests/integration/test_adapter_tasks.py::TestAdapterTaskExecution::test_vic_plan_adapter_execution -xvs

# Run with coverage
uv run pytest tests/integration/ --cov=app --cov-report=html
```

**No dependencies needed** — Redis/Postgres/Celery worker not required.

### Full Integration Run (with Real Worker)

For testing actual distributed execution through Redis:

**1. Start dependencies:**
```bash
docker compose up -d postgres redis
cd shared/db-migrations && alembic upgrade head
```

**2. Start Celery worker (separate terminal):**
```bash
cd services/scraper-worker
celery -A app.celery_app worker --loglevel=info --queue=data_acquisition_queue
```

**3. Modify conftest to disable eager mode:**
```python
# tests/integration/conftest.py
celery_app.conf.update(
    task_always_eager=False,  # Use real broker
    task_eager_propagates=False,
    broker_url=redis_url,
    result_backend=redis_url,
)
```

**4. Run tests:**
```bash
uv run pytest tests/integration/ -v -s
```

Tasks will be dispatched to Redis, picked up by worker, and results returned via AsyncResult.

## Test Fixtures

### Database
- `db_url` - Connection string (defaults to parceliq_test DB)
- `db_engine` - SQLAlchemy engine
- `db_connection` - Per-test connection with rollback
- `seed_test_property` - Insert test property

### Celery
- `celery_config` - Configured Celery app with eager mode
- `redis_url` - Redis connection (defaults to DB 1 for tests)

### Sample Data
- `sample_property_job` - VIC property job dict
- `sample_nsw_property_job` - NSW property job dict

## Key Differences from Unit Tests

| Aspect | Unit Tests | Integration Tests |
|--------|------------|------------------|
| Execution | Mock everything | Mock only external APIs |
| Redis | Not needed | Used (or eager mode) |
| Postgres | Not needed | Optional (for full E2E) |
| Celery | Not configured | Fully configured |
| Speed | ~0.01s per test | ~0.1s per test |
| Scope | Single function | Full execution flow |

## Example Test

```python
def test_vic_plan_adapter_execution(celery_config, sample_property_job):
    """Test VicPlan adapter executes successfully."""
    from app.adapters.state.vic_plan import VicPlanAdapter

    with patch.object(VicPlanAdapter, "fetch_json") as mock_fetch:
        # Mock 3 ArcGIS FeatureServer responses
        mock_fetch.side_effect = [
            {"features": [{"attributes": {"ZONE_CODE": "GRZ1"}}]},  # Zone
            {"features": [{"attributes": {"ZONE_CODE": "HO123"}}]},  # Overlay
            {"features": [{"attributes": {"OBJECTID": 1}}]},  # Bushfire
        ]

        adapter = VicPlanAdapter()
        result = adapter.scrape(sample_property_job)

        assert result["zoning_code"] == "GRZ1"
        assert result["bushfire_risk"] == "LOW"
        assert mock_fetch.call_count == 3  # Verifies all 3 API calls made
```

## Test Results

**Current Status**: ✅ **80/80 tests passing** (72 unit + 8 integration)

```
tests/integration/test_adapter_tasks.py::TestAdapterTaskExecution::test_vic_plan_adapter_execution PASSED
tests/integration/test_adapter_tasks.py::TestAdapterTaskExecution::test_nsw_state_uses_generic_adapter PASSED
tests/integration/test_adapter_tasks.py::TestAdapterTaskExecution::test_nbn_adapter_execution_with_suggest_flow PASSED
tests/integration/test_adapter_tasks.py::TestAdapterTaskExecution::test_abs_census_adapter_with_db_cache_hit PASSED
tests/integration/test_adapter_tasks.py::TestAdapterTaskExecution::test_adapter_error_handling PASSED
tests/integration/test_adapter_tasks.py::TestCeleryTaskConfiguration::test_celery_app_configured PASSED
tests/integration/test_adapter_tasks.py::TestCeleryTaskConfiguration::test_scrape_property_task_registered PASSED
tests/integration/test_adapter_tasks.py::TestCeleryTaskConfiguration::test_census_refresh_task_registered PASSED
```

## Next Steps

To add more integration tests:

1. **Full scrape_property task test** - Requires DB, MinIO, LLM mocking
2. **Census refresh task test** - Test bulk SA2 download
3. **Real worker dispatch** - Test `.apply_async()` with result waiting
4. **Retry behavior** - Test Celery retry logic with transient failures

## References

- Testing Strategy: [`docs/10-testing-strategy.md`](../../../docs/10-testing-strategy.md)
- Celery Configuration: [`app/celery_app.py`](../../app/celery_app.py)
- Main Scrape Task: [`app/tasks.py`](../../app/tasks.py)
