# OZ Property Report – Local Development Workflow

## 1. Philosophy

| Layer | How it runs locally | Why |
|---|---|---|
| PostgreSQL, PostGIS | Docker Compose | Stateful, no value in running natively |
| Redis | Docker Compose | Stateful, no value in running natively |
| MinIO | Docker Compose | Stateful, S3-compatible object storage |
| Flower | Docker Compose | Depends on Redis, no code to debug |
| Public App | `pnpm dev` (native) | Hot reload, React Fast Refresh |
| Admin App | `pnpm dev` (native) | Hot reload, Server Actions |
| Public API | `uvicorn --reload` (native) | Hot reload, Python debugger, stdout |
| Admin Backend API | `uvicorn --reload` (native) | Hot reload, Python debugger, stdout |
| Scraper Worker | `celery worker` (native) | Step-through debugging, direct stdout |
| LLM Parser Worker | `celery worker` (native) | Step-through debugging, direct stdout |

The rule: **if it has application code you wrote, run it natively. If it's infrastructure you configure, run it in Docker.**

---

## 2. Prerequisites

Install these once on your dev machine:

```bash
# Runtime dependencies
brew install node@22 python@3.12 uv postgresql-client redis-cli

# Infrastructure tools
brew install docker docker-compose

# Enable pnpm via corepack (ships with Node.js — no separate install)
corepack enable
corepack prepare pnpm@latest --activate

# Python dev tools (no virtualenv needed — uv handles this per-project)
pip install uv

# Playwright browsers (for scraper worker)
cd services/scraper-worker
uv run playwright install chromium
```

---

## 3. Repository Setup (First Time Only)

```bash
git clone git@github.com:your-org/parceliq.git
cd parceliq

# Install all Node.js dependencies across all apps (pnpm workspaces)
pnpm install   # reads pnpm-workspace.yaml, installs apps/public-web + apps/admin-web

# Create Python virtual environments for all services
cd services/public-api && uv sync && cd ../..
cd services/admin-backend && uv sync && cd ../..
cd services/scraper-worker && uv sync && cd ../..
cd services/llm-parser-worker && uv sync && cd ../..
cd shared/db-migrations && uv sync && cd ../..  # needed to run migrations

# Copy env files
cp .env.example .env
cp apps/public-web/.env.example apps/public-web/.env.local
cp apps/admin-web/.env.example apps/admin-web/.env.local
cp services/public-api/.env.example services/public-api/.env
cp services/admin-backend/.env.example services/admin-backend/.env
cp services/scraper-worker/.env.example services/scraper-worker/.env
cp services/llm-parser-worker/.env.example services/llm-parser-worker/.env

# Fill in API keys — see Section 4 for what's needed
```

---

## 4. Environment Files

### Root `.env` (shared values, sourced by Docker Compose)

```env
# Infrastructure — same values used by both Docker and native processes
POSTGRES_USER=parceliq
POSTGRES_PASSWORD=devpassword
POSTGRES_DB=parceliq
POSTGRES_PORT=5432

REDIS_PORT=6379

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_PORT=9000
MINIO_CONSOLE_PORT=9001

FLOWER_PORT=5555
```

### `apps/public-web/.env.local`

```env
# Clerk — Public Instance (create at clerk.com, configure Email + Google OAuth)
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
CLERK_WEBHOOK_SECRET=whsec_...         # from Clerk dashboard → Webhooks

# Internal
INTERNAL_WEBHOOK_SECRET=dev-webhook-secret-change-in-prod

# Services
# Client requests use relative /api paths; server-side fetches default to localhost:8080.
NEXT_PUBLIC_MAPBOX_TOKEN=pk.eyJ1...    # from mapbox.com
NEXT_PUBLIC_TURNSTILE_SITE_KEY=1x00000000000000000000AA   # Cloudflare test key (always passes)
```

### `apps/admin-web/.env.local`

