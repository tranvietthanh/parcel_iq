# Testing Commands Reference

Quick reference for running tests across the ParcelIQ stack.

---

## All Tests at Once

```bash
# Run ALL tests (Python + TypeScript) — takes ~3-5 minutes
make test-all

# Expected summary:
# Public API:          49 tests ✓ (83% coverage)
# Admin Backend:       24 tests ✓ (73% coverage)
# Scraper Worker:      84 tests ✓ (70% coverage)
# LLM Parser Worker:   77 tests ✓
# Public Web:          25 tests ✓
# ────────────────────────────────────────────
# Total:              ~260 tests passing
```

---

## By Service

### Public API (`services/public-api`)

```bash
cd services/public-api

# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ -v --cov=app --cov-report=term-missing

# Generate HTML coverage report
uv run pytest tests/ --cov=app --cov-report=html
# Open: htmlcov/index.html

# Unit tests only (fast)
uv run pytest tests/unit/ -v

# Integration tests only (requires Docker infra)
uv run pytest tests/integration/ -v

# Run specific test file
uv run pytest tests/unit/test_security.py -v

# Run specific test function
uv run pytest tests/unit/test_security.py::test_clerk_token_validation -v
```

**Key test files:**
- `tests/unit/test_security.py` — Clerk JWT, rate limits
- `tests/unit/test_schemas.py` — Pydantic validation
- `tests/integration/test_search.py` — bbox/text search against real PostGIS
- `tests/integration/test_payments.py` — Stripe webhook
- `tests/integration/test_spatial.py` — GiST index, ST_Contains

---

### Admin Backend (`services/admin-backend`)

```bash
cd services/admin-backend

# Run all tests
uv run pytest tests/ -v --cov=app

# Unit + integration combined (24 tests)
uv run pytest tests/ -v

# Run specific test
uv run pytest tests/test_scrape.py::test_trigger_scrape_dispatch -v
```

**Key test files:**
- `tests/test_stats.py` — dashboard statistics
- `tests/test_scrape.py` — trigger/history endpoints
- `tests/test_reports.py` — approve/reject/patch flows

---

### Scraper Worker (`services/scraper-worker`)

```bash
cd services/scraper-worker

# Unit tests only (no Docker needed, ~1 sec)
uv run pytest tests/unit/ -v --cov=app

# Full suite with integration (Celery eager mode)
uv run pytest tests/ -v --cov=app

# Run adapter tests
uv run pytest tests/unit/adapters/ -v

# Run specific adapter
uv run pytest tests/unit/adapters/test_vic_plan.py -v

# Run utility tests (robots, PDF, retry, PII)
uv run pytest tests/unit/utils/ -v
```

**Key test files:**
- `tests/unit/adapters/` — 8 adapter unit tests
- `tests/unit/test_registry.py` — adapter registry
- `tests/unit/test_runner.py` — parallel executor
- `tests/unit/test_robots.py` — robots.txt compliance
- `tests/unit/test_pii.py` — PII stripping
- `tests/integration/test_celery.py` — Celery task execution (eager mode)

---

### LLM Parser Worker (`services/llm-parser-worker`)

```bash
cd services/llm-parser-worker

# Run all tests
uv run pytest tests/ -v --cov=app

# Unit tests (fast, no LLM calls)
uv run pytest tests/unit/ -v

# Integration tests (mocked Gemini)
uv run pytest tests/integration/ -v

# Specific test
uv run pytest tests/unit/test_confidence.py::test_high_confidence -v

# Run with live Gemini verification (if GEMINI_API_KEY set)
GEMINI_API_KEY=your-key uv run python scripts/verify_gemini_live.py
```

**Key test files:**
- `tests/unit/test_llm_output.py` — Pydantic validation (19 tests)
- `tests/unit/test_confidence.py` — scoring logic (8 tests)
- `tests/unit/test_prompts.py` — system/user prompts (20 tests)
- `tests/integration/test_parse_task.py` — full pipeline (10 tests)
- `tests/unit/celery_config.py` — Beat schedule validation (5 tests)

---

### Public Web (`apps/public-web`)

