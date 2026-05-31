# ParcelIQ

Map-centric property intelligence platform for Australian real estate investors. Aggregates public government data, processes it through an LLM pipeline, and presents tiered access (Lite preview + Full report).

## Production Access

- Public web: https://ozpropertyreport.com
- Public API: not exposed as a separate public domain (accessed via public-web `/api` routes)
- Admin web: not publicly exposed via ingress (internal/admin access only)

## Architecture at a Glance

```
ozpropertyreport.com                 Admin Web (Next.js 16)
(Next.js 16)                         (internal access only, no public ingress)
      │                                     │
      ▼                                     ▼ (K8s internal)
Public API (FastAPI)                  Admin Backend API (FastAPI, no internet ingress)
      │                                     │
      └──────────────────┬──────────────────┘
             │
        PostgreSQL + PostGIS
        Redis (Celery broker)
        Scraper Workers (Playwright)
        LLM Parser Workers
```

**Auth:** Two separate Clerk instances — public (Email + Google OAuth) and admin (invite-only org, Server Actions gate access to the internal-only Admin Backend API).

## Repository Layout

```
apps/
  public-web/          # Investor-facing Next.js app
  admin-web/           # Admin Next.js app (Server Actions → admin backend)
services/
  public-api/          # FastAPI — internet-facing
  admin-backend/       # FastAPI — internal only (no ingress)
  scraper-worker/      # Celery + Playwright — national data acquisition
  llm-parser-worker/   # Celery + provider-configurable LLM parsing
shared/
  db-migrations/       # Alembic migrations (single source of truth)
  py-types/            # Shared Pydantic models
infra/
  k8s/                 # Kubernetes manifests and network policies
  scripts/             # G-NAF import, bucket setup
docs/
  01-system-architecture.md
  02-frontend.md
  03-api-gateway.md
  04-database.md
  05-scraper-worker.md
  06-llm-parser-worker.md
  07-legal-compliance.md
  08-admin-console.md
  09-local-dev.md
  10-testing-strategy.md
docker-compose.yml     # Local dev infrastructure (Postgres, Redis, MinIO, Flower)
README.md
AGENTS.md
```

## Quick Start (Local Dev)

```bash
# 1. Prerequisites: Node.js 22, Python 3.12, uv, Docker
corepack enable && corepack prepare pnpm@latest --activate

# 2. Install dependencies
pnpm install
cd services/public-api && uv sync && cd ../..
cd services/admin-backend && uv sync && cd ../..
cd services/scraper-worker && uv sync && cd ../..
cd services/llm-parser-worker && uv sync && cd ../..

# 3. Configure environment
cp .env.example .env
# copy and fill .env.local / .env files — see docs/09-local-dev.md

# 4. Start infrastructure + run migrations
make infra-up
make db-migrate

# 5. Start services
# Option A: print the recommended 6-terminal commands
make dev-full
# Option B: run frontend apps only
pnpm dev
```

Full setup guide: [`docs/09-local-dev.md`](docs/09-local-dev.md)

## Service Ports (Local)

| Service | Port |
|---|---|
| Public App | 3000 |
| Admin App | 3001 |
| Public API | 8080 |
| Admin Backend API | 8082 |
| Flower | 5555 |
| MinIO Console | 9001 |
| Postgres | 5432 |

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, TypeScript, Tailwind CSS, Mapbox GL JS |
| Package manager | pnpm (workspaces) |
| Backend | Python 3.12, FastAPI, asyncpg, Pydantic v2 |
| Task queue | Celery, Redis |
| Database | PostgreSQL 16 + PostGIS 3.4 |
| Auth | Clerk (two instances) |
| Scraping | Playwright (Python) |
| LLM | Provider-configurable worker (Gemini / NVIDIA / OpenAI-compatible) |
| Observability | Grafana Loki + structlog |
| Object storage | MinIO (S3-compatible) |
| Deployment | K3s (manifests under infra/k8s) |
| Migrations | Alembic |

## Key Documents

| Doc | Contents |
|---|---|
| [`01-system-architecture`](docs/01-system-architecture.md) | Full architecture, security model, data flows |
| [`02-frontend`](docs/02-frontend.md) | Public app component spec, Clerk integration |
| [`03-api-gateway`](docs/03-api-gateway.md) | Public API endpoints and contracts |
| [`04-database`](docs/04-database.md) | Full DDL, indexes, JSONB schemas |
| [`05-scraper-worker`](docs/05-scraper-worker.md) | Adapter pattern, national scrape strategy |
| [`06-llm-parser-worker`](docs/06-llm-parser-worker.md) | LLM integration, validation, confidence scoring |
| [`07-legal-compliance`](docs/07-legal-compliance.md) | AFSL risk, disclaimers, scraping compliance |
| [`08-admin-console`](docs/08-admin-console.md) | Admin app, Server Actions, Admin Backend API |
| [`09-local-dev`](docs/09-local-dev.md) | Full local dev setup and debugging guide |
| [`10-testing-strategy`](docs/10-testing-strategy.md) | Test tools, patterns, CI pipeline |