```env
# Clerk — Admin Instance (separate Clerk app, email/password only)
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_admin_...
CLERK_SECRET_KEY=sk_test_admin_...
CLERK_ADMIN_ORG_ID=org_...             # your org ID from Clerk dashboard

# Admin Backend API — in dev, running natively on localhost:8082
ADMIN_BACKEND_URL=http://localhost:8082
ADMIN_SERVICE_TOKEN=dev-service-token-change-in-prod
```

### `services/public-api/.env`

```env
DATABASE_URL=postgresql+asyncpg://parceliq:devpassword@localhost:5432/parceliq
REDIS_URL=redis://localhost:6379/0
CLERK_PUBLIC_JWKS_URL=https://<your-clerk-public-instance>.clerk.accounts.dev/.well-known/jwks.json
TURNSTILE_SECRET_KEY=1x0000000000000000000000000000000AA   # Cloudflare test secret (always passes)
RESEND_API_KEY=re_...
INTERNAL_WEBHOOK_SECRET=dev-webhook-secret-change-in-prod
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

### `services/admin-backend/.env`

```env
DATABASE_URL=postgresql+asyncpg://parceliq:devpassword@localhost:5432/parceliq
REDIS_URL=redis://localhost:6379/0
ADMIN_SERVICE_TOKEN=dev-service-token-change-in-prod
FLOWER_INTERNAL_URL=http://localhost:5555
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

### `services/scraper-worker/.env`

```env
DATABASE_URL=postgresql+psycopg2://parceliq:devpassword@localhost:5432/parceliq
REDIS_URL=redis://localhost:6379/0
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_USE_SSL=false
# Proxy not needed for local dev — adapters that need it will skip gracefully
PROXY_URL=
WORKER_CONCURRENCY=1    # single concurrency for easier debugging
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

### `services/llm-parser-worker/.env`

```env
DATABASE_URL=postgresql+psycopg2://parceliq:devpassword@localhost:5432/parceliq
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk-...           # from platform.openai.com
OPENAI_MODEL=gpt-3.5-turbo      # or gpt-4o-mini, gpt-4o for higher quality
OPENAI_DAILY_QUOTA=1000         # conservative for dev
OPENAI_MAX_RPM=60
RESEND_API_KEY=re_...           # from resend.com — needed for report-ready emails
PUBLIC_WEB_URL=http://localhost:3000  # points users to local public app
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

---

## 5. Docker Compose (`docker-compose.yml`)

Infrastructure only — no application code in here.

```yaml
version: "3.9"

services:

  postgres:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "${POSTGRES_PORT}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "${REDIS_PORT}:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":${MINIO_CONSOLE_PORT}"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    ports:
      - "${MINIO_PORT}:9000"
      - "${MINIO_CONSOLE_PORT}:9001"
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5

  flower:
    image: mher/flower:2.0
    environment:
      CELERY_BROKER_URL: redis://redis:6379/0
      FLOWER_PORT: ${FLOWER_PORT}
    ports:
      - "${FLOWER_PORT}:5555"
    depends_on:
      redis:
        condition: service_healthy

volumes:
  postgres_data:
  redis_data:
  minio_data:
```

> Flower in Docker Compose is fine for local dev — the admin-web Server Action's `FLOWER_INTERNAL_URL` points to `http://localhost:5555` in dev, unlike production where it's `http://flower:5555`.

---

## 6. Starting Everything

### Step 1 — Start Infrastructure

```bash
# From repo root
docker compose up -d

# Verify everything is healthy
docker compose ps
# Should show postgres, redis, minio, flower all as "healthy"
```

### Step 2 — Run Database Migrations

```bash
# From repo root — run once, or after pulling new migrations
cd shared/db-migrations
DATABASE_URL=postgresql://parceliq:devpassword@localhost:5432/parceliq \
  uv run alembic upgrade head
```

### Step 3 — Start Application Services

Open **6 terminal tabs**, one per service:

**Terminal 1 — Public API**
```bash
cd services/public-api
uv run uvicorn app.main:app --reload --port 8080 --log-level debug
# Hot reloads on any .py file change
# OpenAPI docs at http://localhost:8080/docs
```

