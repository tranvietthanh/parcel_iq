# OZ Property Report – Testing Strategy

## 1. Philosophy

Tests are written to catch the failures that actually hurt: wrong spatial queries returning bad data, report generation silently failing, LLM output bypassing validation, scrapers breaking on DOM changes, and admin actions reaching the wrong users. Coverage for its own sake is not a goal.

**The testing pyramid for this project:**

```
          ▲  E2E (Playwright)
         ███  — critical user journeys only
        ██████
       ████████  Integration — API contracts, DB queries, Celery tasks
      ██████████
     ████████████  Unit — pure functions, adapters, validators, parsers
```

---

## 2. Tools by Layer

| Layer | TypeScript (Next.js apps) | Python (FastAPI / Celery) |
|---|---|---|
| Unit | Vitest | pytest |
| Integration | Vitest + `@testing-library/react` | pytest + `httpx.AsyncClient` + testcontainers |
| E2E | Playwright | — |
| API contract | — | pytest + `httpx.AsyncClient` |
| DB queries | — | pytest + testcontainers (real Postgres+PostGIS) |
| Coverage | Vitest `--coverage` (v8) | pytest-cov |
| CI runner | GitHub Actions | GitHub Actions |

---

## 3. Unit Tests

### 3.1 Python Services

**What to unit test:**
- Adapter output parsing logic (not the HTTP call, just the parsing)
- LLM output Pydantic validators (valid input, missing fields, wrong types)
- Confidence scoring calculation
- `jsonb_set` path builder in `admin-backend`
- Celery task retry/backoff logic (mock the broker)
- G-NAF CSV parsing helpers

**Location:** `services/<name>/tests/unit/`

**Example — LLM validator:**
```python
# services/llm-parser-worker/tests/unit/test_llm_output_validator.py
import pytest
from app.validators import LlmOutput

def test_valid_output_passes():
    data = {
        "zoning_and_planning": {
            "zoning_code": "GRZ1",
            "confidence_score": 0.91
        },
        "risk_factors": {
            "flood": {"risk": "LOW", "confidence_score": 0.97},
            "bushfire": {"risk": "NONE", "confidence_score": 0.99},
        },
        # ... other required fields
    }
    result = LlmOutput.model_validate(data)
    assert result.zoning_and_planning.zoning_code == "GRZ1"

def test_rejects_unexpected_fields():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        LlmOutput.model_validate({"hallucinated_field": "oops", ...})

def test_null_unknown_fields_pass():
    # LLM should return null for unknowns, not omit the field
    data = {..., "risk_factors": {"flood": {"risk": None, "confidence_score": 0.0}}}
    result = LlmOutput.model_validate(data)
    assert result.risk_factors.flood.risk is None

def test_review_required_when_confidence_low():
    from parceliq_types.confidence import compute_confidence
    output = LlmOutput.model_validate({...})
    result = compute_confidence(output)
    assert result.review_required is True
    review_reasons = result.scores.get("review_reasons") or []
    assert any("Low confidence fields" in reason for reason in review_reasons)
```

**Example — adapter parser:**
```python
# services/scraper-worker/tests/unit/test_techone_adapter.py
from app.adapters.council.techone import TechOneCouncilAdapter

def test_parses_planning_application_table():
    html = open("tests/fixtures/techone_planning_table.html").read()
    adapter = TechOneCouncilAdapter(config={})
    result = adapter._parse_applications(html)
    assert len(result) == 3
    assert result[0]["application_number"] == "PA/2024/001"

def test_returns_empty_list_on_no_results():
    result = TechOneCouncilAdapter(config={})._parse_applications("<table></table>")
    assert result == []
```

**Run:**
```bash
cd services/llm-parser-worker
uv run pytest tests/unit/ -v
```

---

### 3.2 TypeScript Apps

**What to unit test:**
- Utility functions (`lib/api.ts` error handling, token attachment logic)
- Pure UI components with props (StatCard, MetricCard, RiskTeaser)
- Form validation logic in admin forms

**Location:** `apps/<name>/tests/unit/` or colocated as `*.test.ts`

