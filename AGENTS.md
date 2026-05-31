# AGENTS.md

Guidance for AI coding agents (Claude Code, Cursor, Copilot, etc.) working on this codebase. Read this before making any changes.

---

## What This Project Is

OZ Property Report is a property intelligence platform for Australian real estate investors. It aggregates public government data, processes it through an LLM pipeline, and presents tiered access — a free Lite Preview and a paid Full Report. The codebase is a pnpm + Python monorepo with two Next.js apps, two FastAPI services, two Celery workers, shared infrastructure, and a PDF renderer.

---

## Non-Negotiable Architecture Rules

**1. The Admin Backend API has no internet ingress. Never add one.**
`services/admin-backend` is a ClusterIP-only service. It is only reachable from the `admin-web` pod via K8s NetworkPolicy. Do not add a Traefik ingress, do not add a LoadBalancer service. If the admin app needs a new backend operation, add it to `services/admin-backend` and call it from a Server Action in `apps/admin-web`.

**2. The admin app uses Server Actions — not client-side API calls.**
`apps/admin-web` must never `fetch()` the Admin Backend API from a client component. All calls to `services/admin-backend` must go through Server Actions in `apps/admin-web/actions/`. The base wrapper is `apps/admin-web/lib/admin-action.ts`. Use it for every new admin operation.

**3. Two Clerk instances — never cross them.**
`apps/public-web` uses the `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` for the **public** Clerk instance. `apps/admin-web` uses a different `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` for the **admin** Clerk instance. The env vars have the same name but different values in each app's `.env.local`. Do not import Clerk from one app into the other.

**4. Postgres and Redis are internal only.**
Never expose port 5432 or 6379 outside the cluster. Never add connection strings to client-side code or Next.js `NEXT_PUBLIC_` vars.

**5. Admin users are not in the `users` table.**
The `users` table stores public investors keyed by `clerk_user_id`. Admin users exist only in the Clerk Admin Instance dashboard. `admin_activity_log` stores `clerk_admin_id` as a plain string — there is no FK to `users`. Do not try to look up admins in the `users` table.

---

## Where Things Live

```
apps/public-web/          Investor-facing Next.js app (Clerk public instance)
  app/(map)/              Main map layout: property, suburb, school detail pages
  components/             React components (map, property, UI)
  lib/                    Utilities: API client, JSON-LD helpers, slug utils
  hooks/                  Custom React hooks
apps/admin-web/           Admin Next.js app (Clerk admin, Server Actions only)
  actions/                All Server Actions — one file per domain
  app/api/flower/         Flower proxy Route Handler (Clerk-gated)
  lib/admin-action.ts     Base wrapper for all admin backend calls

services/public-api/      FastAPI — internet-facing, Clerk JWT verification (port 8080)
services/admin-backend/   FastAPI — internal only, X-Service-Token verification (port 8082)
services/scraper-worker/  Celery workers + Playwright adapters
services/llm-parser-worker/ Celery workers + LLM (Gemini or NVIDIA via factory pattern)

shared/db-migrations/     Alembic — single source of truth for schema
shared/py-types/          Shared Pydantic models used across Python services
shared/pdf-renderer/      PDF generation service

infra/k8s/                K8s manifests (deployments, services, network policies)
infra/scripts/            Data import and setup scripts (GNAF, schools, spatial zones)
docs/                     All specification documents
openspec/                 Change management (proposals, designs, tasks)
data/                     Spatial data files (shapefiles, CSVs)
```

---

## Before You Write Code

1. **Check the relevant spec doc in `docs/`.** Architecture decisions, DB schema, API contracts, and adapter patterns are fully specified. Do not invent new patterns — follow what's documented.

2. **For any new DB column or table**, add an Alembic migration in `shared/db-migrations/versions/`. Never use raw `ALTER TABLE` in application code.

3. **For a new LGA scraper adapter**, extend `BaseAdapter` in `services/scraper-worker/app/adapters/base.py` and register it in the adapter registry. Then insert a row into `data_source_configs` — no code changes needed for the dispatch path.

4. **For a new admin operation:**
   - Add the endpoint to `services/admin-backend/app/routers/`
   - Add the Server Action to `apps/admin-web/actions/`
   - Add the UI to `apps/admin-web/app/`
   - Never skip the Server Action layer.

---

## Code Style

**Python:** `uv` for dependency management, `ruff` for linting, `black` for formatting. Type hints everywhere. Pydantic v2 for all data validation — use `model_validate`, `model_dump`, and strict mode where appropriate.

**Python Virtual Environments:** Each Python service and shared package has its own `.venv/` directory managed by `uv`:
- `services/public-api/` → `cd services/public-api && uv sync`
- `services/admin-backend/` → `cd services/admin-backend && uv sync`
- `services/scraper-worker/` → `cd services/scraper-worker && uv sync`
- `services/llm-parser-worker/` → `cd services/llm-parser-worker && uv sync`
- `shared/db-migrations/` → `cd shared/db-migrations && uv sync`
- `shared/pdf-renderer/` → `cd shared/pdf-renderer && uv sync`
- `infra/scripts/` → `cd infra/scripts && uv sync`

**Do not activate venvs manually.** Use `uv run` (e.g., `uv run pytest ...`) which automatically uses the local `.venv/`. The `.venv/` directories are git-ignored; only `uv.lock` is committed for reproducibility.

**TypeScript:** `pnpm` for packages, ESLint + Prettier. Prefer `type` over `interface`. All Server Actions are in `apps/admin-web/actions/` and marked `'use server'`. All client components are marked `'use client'`. Default to Server Components.