**Terminal 2 — Admin Backend API**
```bash
cd services/admin-backend
uv run uvicorn app.main:app --reload --port 8082 --log-level debug
# Hot reloads on any .py file change
# OpenAPI docs at http://localhost:8082/docs
```

**Terminal 3 — Scraper Worker**
```bash
cd services/scraper-worker
uv run celery -A app.celery_app worker \
  --queues data_acquisition_queue \
  --concurrency 1 \
  --loglevel debug \
  --pool solo      # solo pool = single thread, plays nicely with Python debuggers
```

**Terminal 4 — LLM Parser Worker**
```bash
cd services/llm-parser-worker
uv run celery -A app.celery_app worker \
  --queues llm_processing_queue \
  --concurrency 1 \
  --loglevel debug
```

Use `--pool solo` only when attaching a debugger. For normal local runs, keeping the
default prefork pool avoids false missed-heartbeat warnings while the LLM task blocks
on network I/O.

**Terminal 5 — Public App**
```bash
cd apps/public-web
pnpm dev
# http://localhost:3000
```

**Terminal 6 — Admin App**
```bash
cd apps/admin-web
pnpm dev
# http://localhost:3001
```

---

## 7. Single Command Alternative (Turbo + pnpm)

If you want to start everything in one command instead of 6 terminals. Turbo is run via pnpm — no global install needed.

```json
// turbo.json  (repo root)
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "dev": {
      "persistent": true,
      "cache": false
    }
  }
}
```

```yaml
# pnpm-workspace.yaml  (repo root)
packages:
  - "apps/*"
```

```json
// package.json  (repo root)
{
  "packageManager": "pnpm@9",
  "scripts": {
    "dev":        "turbo run dev --parallel",
    "infra:up":   "docker compose up -d",
    "infra:down": "docker compose down",
    "db:migrate": "cd shared/db-migrations && DATABASE_URL=postgresql://parceliq:devpassword@localhost:5432/parceliq uv run alembic upgrade head",
    "dev:full":   "pnpm infra:up && pnpm db:migrate && pnpm dev"
  },
  "devDependencies": {
    "turbo": "^2"
  }
}
```

```json
// apps/public-web/package.json
{ "scripts": { "dev": "next dev --port 3000" } }

// apps/admin-web/package.json
{ "scripts": { "dev": "next dev --port 3001" } }
```

Then just:
```bash
pnpm dev:full
# Starts Docker infra + runs migrations + starts all 6 app services
# Turbo prefixes each service's output with its name and a distinct colour
```

---

## 8. Service URLs (Local)

| Service | URL | Notes |
|---|---|---|
| Public App | http://localhost:3000 | Next.js dev server |
| Admin App | http://localhost:3001 | Next.js dev server |
| Public API | http://localhost:8080 | FastAPI |
| Public API Docs | http://localhost:8080/docs | OpenAPI (dev only) |
| Admin Backend API | http://localhost:8082 | FastAPI |
| Admin Backend Docs | http://localhost:8082/docs | OpenAPI (dev only) |
| Flower | http://localhost:5555 | Celery monitor (direct in dev) |
| MinIO Console | http://localhost:9001 | Object storage UI |
| Postgres | localhost:5432 | Connect with any DB client |

---

## 9. Dev-Specific Behaviour

### Clerk in Development

Clerk provides **test mode** instances — sign in works normally but no real emails are sent and no billing occurs. Use `pk_test_*` / `sk_test_*` keys from the Clerk dashboard.

For the Clerk webhook (`user.created` → sync to DB): in development you need to expose your local Next.js server to the internet so Clerk can POST to it. Use ngrok:

```bash
# In a separate terminal
ngrok http 3000
# Copy the https://xxxx.ngrok.io URL
# In Clerk dashboard → Webhooks → set endpoint to https://xxxx.ngrok.io/api/webhooks/clerk
```

Alternatively, skip the webhook entirely during local dev and manually insert a test user:

