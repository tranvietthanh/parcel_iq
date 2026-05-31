# OZ Property Report – Quick Start & Testing Guide

> **TL;DR:** Run `make infra-up && make db-migrate`, then `make dev-full` to start all services, then `make test-all` to run all tests.

---

## 1. Prerequisites

**System:**
- Linux or macOS (Windows: WSL2)
- Docker & Docker Compose
- PostgreSQL client (`psql`)
- `pnpm` (for Node/frontend)
- `uv` (for Python)
- `make`

**Verify installation:**
```bash
docker compose --version
psql --version
pnpm --version
uv --version
make --version
```

---

## 2. Initial Setup (One-Time)

### 2a. Clone & Environment

```bash
cd /home/thanhtran/Projects/parcel_iq
```

Check `.env` exists (should be already created):
```bash
cat .env | head -10
# Should show: POSTGRES_USER=parceliq, POSTGRES_PASSWORD=..., etc.
```

### 2b. Start Infrastructure

```bash
# Start Postgres, Redis, MinIO, Flower
make infra-up

# Verify all containers are healthy
docker compose ps
```

You should see all containers with status `Up` (healthy).

### 2c. Create Databases & Run Migrations

```bash
# Create MinIO buckets (raw-scrape-cache, ozpr-db-backups)
make minio-buckets

# Run all 11 Alembic migrations
make db-migrate

# Verify tables were created
make db-shell
# Inside psql:
\dt
# Should list: admin_activity_log, data_source_configs, gnaf_addresses, properties, 
#              property_reports, property_school_catchments, saved_properties, 
#              spatial_zones, unlocked_reports, users
\q
```

### 2d. Install Frontend Dependencies

```bash
# Install all Node packages (root + apps)
pnpm install
```

---

## 3. Running the Full Stack

### 3a. Development Mode (All Services Running)

**Option 1: Start Everything at Once**

```bash
# Starts Postgres, Redis, MinIO, Flower + all 6 services (async)
make dev-full

# Wait ~10 seconds for all services to boot
sleep 10

# Verify all are running:
curl http://localhost:8080/api/health         # Public API
curl http://localhost:8082/stats             # Admin Backend
curl http://localhost:3000                    # Public Web (next dev)
curl http://localhost:3001                    # Admin Web (next dev)
```

**Option 2: Start Services Individually**

If you prefer to control each service:

```bash
# Terminal 1: Infrastructure
make infra-up

# Terminal 2: Public API
cd services/public-api && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# Terminal 3: Admin Backend
cd services/admin-backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8082

# Terminal 4: Scraper Worker
cd services/scraper-worker && uv run celery -A app.celery:app worker -l info -Q data_acquisition_queue

# Terminal 5: LLM Parser Worker
cd services/llm-parser-worker && uv run celery -A app.celery:app worker -l info -Q llm_processing_queue

# Terminal 6: Celery Beat (scheduler)
cd services/llm-parser-worker && uv run celery -A app.celery:app beat -l info

# Terminal 7: Public Web (Next.js dev)
cd apps/public-web && pnpm dev

# Terminal 8: Admin Web (Next.js dev)
cd apps/admin-web && pnpm dev
```

### 3b. Service URLs

Once running, you can access:

| Service | URL | Purpose |
|---------|-----|---------|
| **Public API** | http://localhost:8080 | REST API for investors |
| **Public API Docs** | http://localhost:8080/docs | Swagger OpenAPI |
| **Admin API** | http://localhost:8082 | Admin endpoints (internal only) |
| **Admin API Docs** | http://localhost:8082/docs | Swagger OpenAPI |
| **Public Web** | http://localhost:3000 | Investor-facing app |
| **Admin Web** | http://localhost:3001 | Admin dashboard |
| **Flower** | http://localhost:5555 | Celery task monitor |
| **MinIO** | http://localhost:9001 | S3-compatible storage browser |

---

## 4. Testing

### 4a. Quick Test Summary

```bash
# Run all tests (Python + TypeScript)
make test-all

# Expected output:
#   Public API:     49 tests pass, 83% coverage
#   Admin Backend:  24 tests pass, 73% coverage
#   Scraper Worker: 84 tests pass, 70% coverage
#   LLM Parser:     77 tests pass
#   Public Web:     25 tests pass
#   Admin Web:      (to be created in Phase 7)
#   ─────────────────────
#   Total:          ~260 tests passing
```

### 4b. Test by Service

**Python Services (Unit + Integration):**