**SQL:** All queries use asyncpg's parameterised `$1, $2` syntax. Never f-string SQL. Spatial queries always include explicit SRID (`4326`).

---

## Development Commands

### Setup (First Time)
```bash
corepack enable && corepack prepare pnpm@latest --activate
pnpm install
make py-sync
make infra-up
make db-migrate
make minio-buckets
make playwright-install
```

### Running Services
```bash
make api-public        # Public API (port 8080)
make api-admin         # Admin Backend API (port 8082)
make worker-scraper    # Scraper Worker (Celery)
make worker-llm        # LLM Parser Worker (Celery)
make web-public        # Public Web (port 3000)
make web-admin         # Admin Web (port 3001)
make dev-full          # Print all commands for running everything
```

### Infrastructure
```bash
make infra-up          # Start Docker (Postgres, Redis, MinIO, Flower)
make infra-down        # Stop containers
make infra-reset       # Wipe all data volumes
make infra-status      # Show Docker status
make infra-logs        # Tail infrastructure logs
```

### Database
```bash
make db-migrate                      # Run all pending migrations
make db-rollback                     # Roll back one migration
make db-revision msg="add_foo"       # Create new migration
make db-history                      # Show migration history
make db-shell                        # Open psql shell
make db-reset                        # Wipe DB + re-migrate (destructive)
```

### Testing
```bash
make test-public-api     # Public API unit tests
make test-admin-backend  # Admin Backend unit tests
make test-scraper        # Scraper Worker unit tests
make test-llm            # LLM Parser unit tests
make test-python         # All Python tests
make test-frontend       # All frontend tests (Vitest)
make test-all            # All tests
```

### Data Import
```bash
make import-spatial-zones type=LGA source=/path/to/shapefile
make import-spatial-zones type=SUBURB source=/path/to/shapefile
make import-spatial-zones type=SCHOOL_CATCHMENT source=/path/to/shapefile
make import-schools source=/path/to/csv state=VIC
make import-gnaf source=/path/to/gnaf.zip
make create-properties state=VIC limit=10000 batch=1000
```

### Build & Deploy
```bash
make web-build                    # Build both Next.js apps
make build-docker tag=<tag>       # Build all 7 Docker images
make deploy tag=<tag>             # Push images and deploy to K3s
make k8s-secrets                  # Apply secrets from .env to cluster
make k8s-status                   # Show all K8s resources
make k8s-logs svc=<service>       # Tail logs for a deployment
make k8s-admin                    # Port-forward admin surfaces
make k8s-hosts                    # Print /etc/hosts entries for cluster
make k8s-init-data lga_source=... # Bootstrap VIC reference data
```

---

## Running Tests

```bash
# Python unit tests (fast, no Docker needed)
cd services/public-api && uv run pytest tests/unit/ -v
cd services/llm-parser-worker && uv run pytest tests/unit/ -v

# Python integration tests (needs Postgres + Redis running)
docker compose up -d postgres redis
cd services/public-api && uv run pytest tests/integration/ -v

# TypeScript tests
pnpm --filter public-web test --run
pnpm --filter admin-web test --run

# E2E (needs staging environment)
pnpm --filter public-web exec playwright test
```

Full testing guide: [`docs/10-testing-strategy.md`](docs/10-testing-strategy.md)

---

## Documentation

All specifications are in `docs/`:
- `01-system-architecture.md` — Architecture, security model, data flows
- `02-frontend.md` — Public app components, Clerk integration, SEO patterns
- `03-api-gateway.md` — Public API endpoints and contracts
- `04-database.md` — Full DDL, indexes, JSONB schemas
- `05-scraper-worker.md` — Adapter pattern, national scrape strategy
- `06-llm-parser-worker.md` — LLM provider config (Gemini/NVIDIA), confidence scoring
- `07-legal-compliance.md` — AFSL risk, disclaimers, scraping compliance
- `08-admin-console.md` — Admin app, Server Actions, Admin Backend API
- `09-local-dev.md` — Full local dev setup and debugging guide
- `10-testing-strategy.md` — Test tools, patterns, CI pipeline
- `11-first-time-data-population.md` — Initial data seeding pipeline for production
- `12-school-data-sources.md` — School data sources and import process
- `deployment-guide.md` — K3s production deployment guide

---

## Common Mistakes to Avoid

| Mistake | Why it's wrong |
|---|---|
| Adding `NEXT_PUBLIC_ADMIN_BACKEND_URL` to admin-web | Exposes internal URL to browser; use Server Actions |
| Calling `fetch('http://admin-backend:...')` in a client component | Admin backend is internal only; must go through Server Action |
| Adding `password_hash` or `role` column to `users` table | Clerk owns auth; users table stores only `clerk_user_id` |
| Creating a new Alembic migration without running existing ones first | Will cause conflicts; always `alembic upgrade head` before `revision --autogenerate` |
| Using `npm` or `yarn` in any JS context | This repo uses `pnpm` exclusively |
| Disabling `review_flag` check to speed up development | Reports must go through review if LLM confidence is low — this is a legal risk mitigation |
| Importing from one app into another | `apps/public-web` and `apps/admin-web` are independent — no cross-imports |
| Setting `FLOWER_BASIC_AUTH` | Flower auth is handled by the Admin Backend API proxy layer; Flower itself has no auth |
| Activating venvs manually (`source .venv/bin/activate`) | Use `uv run` instead — it auto-selects the correct local `.venv/` |