```sql
INSERT INTO users (clerk_user_id, email)
VALUES ('user_dev_test_123', 'dev@example.com');
```

### Cloudflare Turnstile in Development

The `.env` files above use Cloudflare's **always-pass test keys**:
- Site key: `1x00000000000000000000AA`
- Secret key: `1x0000000000000000000000000000000AA`

These bypass the actual Turnstile challenge so you can use the search API without browser automation.



### Admin Backend API Authentication

In dev, the Server Action calls `http://localhost:8082` with `ADMIN_SERVICE_TOKEN=dev-service-token-change-in-prod`. You can also call it directly with curl for testing:

```bash
curl -H "X-Service-Token: dev-service-token-change-in-prod" \
     -H "X-Admin-User-Id: dev-admin" \
     http://localhost:8082/stats
```

### Running a Test Scrape

The fastest way to test the full on-demand pipeline locally:

```bash
# 1. Make sure scraper worker and LLM parser worker are running (Terminals 3 + 4)

# 2. Insert a test property if G-NAF hasn't been imported yet
psql postgresql://parceliq:devpassword@localhost:5432/parceliq -c "
  INSERT INTO properties (gnaf_pid, address_string, geom, state)
  VALUES (
    'TEST001',
    '8 St Lawrence Close, Werribee VIC 3030',
    ST_SetSRID(ST_MakePoint(144.6634, -37.9021), 4326),
    'VIC'
  ) ON CONFLICT DO NOTHING
  RETURNING id;
"
# Note the returned UUID — you'll need it in step 3

# 3. Trigger a scrape via the Public API (on-demand flow)
#    Replace <PROPERTY_ID> with the UUID from step 2
#    Get a Clerk test token, or use an unauthenticated request (lower priority queue)
curl -X POST http://localhost:8080/api/properties/<PROPERTY_ID>/request-scrape \
  -H "Content-Type: application/json"

# For an authenticated request (higher priority), pass a Clerk JWT:
# curl -X POST http://localhost:8080/api/properties/<PROPERTY_ID>/request-scrape \
#   -H "Authorization: Bearer <clerk_test_token>"

# Alternatively, trigger via the Admin Backend (bypasses auth, forces re-scrape):
curl -X POST http://localhost:8082/properties/<PROPERTY_ID>/force-scrape \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: dev-service-token-change-in-prod" \
  -H "X-Admin-User-Id: dev-admin" \
  -d '{"mode": "FORCE_ALL", "priority": "HIGH"}'

# 4. Watch progress in Flower
open http://localhost:5555

# 5. Check result in DB
psql postgresql://parceliq:devpassword@localhost:5432/parceliq -c "
  SELECT status, overall_confidence, updated_at
  FROM property_reports ORDER BY updated_at DESC LIMIT 5;
"
```

---

## 10. Debugging

### Python Services (VS Code)

Add to `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Public API",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--reload", "--port", "8080"],
      "cwd": "${workspaceFolder}/services/public-api",
      "envFile": "${workspaceFolder}/services/public-api/.env"
    },
    {
      "name": "Admin Backend API",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--reload", "--port", "8082"],
      "cwd": "${workspaceFolder}/services/admin-backend",
      "envFile": "${workspaceFolder}/services/admin-backend/.env"
    },
    {
      "name": "Scraper Worker",
      "type": "debugpy",
      "request": "launch",
      "module": "celery",
      "args": ["-A", "app.celery_app", "worker",
               "--queues", "data_acquisition_queue",
               "--concurrency", "1", "--pool", "solo",
               "--loglevel", "debug"],
      "cwd": "${workspaceFolder}/services/scraper-worker",
      "envFile": "${workspaceFolder}/services/scraper-worker/.env"
    },
    {
      "name": "LLM Parser Worker",
      "type": "debugpy",
      "request": "launch",
      "module": "celery",
      "args": ["-A", "app.celery_app", "worker",
               "--queues", "llm_processing_queue",
               "--concurrency", "1", "--pool", "solo",
               "--loglevel", "debug"],
      "cwd": "${workspaceFolder}/services/llm-parser-worker",
      "envFile": "${workspaceFolder}/services/llm-parser-worker/.env"
    }
  ]
}
```