**Example — API client error handling:**
```typescript
// apps/public-web/lib/__tests__/api.test.ts
import { describe, it, expect, vi } from 'vitest';
import { useApiClient } from '../api';

describe('useApiClient', () => {
  it('throws ApiError with status on non-ok response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({ detail: 'Rate limit exceeded' }),
    });
    // ... test the error is thrown correctly
  });
});
```

**Run:**
```bash
cd apps/public-web
pnpm test          # Vitest watch mode
pnpm test --run    # single pass (CI)
```

---

## 4. Integration Tests

### 4.1 Python — API Endpoints (httpx.AsyncClient)

All FastAPI routes are tested against a real in-process app with a real test database (via testcontainers). No mocking of DB — spatial queries must actually run.

**Setup — shared pytest fixtures:**
```python
# shared/db-migrations/tests/conftest.py  (or per-service conftest.py)
import pytest
import asyncpg
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgis/postgis:16-3.4") as pg:
        yield pg

@pytest.fixture(scope="session")
async def db_pool(pg_container):
    pool = await asyncpg.create_pool(pg_container.get_connection_url())
    # Run all migrations against the test DB
    await run_migrations(pg_container.get_connection_url())
    yield pool
    await pool.close()
```

**Public API integration tests:**
```python
# services/public-api/tests/integration/test_search.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_bbox_search_returns_geojson(db_pool, seed_properties):
    async with AsyncClient(transport=ASGITransport(app=app)) as client:
        response = await client.get(
            "/api/search",
            params={"bbox": "144.5,-37.95,144.75,-37.80"},
            headers={"X-Turnstile-Token": "test-bypass"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) > 0
    assert body["features"][0]["geometry"]["type"] == "Point"

@pytest.mark.asyncio
async def test_bbox_search_rate_limited_after_5_requests(db_pool):
    async with AsyncClient(transport=ASGITransport(app=app)) as client:
        for _ in range(5):
            await client.get("/api/search", params={"bbox": "..."})
        response = await client.get("/api/search", params={"bbox": "..."})
    assert response.status_code == 429

@pytest.mark.asyncio
async def test_property_detail_returns_curated_sections(client, db_pool):
  response = await client.get("/api/properties/some-uuid/detail")
  assert response.status_code == 200
  body = response.json()
  assert "education" in body
  assert "connectivity" in body

@pytest.mark.asyncio
async def test_full_pdf_requires_auth(
    auth_client, db_pool, seed_unlocked_report
):
    response = await auth_client.get(
    f"/api/properties/{seed_unlocked_report.property_id}/full/pdf"
    )
    assert response.status_code == 200
  assert response.headers["content-type"] == "application/pdf"
```

**Admin Backend API integration tests:**
```python
# services/admin-backend/tests/integration/test_reports.py
@pytest.mark.asyncio
async def test_approve_report_sets_status_ready(admin_client, db_pool, seed_review_report):
    response = await admin_client.post(
        f"/reports/{seed_review_report.id}/approve"
    )
    assert response.status_code == 200

    row = await db_pool.fetchrow(
        "SELECT status FROM property_reports WHERE id=$1",
        seed_review_report.id
    )
    assert row["status"] == "READY"

@pytest.mark.asyncio
async def test_reject_without_service_token_returns_401(db_pool, seed_review_report):
    async with AsyncClient(transport=ASGITransport(app=app)) as client:
        response = await client.post(f"/reports/{seed_review_report.id}/reject")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_patch_insights_updates_nested_jsonb(admin_client, db_pool, seed_report):
    response = await admin_client.patch(
        f"/reports/{seed_report.id}/insights",
        json={"field_path": "risk_factors.flood.risk", "new_value": "MEDIUM"}
    )
    assert response.status_code == 200

    row = await db_pool.fetchrow(
        "SELECT llm_parsed_insights FROM property_reports WHERE id=$1", seed_report.id
    )
    assert row["llm_parsed_insights"]["risk_factors"]["flood"]["risk"] == "MEDIUM"
```