```bash
cd apps/public-web

# Run all tests
pnpm test

# Run watch mode (auto-rerun on change)
pnpm test:watch

# Run specific test file
pnpm test -- components/Button.test.tsx

# Run matching pattern
pnpm test -- --grep "Button"

# Generate coverage
pnpm test -- --coverage
```

**Test files:**
- `__tests__/components/` — Button, Spinner, MetricCard (14 tests)
- `__tests__/lib/` — mapbox, stripe (6 tests)
- `__tests__/hooks/` — useMapBounds (2 tests)
- `__tests__/types/` — ApiError (2 tests)
- `__tests__/middleware.ts` — Auth config (1 test)

---

## Test Fixtures & Setup

### Python Fixtures (conftest.py)

Each Python service has fixtures for:
- **Database connection** (`db`, `db_connection`)
- **Mock Celery** (`celery_app`, `celery_worker`)
- **Sample data** (`valid_property_data`, `valid_llm_output`)
- **Auth** (`auth_token`, `service_token`)

Example usage:
```python
def test_search(db, auth_token):
    # db = asyncio-ready DB connection
    # auth_token = valid Clerk JWT (mocked)
    pass
```

### TypeScript Fixtures

Vitest + Testing Library fixtures:
- Mock Next.js components (`Image`, `Link`)
- Mock Mapbox GL JS
- Mock SWR hooks
- Mock Clerk auth

---

## Coverage Thresholds

```
Service                  Target    Actual
─────────────────────────────────────────
Public API              > 70%     83% ✓
Admin Backend           > 70%     73% ✓
Scraper Worker          > 60%     70% ✓
LLM Parser Worker       > 60%     N/A (integration focus)
Public Web              > 50%     N/A (component focus)
```

---

## CI/CD (GitHub Actions)

Tests run automatically on push:

```bash
# View results
# GitHub repo → Actions tab → test-python / test-frontend

# Local CI simulation (same steps)
docker compose run --rm public-api uv run pytest tests/ -v
docker compose run --rm scraper-worker uv run pytest tests/unit/ -v
docker compose run --rm llm-parser-worker uv run pytest tests/ -v
cd apps/public-web && pnpm test --run
```

---

## Debugging Failed Tests

### Python Tests

```bash
# Show print statements
uv run pytest tests/unit/ -v -s

# Drop into debugger on failure
uv run pytest tests/unit/ --pdb

# Show local variables on error
uv run pytest tests/unit/ -l

# Run with verbose SQL logging (for DB tests)
uv run pytest tests/integration/ -v --log-cli-level=DEBUG
```

### TypeScript Tests

```bash
# Run in watch mode to iterate
pnpm test:watch

# Show verbose output
pnpm test -- --reporter=verbose

# Run single test file in debug mode
node --inspect-brk node_modules/.bin/vitest run __tests__/components/Button.test.tsx
# Then open chrome://inspect in Chrome browser
```

---

## Performance / Benchmark

```bash
# Time test execution
time make test-python    # Should be < 30 sec

# Parallel test execution
pytest tests/ -n auto    # If pytest-xdist installed
```

---

## Integration Test Prerequisites

Before running integration tests, ensure:

```bash
# 1. Infrastructure is running
docker compose ps | grep -E "(postgres|redis)" | grep healthy

# 2. Database is migrated
make db-migrate

# 3. Required env vars are set
cat .env | grep DATABASE_URL
cat .env | grep REDIS_URL

# Then run integration tests
cd services/public-api && uv run pytest tests/integration/ -v
```

---

## Quick Test Validation (30 seconds)

```bash
# Skip slow tests, verify basic functionality
cd services/public-api && uv run pytest tests/unit/ -v -k "not integration"
cd services/scraper-worker && uv run pytest tests/unit/ -v
cd services/llm-parser-worker && uv run pytest tests/unit/ -v
cd apps/public-web && pnpm test -- --run

# If all pass → code quality is good
```

---

## Next: Manual Testing

After unit/integration tests pass, test the full stack manually:

1. **Start services:** `make dev-full`
2. **Visit app:** http://localhost:3000
3. **Test features:** Search → pin click → lite panel → unlock flow
4. **Check API:** http://localhost:8080/docs (Swagger)
5. **Review logs:** `make infra-logs`

See **QUICKSTART.md** for detailed manual testing steps.