Set a breakpoint anywhere, hit F5 — full debugger with step-through, variable inspection, watch expressions. This uses `--pool solo`, which runs Celery tasks in the main thread instead of a subprocess.

### Next.js (VS Code)

```json
{
  "name": "Public App",
  "type": "node",
  "request": "launch",
  "program": "${workspaceFolder}/apps/public-web/node_modules/.bin/next",
  "args": ["dev", "--port", "3000"],
  "cwd": "${workspaceFolder}/apps/public-web",
  "envFile": "${workspaceFolder}/apps/public-web/.env.local",
  "sourceMaps": true,
  "skipFiles": ["<node_internals>/**"]
}
```

Server Actions run on the Node.js server, so breakpoints in Server Action files work in VS Code exactly like any other Node.js code.

---

## 11. Database Management

```bash
# Connect with psql
psql postgresql://parceliq:devpassword@localhost:5432/parceliq

# Or use a GUI (TablePlus, DBeaver, DataGrip)
# Host: localhost  Port: 5432  User: parceliq  Pass: devpassword  DB: parceliq

# Reset the database entirely (useful when testing migrations)
docker compose down -v          # destroys postgres_data volume
docker compose up -d postgres
pnpm db:migrate

# Create a new migration
cd shared/db-migrations
uv run alembic revision --autogenerate -m "add_column_foo_to_properties"
# Review the generated file in versions/ before committing

# Run only specific migrations
uv run alembic upgrade +1       # apply one migration
uv run alembic downgrade -1     # roll back one migration
```

---

## 12. Stopping Everything

```bash
# Stop all native processes: Ctrl+C in each terminal (or kill the Turbo process)

# Stop Docker infrastructure
docker compose down

# Stop Docker AND wipe all data volumes (full reset)
docker compose down -v
```

---

## 13. Common Issues

| Problem | Cause | Fix |
|---|---|---|
| `connection refused` on port 5432 | Postgres not ready yet | `docker compose ps` — wait for healthy status |
| Celery tasks not being picked up | Wrong queue name | Check `--queues` flag matches task's `queue=` argument |
| `ADMIN_SERVICE_TOKEN mismatch` | `.env` values differ between admin-web and admin-backend | Ensure both files have identical `ADMIN_SERVICE_TOKEN` value |
| Clerk webhook not firing | ngrok not running | Start ngrok and update Clerk dashboard webhook URL |
| Playwright browser not found | Browsers not installed | `cd services/scraper-worker && uv run playwright install chromium` |
| `relation "properties" does not exist` | Migrations not run | `pnpm db:migrate` |
| MinIO buckets missing | Buckets not created | Run `bash infra/scripts/create_buckets.sh` to auto-create MinIO buckets (raw-scrape-cache, ozpr-db-backups), or open http://localhost:9001 and create manually |

---

## 14. MinIO Bucket Init Script

Create the required MinIO buckets after first `docker compose up`:

```bash
#!/usr/bin/env bash
# infra/scripts/create_buckets.sh
# Creates required MinIO buckets for local development.
# Requires: mc (MinIO Client) — install via `brew install minio/stable/mc`

set -euo pipefail

MINIO_ENDPOINT="http://localhost:${MINIO_PORT:-9000}"
MINIO_USER="${MINIO_ROOT_USER:-minioadmin}"
MINIO_PASS="${MINIO_ROOT_PASSWORD:-minioadmin}"

mc alias set parceliq "$MINIO_ENDPOINT" "$MINIO_USER" "$MINIO_PASS" --api S3v4

for BUCKET in raw-scrape-cache ozpr-db-backups; do
    if mc ls parceliq/"$BUCKET" &>/dev/null; then
        echo "Bucket '$BUCKET' already exists."
    else
        mc mb parceliq/"$BUCKET"
        echo "Created bucket '$BUCKET'."
    fi
done

echo "Done. MinIO buckets ready."
```