```bash
# Public API
cd services/public-api && uv run pytest tests/ -v --cov=app

# Admin Backend
cd services/admin-backend && uv run pytest tests/ -v --cov=app

# Scraper Worker (unit tests only — no Docker needed)
cd services/scraper-worker && uv run pytest tests/unit/ -v --cov=app

# LLM Parser Worker (unit + integration)
cd services/llm-parser-worker && uv run pytest tests/ -v --cov=app
```

**Frontend (TypeScript):**

```bash
# Public Web
cd apps/public-web && pnpm test

# Admin Web (once created)
cd apps/admin-web && pnpm test
```

### 4c. Integration Test Prerequisites

Some tests require running infrastructure. Make sure these services are up before running integration tests:

```bash
# Required for API/worker tests:
docker compose ps | grep -E "postgres|redis"

# If not running:
make infra-up

# Run migrations (required for API tests):
make db-migrate

# Then run API integration tests:
cd services/public-api && uv run pytest tests/integration/ -v
```

### 4d. Test Coverage Report

```bash
# Generate HTML coverage report for a service
cd services/public-api && uv run pytest tests/ --cov=app --cov-report=html

# Open in browser
open htmlcov/index.html
```

---

## 5. Manual Testing (Happy Path)

### 5a. Public API — Search & Property Lookup

```bash
# 1. Search by bounding box (Sydney area)
curl "http://localhost:8080/api/search?bbox=150.5,-34.1,152.0,-33.5" \
  -H "Turnstile-Token: dummy-token-for-dev"

# Expected: GeoJSON FeatureCollection with property pins

# 2. Text search (suburbs, postcodes, addresses)
curl "http://localhost:8080/api/search?q=Paddington" \
  -H "Turnstile-Token: dummy-token-for-dev"

# Expected: Search results array

# 3. Get lite property preview (no auth)
curl "http://localhost:8080/api/properties/some-uuid/lite"

# Expected: {address, suburb, beds, baths, etc.}

# 4. Get zones (LGA boundaries, school catchments)
curl "http://localhost:8080/api/search/zones?type=lga"

# Expected: GeoJSON polygon features
```

### 5b. Admin API — Trigger Scrape

```bash
# 1. Get dashboard stats
curl -H "X-Service-Token: dev-service-token-change-in-prod" \
  http://localhost:8082/stats

# Expected: {properties_count, reports_count, failed_reports, etc.}

# 2. Trigger a scrape for a property
curl -X POST \
  -H "X-Service-Token: dev-service-token-change-in-prod" \
  -H "Content-Type: application/json" \
  -d '{"property_id": "some-uuid", "adapters": ["VicPlanAdapter"]}' \
  http://localhost:8082/scrape/trigger

# Expected: {job_id: "..."}

# 3. Check scrape history
curl -H "X-Service-Token: dev-service-token-change-in-prod" \
  http://localhost:8082/scrape/history
```

### 5c. Public Web — Interactive Map

1. Open **http://localhost:3000** in your browser
2. You should see:
   - **Mapbox map** (Sydney, zoom 5) with pins for any loaded properties
   - **Search omnibox** (top-left) — type "Paddington" → should show autocomplete
   - **User avatar** (top-right) — click to sign in/up
3. **Click a pin** → lite panel slides in from right with:
   - Address, beds, baths, cars, land, estimated value, gross yield
   - School catchments
   - "Generate Full Report" button (blurred risk section)
4. **Sign in** → click "Generate Full Report" → full report generation triggered
5. **After generation** → full report shows with:
   - Risk assessment (flood, bushfire, contamination)
   - Planning details (zoning, FSR, heritage)
   - Disclaimer gate (must acknowledge before viewing)

### 5d. Admin Web (Coming in Phase 7)

Will include:
- Dashboard with stats & queue health
- Report review queue
- Scrape trigger form
- Data source management
- Embedded Flower task monitor

---

## 6. Debugging & Logs

### 6a. View Logs

```bash
# All infrastructure services
make infra-logs

# Specific service (e.g., Postgres)
docker compose logs -f postgres

# Python API service (terminal running the service)
# — Look for "INFO: Application startup complete"

# Next.js frontend (terminal running `pnpm dev`)
# — Look for "ready - started server on 0.0.0.0:3000"

# Celery worker task logs
# — Should show "[tasks] Received..." and "[tasks] Task...succeeded"
```

### 6b. Database Shell

```bash
# Open psql to local database
make db-shell

# Useful queries:
SELECT count(*) FROM properties;               # Property count
SELECT status, count(*) FROM property_reports  # Report status breakdown
  GROUP BY status;
SELECT * FROM admin_activity_log               # Admin audit log
  ORDER BY created_at DESC LIMIT 10;
SELECT name, message FROM celery_taskmeta      # Celery task results (if stored)
  ORDER BY date_done DESC LIMIT 5;
```