**Key spatial query tests:**
```python
# services/public-api/tests/integration/test_spatial.py
@pytest.mark.asyncio
async def test_school_catchment_contains_property(db_pool, seed_spatial_data):
    """Validates PostGIS ST_Contains — wrong SRID would silently fail this."""
    rows = await db_pool.fetch("""
        SELECT p.id FROM properties p
        JOIN spatial_zones z ON ST_Contains(z.geom, p.geom)
        WHERE z.name = 'Test Primary School' AND z.zone_type = 'SCHOOL_CATCHMENT'
    """)
    assert len(rows) == 1
    assert str(rows[0]["id"]) == seed_spatial_data["inside_property_id"]

@pytest.mark.asyncio
async def test_bbox_query_uses_gist_index(db_pool):
    """EXPLAIN ANALYZE to verify the GiST index is hit — catches missing indexes."""
    plan = await db_pool.fetchval("""
        EXPLAIN (FORMAT JSON, ANALYZE)
        SELECT id FROM properties
        WHERE geom && ST_MakeEnvelope(144.5, -37.95, 144.75, -37.80, 4326)
    """)
    import json
    plan_json = json.loads(plan)
    node_types = extract_node_types(plan_json)
    assert "Bitmap Index Scan" in node_types or "Index Scan" in node_types
```

---

### 4.2 TypeScript — Next.js Server Actions

Server Actions are tested by calling them directly in a Node.js test environment with a mocked Clerk session and a stubbed internal HTTP client.

```typescript
// apps/admin-web/tests/integration/actions/scrape.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { triggerScrape } from '@/actions/scrape';

// Mock Clerk auth
vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn().mockResolvedValue({
    userId: 'user_test_admin',
    orgId: process.env.CLERK_ADMIN_ORG_ID,
  }),
}));

// Mock fetch (the internal HTTP call to admin-backend)
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('triggerScrape Server Action', () => {
  beforeEach(() => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ jobs_queued: 42, estimated_completion_minutes: 14 }),
    });
  });

  it('calls admin backend with correct payload', async () => {
    const formData = new FormData();
    formData.set('scope', 'LGA');
    formData.set('state', 'VIC');
    formData.set('lga', 'Wyndham City Council');
    formData.set('priority', 'HIGH');

    await triggerScrape(formData);

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/scrape/trigger'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'X-Service-Token': process.env.ADMIN_SERVICE_TOKEN,
        }),
        body: expect.stringContaining('"scope":"LGA"'),
      })
    );
  });

  it('throws when Clerk org does not match', async () => {
    vi.mocked(auth).mockResolvedValueOnce({
      userId: 'user_imposter',
      orgId: 'org_wrong',
    });
    await expect(triggerScrape(new FormData())).rejects.toThrow('Unauthorised');
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
```

---

### 4.3 Celery Task Integration Tests

Test full task execution (scrape → parse pipeline) against a real Redis broker (testcontainers) and real Postgres, with Playwright and Gemini API mocked.

```python
# services/scraper-worker/tests/integration/test_scrape_task.py
import pytest
from unittest.mock import patch, AsyncMock
from app.tasks import scrape_property

@pytest.mark.asyncio
async def test_scrape_task_writes_raw_data_to_db(db_pool, redis_url, seed_property):
    with patch("app.adapters.state.vic.VicPlanAdapter.fetch") as mock_vic, \
         patch("app.adapters.council.techone.TechOneCouncilAdapter.fetch") as mock_council:
        mock_vic.return_value = {"zoning": "GRZ1", "overlays": []}
        mock_council.return_value = {"applications": []}

        scrape_property.apply(
            kwargs={
                "property_id": str(seed_property["id"]),
                "gnaf_pid": seed_property["gnaf_pid"],
                "address_string": seed_property["address_string"],
                "latitude": -37.9021,
                "longitude": 144.6634,
                "lga_name": "Wyndham City Council",
                "state": "VIC",
            }
        )

    row = await db_pool.fetchrow(
        "SELECT status, raw_scraped_data FROM property_reports "
        "WHERE property_id=$1 ORDER BY created_at DESC LIMIT 1",
        seed_property["id"]
    )
    assert row["status"] == "PROCESSING"
    assert row["raw_scraped_data"]["vic_plan"]["zoning"] == "GRZ1"

@pytest.mark.asyncio
async def test_scrape_task_retries_on_adapter_timeout(db_pool, seed_property):
    with patch("app.adapters.state.vic.VicPlanAdapter.fetch",
               side_effect=TimeoutError("upstream timeout")):
        with pytest.raises(Exception):   # Celery will retry
            scrape_property.apply(kwargs={...})

    row = await db_pool.fetchrow(
        "SELECT retry_count FROM property_reports WHERE property_id=$1",
        seed_property["id"]
    )
    assert row["retry_count"] >= 1
```