---

## 15. Deploying to Remote K3s

This section covers deploying all 6 application services to the 3-node K3s cluster using Docker images and Kubernetes manifests in `infra/k8s/`.

### Prerequisites

```bash
# 1. Docker logged in to your registry
docker login ghcr.io   # or your chosen registry

# 2. kubectl pointed at the remote K3s cluster
export KUBECONFIG=~/.kube/k3s-config   # or however you manage kubeconfig
kubectl get nodes   # should list k3s-master, k3s-node01, k3s-node02

# 3. envsubst available (usually pre-installed on Linux/macOS)
which envsubst

# 4. Root .env file populated with all secrets (see infra/k8s/secrets.example.yaml)
```

### First-Time Setup

```bash
# 1. Set your registry (override the default placeholder)
export REGISTRY=ghcr.io/your-org   # or your Docker Hub / ECR / etc.

# 2. Build all 6 images
make build-docker tag=v1.0.0

# 3. Push images and deploy everything to the cluster
make deploy tag=v1.0.0 REGISTRY=$REGISTRY

# 4. Confirm all pods are Running
make k8s-status

# 5. Add /etc/hosts entries (for local access before DNS is configured)
make k8s-hosts
```

### DNS Requirements

Let's Encrypt TLS requires **real public DNS** — `/etc/hosts` overrides alone won't work. Create A records:

| Domain | Target |
|---|---|
| `ozpropertyreport.com` | Any K3s node IP (e.g., `192.168.10.185`) |

cert-manager will automatically request and renew certificates via the ACME HTTP-01 challenge.

### Accessing Admin Surfaces (Port-Forward Only)

Admin-web, MinIO console, and Flower have **no internet ingress**. Use:

```bash
make k8s-admin
# Opens:
#   http://localhost:3001  ← admin-web
#   http://localhost:9001  ← MinIO console
#   http://localhost:5555  ← Flower
```

Press Ctrl+C to stop all port-forwards.

### Data Initialization (First Time)

After deploying, the database schema is ready but empty. Run the VIC bootstrap:

```bash
make k8s-init-data \
  lga_source=/path/to/LGA_2024_AUST_GDA2020.shp \
  suburb_source=/path/to/SAL_2021_AUST_GDA2020.shp \
  catchment_source=/path/to/school_catchments_vic.geojson \
  school_source=/path/to/vic_schools_2024.csv \
  gnaf_source=/path/to/gnaf_feb2026.zip
```

Download source files from:
- **G-NAF**: [data.gov.au](https://data.gov.au/dataset/geocoded-national-address-file-g-naf)
- **ABS ASGS (LGA, Suburb)**: [abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/digital-boundary-files)
- **School catchments**: Victorian Department of Education
- **School locations**: ACARA [My School](https://www.myschool.edu.au/media-centre/data-assets)

### Re-deploying After Code Changes

```bash
# Build and push updated images, then rolling-update all deployments
make build-docker tag=v1.0.1
make deploy tag=v1.0.1 REGISTRY=$REGISTRY
```

### Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `ImagePullBackOff` | Registry credentials not set on cluster | `kubectl create secret docker-registry ...` and add `imagePullSecrets` |
| `CrashLoopBackOff` on app pods | Missing secrets or misconfigured env | `make k8s-logs svc=<service>` — check for env var errors |
| Migration Job times out | Postgres not ready | Check `kubectl rollout status statefulset/postgres`, ensure PVC bound |
| Cert not issued | DNS not propagated yet | Wait 5–10 min after creating A records; `kubectl describe cert public-web-tls -n ozpropertyreport` |
| `port-forward` exits immediately | Pod not running | `make k8s-status` — confirm target pod is Running |
| G-NAF import OOMKill | Local machine RAM | Run on a machine with ≥16 GiB RAM; import is memory-intensive |