### 6c. Redis CLI

```bash
# Connect to Redis
docker compose exec redis redis-cli

# Useful commands:
KEYS "*"                    # List all keys
GET key-name                # Get a value
HGETALL celery_results_meta # Celery task metadata
FLUSHDB                      # Clear everything (dev only)
```

### 6d. MinIO Browser

```bash
# Open http://localhost:9001
# Login: minioadmin / minioadmin
# Browse: raw-scrape-cache, ozpr-db-backups buckets
```

---

## 7. Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| `psql: could not connect to localhost:5432` | Postgres not running | `make infra-up` |
| `ModuleNotFoundError: No module named 'app'` | Wrong working directory | `cd services/public-api` before `uv run` |
| `pnpm: command not found` | pnpm not installed | `npm install -g pnpm` |
| `ImportError: asyncpg` | Dependencies not synced | `cd services/public-api && uv sync` |
| API returns 422 on POST | Request body missing/malformed | Check `-d '...'` JSON syntax |
| Map doesn't load at localhost:3000 | Mapbox token missing | Set `NEXT_PUBLIC_MAPBOX_TOKEN` in `.env.local` |
| "Turnstile token invalid" on search | Turnstile disabled in dev | Add `-H "Turnstile-Token: dummy"` to curl |
| Celery tasks don't run | Worker not running | Start worker: `cd services/scraper-worker && uv run celery -A app.celery:app worker` |

---

## 8. Clean Up & Reset

```bash
# Stop all services (keep data)
make infra-down

# Stop and DESTROY all data (fresh start)
make infra-reset

# Full reset: destroy volumes + re-run migrations
make db-reset

# Clean up build artifacts (Node/Python)
pnpm clean                              # Clear pnpm cache
rm -rf apps/public-web/.next            # Clear Next.js build
cd services/public-api && rm -rf .venv  # Clear Python venv (if using)
```

---

## 9. Production-Like Testing

### 9a. Build Docker Images

```bash
# Build all service images (using docker-compose)
docker compose build

# Verify images were created
docker images | grep parceliq
```

### 9b. Run Tests in Docker

```bash
# Run Public API tests in container
docker compose run --rm public-api uv run pytest tests/ -v

# Run Scraper Worker tests in container
docker compose run --rm scraper-worker uv run pytest tests/unit/ -v
```

### 9c. Standalone Frontend Build

```bash
# Build Next.js for production
cd apps/public-web && pnpm build

# Start production server
pnpm start

# Should serve on http://localhost:3000 with optimized output
```

---

## 10. Feature Checklist (Phase 6)

After starting the stack, verify these work:

- [ ] **Map loads** — http://localhost:3000 shows Mapbox
- [ ] **Search works** — Omnibox returns results in < 300ms
- [ ] **Pins render** — Bbox search returns GeoJSON pins
- [ ] **Lite panel opens** — Click pin → panel slides in
- [ ] **Clustering** — Zoom out to see cluster groups
- [ ] **Sign in** — Clerk modal appears (dev instance)
- [ ] **Generate button** — Routes to property detail page
- [ ] **Disclaimer gate** — Must acknowledge before viewing
- [ ] **All tests pass** — `make test-all` returns success

---

## 11. Next Steps

1. **Start the stack:** `make infra-up && make db-migrate && make dev-full`
2. **Run tests:** `make test-all`
3. **Visit the app:** http://localhost:3000
4. **Review logs:** `docker compose logs -f`
5. **Check Phase 7:** Admin Web (coming next)
6. **Then Phase 8:** Infrastructure, E2E tests, and launch prep

---

## Useful Make Commands

```bash
make help              # Show all available Makefile commands
make infra-up          # Start infrastructure
make infra-down        # Stop infrastructure
make db-migrate        # Run migrations
make db-shell          # Open psql
make dev-full          # Start all services (async)
make test-all          # Run all tests
make test-python       # Run Python tests only
make test-frontend     # Run Node/TypeScript tests only
make minio-buckets     # Create MinIO buckets
make infra-logs        # Tail all container logs
make infra-status      # Show container status
```

**For detailed command docs:**
```bash
make help
```

---

## Questions? Issues?

Check:
- **Logs:** `make infra-logs` or service terminal output
- **Migrations:** `make db-history` to see migration state
- **Health:** Curl service health endpoints (e.g., `curl http://localhost:8080/api/health`)
- **Docs:** Read `docs/09-local-dev.md` for deeper dev setup