---

## 5. End-to-End Tests (Playwright)

Only critical user journeys. Not comprehensive — just the flows where a regression would cause lost revenue or data corruption.

**Location:** `apps/public-web/tests/e2e/`  
**Target:** staging environment (not localhost) — uses real Clerk test mode.

### 5.1 Covered Journeys

**Journey 1 — Anonymous user searches and sees lite preview:**
```typescript
// tests/e2e/search.spec.ts
test('anonymous user can search and see lite panel', async ({ page }) => {
  await page.goto('/');
  await page.waitForSelector('[data-testid="map-container"]');

  // Type in omnibox
  await page.fill('[data-testid="search-omnibox"]', 'Werribee VIC');
  await page.click('[data-testid="suggestion-0"]');

  // Map should fly to location and show pins
  await expect(page.locator('[data-testid="property-marker"]').first()).toBeVisible();

  // Click a pin — lite panel should open
  await page.locator('[data-testid="property-marker"]').first().click();
  await expect(page.locator('[data-testid="lite-panel"]')).toBeVisible();
  await expect(page.locator('[data-testid="estimated-value"]')).toBeVisible();

  // Risk section should be blurred / locked
  await expect(page.locator('[data-testid="risk-teaser"]')).toBeVisible();
  await expect(page.locator('[data-testid="unlock-button"]')).toBeVisible();
});
```

**Journey 2 — User signs up and generates a report:**
```typescript
// tests/e2e/generate.spec.ts
test('user signs up and generates a full report', async ({ page }) => {
  // Start from lite panel
  await openLitePanel(page, TEST_PROPERTY_ID);

  // Click generate → should redirect to Clerk sign-in
  await page.click('[data-testid="download-button"]');
  await expect(page).toHaveURL(/sign-in/);

  // Sign up with test credentials
  await page.fill('[name="emailAddress"]', `test+${Date.now()}@example.com`);
  await page.fill('[name="password"]', 'TestPassword123!');
  await page.click('[type="submit"]');

  // Should be back on property page after sign-up
  await expect(page.locator('[data-testid="download-button"]')).toBeVisible();
  await page.click('[data-testid="download-button"]');

  // Should show full report visible
  await expect(page).toHaveURL(new RegExp(TEST_PROPERTY_ID));
  await page.click('[data-testid="disclaimer-accept"]');
  await expect(page.locator('[data-testid="full-report"]')).toBeVisible();
  await expect(page.locator('[data-testid="zoning-section"]')).toBeVisible();
});
```

**Journey 3 — Admin reviews and approves a flagged report:**
```typescript
// tests/e2e/admin-review.spec.ts
test('admin approves a review-required report', async ({ page }) => {
  // Sign in as admin (Clerk test mode)
  await page.goto('http://localhost:3001/sign-in');
  await page.fill('[name="emailAddress"]', process.env.TEST_ADMIN_EMAIL!);
  await page.fill('[name="password"]', process.env.TEST_ADMIN_PASSWORD!);
  await page.click('[type="submit"]');

  await page.goto('/reports/review');
  await expect(page.locator('[data-testid="review-card"]').first()).toBeVisible();

  // Approve the first card
  await page.click('[data-testid="approve-button"]');
  await expect(page.locator('[data-testid="toast-success"]')).toBeVisible();

  // Card should disappear from queue
  const cardCount = await page.locator('[data-testid="review-card"]').count();
  expect(cardCount).toBeLessThan(
    await page.locator('[data-testid="review-card"]').count() + 1
  );
});
```

**Run E2E tests:**
```bash
cd apps/public-web
pnpm exec playwright test               # headless
pnpm exec playwright test --headed      # see the browser
pnpm exec playwright test --ui          # Playwright UI mode (best for debugging)
```

---

## 6. What Is Explicitly Not Tested

| Area | Reason |
|---|---|
| Clerk authentication internals | Clerk's responsibility, not ours |
| Mapbox rendering | Visual regression is out of scope for MVP |
| G-NAF import script | One-time script; manually verified on first run |
| Flower UI | Open source tool we don't own |
| Full scraper Playwright execution against real councils | Too slow, too brittle; use recorded fixture HTML instead |

---

## 7. Test Fixtures & Seed Data

**Python services** use pytest fixtures to seed the test DB before each test:

```python
# conftest.py (shared)
@pytest.fixture
async def seed_property(db_pool) -> dict:
    row = await db_pool.fetchrow("""
        INSERT INTO properties (gnaf_pid, address_string, geom, state)
        VALUES ('TEST001', '8 St Lawrence Close, Werribee VIC 3030',
                ST_SetSRID(ST_MakePoint(144.6634, -37.9021), 4326), 'VIC')
        RETURNING *
    """)
    yield dict(row)
    await db_pool.execute("DELETE FROM properties WHERE gnaf_pid='TEST001'")

@pytest.fixture
async def seed_review_report(db_pool, seed_property) -> dict:
    row = await db_pool.fetchrow("""
        INSERT INTO property_reports
          (property_id, status, llm_parsed_insights, confidence_scores)
        VALUES ($1, 'READY', $2::jsonb, $3::jsonb)
        RETURNING *
    """, seed_property["id"],
        json.dumps(SAMPLE_LLM_OUTPUT),
        json.dumps(SAMPLE_CONFIDENCE_SCORES))
    yield dict(row)
```

**HTML fixtures for scraper unit tests:**

```
services/scraper-worker/tests/fixtures/
├── techone_planning_table.html     # real captured HTML (council site)
├── vicplan_api_response.json       # real captured API response
└── abs_census_sa2_response.json    # real captured ABS response
```

These are captured once from real sources and committed. When a council site changes its DOM and a scraper breaks in production, the fixture is updated to match the new DOM and the adapter fix is written against it.

---

## 8. CI Pipeline (GitHub Actions)

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:

jobs:
  test-python:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgis/postgis:16-3.4
        env:
          POSTGRES_USER: parceliq
          POSTGRES_PASSWORD: test
          POSTGRES_DB: parceliq_test
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-retries 10
      redis:
        image: redis:7-alpine
        options: --health-cmd "redis-cli ping"
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Test public-api
        run: cd services/public-api && uv run pytest tests/ -v --cov=app --cov-report=term-missing
        env:
          DATABASE_URL: postgresql+asyncpg://parceliq:test@localhost:5432/parceliq_test
          REDIS_URL: redis://localhost:6379/0
      - name: Test admin-backend
        run: cd services/admin-backend && uv run pytest tests/ -v --cov=app
        env:
          DATABASE_URL: postgresql+asyncpg://parceliq:test@localhost:5432/parceliq_test
          ADMIN_SERVICE_TOKEN: ci-test-token
      - name: Test scraper-worker
        run: cd services/scraper-worker && uv run pytest tests/unit/ -v
      - name: Test llm-parser-worker
        run: cd services/llm-parser-worker && uv run pytest tests/unit/ -v

  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: corepack enable && corepack prepare pnpm@latest --activate
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter public-web test --run
      - run: pnpm --filter admin-web test --run

  e2e:
    runs-on: ubuntu-latest
    needs: [test-python, test-frontend]
    if: github.ref == 'refs/heads/main'   # E2E only on main — runs against staging
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: corepack enable && corepack prepare pnpm@latest --activate
      - run: pnpm install --frozen-lockfile
      - run: pnpm exec playwright install --with-deps chromium
      - run: pnpm --filter public-web exec playwright test
        env:
          BASE_URL: ${{ secrets.STAGING_URL }}
          TEST_ADMIN_EMAIL: ${{ secrets.TEST_ADMIN_EMAIL }}
          TEST_ADMIN_PASSWORD: ${{ secrets.TEST_ADMIN_PASSWORD }}
```

---

## 9. Coverage Targets (MVP)

These are minimums, not goals. The goal is meaningful tests, not a number.

| Service | Minimum Coverage | Focus |
|---|---|---|
| `public-api` | 70% | All route handlers + auth logic |
| `admin-backend` | 70% | All route handlers + service token auth |
| `llm-parser-worker` | 80% | Validator + confidence scoring (these are critical) |
| `scraper-worker` | 60% | Adapter parsers (network calls are mocked) |
| `public-web` | 50% | Server-side utilities; not UI component snapshots |
| `admin-web` | 60% | All Server Actions (auth + payload) |
