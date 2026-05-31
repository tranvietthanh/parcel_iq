# OZ Property Report – System Architecture Overview

## 1. Project Summary

OZ Property Report is a map-centric property intelligence platform for Australian real estate investors. It aggregates public data from government APIs, local council portals, and open spatial datasets, processes it through an LLM pipeline, and presents it in an open-source, self-hosted platform.

**Scope:** All of Australia. All 8 states/territories supported from day one.

**Tech stack:** Next.js 16 (Node.js 22 LTS), Python 3.12 / FastAPI, PostgreSQL 16 + PostGIS, Redis + Celery, Clerk (auth), K3s. Frontend monorepo managed with pnpm workspaces.

---

## 2. Application Separation Model

OZ Property Report is **two completely separate web applications** — a public investor app and an internal admin app — with no shared frontend code, separate deployments, and separate Clerk authentication instances.

| | Public App | Admin App |
|---|---|---|
| URL | `ozpropertyreport.com` | `kubectl port-forward` only |
| Repository | `apps/public-web` | `apps/admin-web` |
| Auth | Clerk Public Instance (Email + Google OAuth) | Clerk Admin Instance (invite-only org) |
| Internet exposed | Yes | **No** — accessed only via `kubectl port-forward` |
| Backend communication | Client → public-web `/api/*` rewrites → Public API (internal) | Server Actions → Admin Backend API (internal) |
| Backend exposed | Public API: **internal only** (ClusterIP) | Admin Backend API: **internal only** (ClusterIP) |

---

## 3. Security Model: Why Server Actions for Admin

The Admin App uses **Next.js Server Actions** as its BFF layer rather than making API calls from the browser. This is a stronger security model for three reasons:

**1. The browser never holds a credential that can reach the backend.**
The Clerk admin JWT is verified inside the Server Action (which runs on the Next.js server pod). The Admin Backend API is never reachable from the internet — it has no Traefik ingress. Even if a Clerk JWT were somehow stolen, it cannot be used to call the Admin Backend API because that service is ClusterIP-only inside K3s.

**2. The Admin Backend API trusts only one caller.**
The Admin Backend API authenticates callers using a shared internal service secret (`ADMIN_SERVICE_TOKEN`) set as a K8s Secret. Only the Admin App pod has this secret. The Admin Backend API rejects any request without the correct token.

**3. All admin logic runs server-side.**
No sensitive data, no task IDs, no raw DB rows are ever sent to the browser as part of an API response that could be intercepted. The Server Action fetches what it needs, shapes it, and returns only the UI-relevant portion.

```
Browser
  │
  │  (HTTPS — only Next.js page/action responses travel here)
  ▼
Admin App (Next.js — internal admin access, typically via kubectl port-forward)
  │  Clerk JWT verified inside Server Action
  │  ADMIN_SERVICE_TOKEN attached to outgoing call
  │
  │  (HTTP — K3s internal network only, never leaves the cluster)
  ▼
Admin Backend API (FastAPI — ClusterIP:8082, no ingress)
  │  Verifies ADMIN_SERVICE_TOKEN header
  │
  ├──▶ PostgreSQL (ClusterIP)
  ├──▶ Redis / Celery (ClusterIP)
  └──▶ Flower (ClusterIP)
```

---

## 4. High-Level Architecture Diagram

```
INTERNET
  │
  ├────────────────────────────────────────────────────┐
  │                                                    │
  ▼                                                    ▼
┌─────────────────────────────────────┐   ┌───────────────────────────────────────┐
│  PUBLIC APP                         │   │  ADMIN APP                            │
│  ozpropertyreport.com               │   │  Admin Console (port-forward only)    │
│  Next.js 16, Clerk Public Instance  │   │  Next.js 16, Clerk Admin Instance     │
│  Client components call             │   │  Server Actions                       │
│    public-web /api rewrites         │   │    verify Clerk admin JWT             │
└───────────────┬─────────────────────┘   └─────────────────┬─────────────────────┘
                │                                           │
                │ HTTPS (internet)                          │ HTTP (K3s internal only)
                │                                           │
                ▼                                           ▼
┌───────────────────────────────────┐   ┌──────────────────────────────────────────┐
│  PUBLIC API (FastAPI)             │   │  ADMIN BACKEND API (FastAPI)             │
│  ClusterIP only — no ingress      │   │  ClusterIP:8082 — NO internet ingress    │
│  - Clerk JWT verify               │   │  - ADMIN_SERVICE_TOKEN auth               │
│  - Turnstile bot protection       │   │  - Admin DB reads + writes               │
│  - IP rate limiting               │   │  - Celery task dispatch                  │
│  - Public data reads              │   └─────────────────┬────────────────────────┘
│  - Celery on-demand jobs          │                     │
└───────────────┬───────────────────┘                     │
                │                                         │
                └──────────────────┬──────────────────────┘
                                   │
                  K3s Internal Network (ClusterIP services only)
          ┌────────────────────────┼────────────────────────────────┐
          │                        │                                │
          ▼                        ▼                                ▼
┌──────────────────┐   ┌────────────────────────┐    ┌─────────────────────────┐
│  PostgreSQL 16   │   │  REDIS 7               │    │  MinIO                  │
│  + PostGIS 3.4   │   │  (Celery broker)       │    │  (Object storage)       │
│  ClusterIP only  │   │  ClusterIP only        │    │  ClusterIP only         │
└──────────────────┘   └────────────┬───────────┘    └─────────────────────────┘
                                    │
                     ┌──────────────┴──────────────────┐
                     │                                 │
                     ▼                                 ▼
        ┌────────────────────────┐     ┌──────────────────────────────┐
        │  SCRAPER WORKERS       │     │  LLM PARSER WORKERS          │
        │  Celery + Playwright   │     │  Celery + Gemini API         │
        │  ClusterIP only        │     │  ClusterIP only              │
        └────────────────────────┘     └──────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────┐
        │  FLOWER                │
        │  Celery monitoring UI  │
        │  ClusterIP only        │
        │  (proxied by Admin     │
        │   Backend API)         │
        └────────────────────────┘
```

---

## 5. Services Inventory

| Service | Path | Technology | Network Exposure | Role |
|---|---|---|---|---|
| Public App | `apps/public-web` | Next.js 15, pnpm, Clerk Public | Internet | Map UI, investor auth, user operations |
| Admin App | `apps/admin-web` | Next.js 15, pnpm, Clerk Admin, Server Actions | Internet (Clerk-gated) | Admin UI — all backend calls via Server Actions |
| Public API | `services/public-api` | Python 3.12, FastAPI | Internal only (ClusterIP) | REST API for public app |
| Admin Backend API | `services/admin-backend` | Python 3.12, FastAPI | **Internal only (ClusterIP)** | All admin operations — never internet-facing |
| Database | `infra/postgres` | PostgreSQL 16 + PostGIS 3.4 | Internal only | All persistent data |
| Task Broker | `infra/redis` | Redis 7 | Internal only | Celery broker + result backend |
| Scraper Workers | `services/scraper-worker` | Python 3.12, Celery, Playwright | Internal only | National data acquisition |
| LLM Workers | `services/llm-parser-worker` | Python 3.12, Celery, OpenAI Chat Completions | Internal only | AI extraction, confidence scoring, email notification, Celery Beat schedule |
| Object Storage | `infra/minio` | MinIO | Internal only | PDFs, raw scrape cache |
| Job Monitor | `infra/flower` | Flower 2.x | **Internal only (ClusterIP)** | Celery UI, proxied by Admin Backend API |

---

## 6. Authentication Architecture

### Two Clerk Instances

| | Public Instance | Admin Instance |
|---|---|---|
| Keys | `CLERK_PUBLIC_*` | `CLERK_ADMIN_*` |
| Sign-in on | `ozpropertyreport.com` | Admin Console (port-forward access) |
| Providers | Email/password + Google OAuth | Email/password only |
| Access control | Open sign-up | Invite-only, org membership required |
| JWT verified by | Public API (on each request) | Admin App Server Action (before internal call) |
| Users stored in DB | Yes — `users` table, keyed by `clerk_user_id` | No — Clerk Dashboard is source of truth |

### Admin Auth Flow (the critical path)

```
1. Admin opens the Admin Console (typically via `kubectl port-forward`, e.g. `http://localhost:3001`)
2. Clerk middleware on Next.js server checks session
   → No session: redirect to Clerk-hosted sign-in page
   → Session exists but wrong org: return 403 before rendering
3. Admin fills in a form / clicks an action in the browser
4. Browser POSTs to the Next.js Server Action endpoint (same origin)
5. Server Action runs on the Next.js server (not the browser):
   a. Calls auth() from Clerk — verifies session + org membership
   b. If invalid: throws error, returns nothing to browser
   c. If valid: attaches ADMIN_SERVICE_TOKEN header
   d. Makes HTTP request to Admin Backend API ClusterIP:8082
6. Admin Backend API receives request:
   a. Checks X-Service-Token header == ADMIN_SERVICE_TOKEN
   b. If invalid: 401, logged, done
   c. If valid: executes the admin operation (DB write, Celery task, etc.)
7. Result returned: Admin Backend API → Server Action → browser
   (browser only ever sees the shaped UI response — never raw DB data or tokens)
```

---

## 7. Internal Service Authentication

The Admin Backend API uses a **static shared secret** for service-to-service auth:

```
ADMIN_SERVICE_TOKEN=<random 64-byte hex string, stored as K8s Secret>
```

This secret is mounted only into two pods:
- `admin-web` (Admin App) — attaches it as `X-Service-Token` header in Server Actions
- `admin-backend` (Admin Backend API) — verifies it on every request

No other pod has this secret. The Admin Backend API rejects all requests without it regardless of source IP, so even if another internal pod were compromised, it cannot call admin endpoints.

---

## 8. Deployment: K3s (Single Node MVP)

```
k3s-node/
└── namespace: parceliq
    │
    │  ── INTERNET-FACING (Traefik ingress) ─────────────────────────
    ├── Deployment: public-web        (2 replicas, ozpropertyreport.com)
    │
    │  ── INTERNAL ONLY (ClusterIP, no Traefik ingress) ─────────────
    ├── Deployment: admin-web         (1 replica, accessed via port-forward)
    ├── Deployment: public-api        (2 replicas, ClusterIP)
    ├── Deployment: admin-backend     (1 replica,  ClusterIP:8082)
    ├── Deployment: scraper-worker    (1 → scale to 5)
    ├── Deployment: llm-parser-worker (1 → scale to 3, includes Celery Beat)
    ├── Deployment: flower            (1, ClusterIP:5555)
    ├── StatefulSet: postgres         (1 pod, PVC: 50Gi)
    ├── StatefulSet: redis            (1 pod, PVC: 2Gi)
    └── StatefulSet: minio            (1 pod, PVC: 100Gi)
```

Note: `admin-web` and `admin-backend` have no public ingress in the current deployment. Admin access is via port-forward to `admin-web`, which then calls `admin-backend` over the cluster internal network.

### Resource Limits (MVP)

| Pod | CPU Request | CPU Limit | Memory Request | Memory Limit |
|---|---|---|---|---|
| public-web | 100m | 500m | 128Mi | 512Mi |
| admin-web | 100m | 500m | 128Mi | 512Mi |
| public-api | 200m | 1000m | 256Mi | 1Gi |
| admin-backend | 100m | 500m | 128Mi | 512Mi |
| scraper-worker | 500m | 2000m | 1Gi | 3Gi |
| llm-parser-worker | 100m | 500m | 256Mi | 1Gi |
| flower | 50m | 200m | 64Mi | 256Mi |
| postgres | 1000m | 4000m | 2Gi | 8Gi |
| redis | 100m | 500m | 256Mi | 1Gi |
| minio | 100m | 500m | 256Mi | 1Gi |

---

## 9. Network Policies

```yaml
# Only Public API and Admin Backend can reach Postgres
# postgres-network-policy.yaml
spec:
  podSelector: { matchLabels: { app: postgres } }
  ingress:
    - from:
        - podSelector: { matchLabels: { app: public-api } }
        - podSelector: { matchLabels: { app: admin-backend } }
      ports: [{ port: 5432 }]
---
# Only Admin Backend can reach Flower — not the browser, not the Admin App frontend
# flower-network-policy.yaml
spec:
  podSelector: { matchLabels: { app: flower } }
  ingress:
    - from:
        - podSelector: { matchLabels: { app: admin-backend } }
      ports: [{ port: 5555 }]
---
# Only Admin App (Next.js server) can reach Admin Backend
# admin-backend-network-policy.yaml
spec:
  podSelector: { matchLabels: { app: admin-backend } }
  ingress:
    - from:
        - podSelector: { matchLabels: { app: admin-web } }
      ports: [{ port: 8082 }]
```

---

## 10. Data Flows

### Flow A — User Views a Property (Anonymous)

```
Browser → GET ozpropertyreport.com/
  → Next.js serves map shell
  → Client JS: GET ozpropertyreport.com/api/search?bbox=...  (Turnstile token)
  → Public API → PostGIS bbox query → GeoJSON → Map renders pins
  → User clicks pin → GET ozpropertyreport.com/api/properties/{id}/detail
  → Property detail panel renders curated sections
```

### Flow B — Admin Triggers a Batch Scrape

```
Browser → clicks "Queue Scrape" in Admin App form
  → POST /actions/scrape  (Server Action, same origin to admin app)
  → Next.js server:
      auth().protect()  ← Clerk session + org check
      fetch("http://admin-backend:8082/scrape/trigger", {
        headers: { "X-Service-Token": ADMIN_SERVICE_TOKEN }
      })
  → Admin Backend API:
      validates X-Service-Token
      queries gnaf_addresses
      publishes Celery tasks to Redis
  → Server Action returns { jobsQueued: 1247 } to browser
```

### Flow C — Admin Views Flower

```
Browser → navigates to /jobs in Admin App
  → Server Action fetches http://admin-backend:8082/flower/proxy/
  → Admin Backend API reverse-proxies to http://flower:5555
  → Flower HTML returned through Server Action → browser renders iframe
  → All subsequent Flower iframe requests also go through the same proxy chain
```

### Flow D — User Generates Full Report

```
Browser → POST ozpropertyreport.com/api/reports/generate
  → Public API handles generation and verification
  → User redirected back → Full report accessible
```

---

## 11. Monorepo Structure

```
/parceliq/
├── apps/
│   ├── public-web/          # Next.js public investor app
│   └── admin-web/           # Next.js admin app (Server Actions → admin-backend)
├── services/
│   ├── public-api/          # FastAPI — internal-only public API
│   ├── admin-backend/       # FastAPI — internal-only admin API
│   ├── scraper-worker/      # Celery scraper workers
│   └── llm-parser-worker/   # Celery LLM parser workers + Celery Beat schedule
├── shared/
│   ├── db-migrations/       # Alembic migrations (single source of truth)
│   ├── py-types/            # Shared Pydantic models
│   └── pdf-renderer/        # Shared PDF rendering service
├── infra/
│   ├── k8s/                 # K8s manifests (namespace, configmap, PVCs, deployments, ingress)
│   │   ├── apps/            # Application service Deployments (envsubst templated)
│   │   ├── infrastructure/  # Postgres, Redis, MinIO, Flower
│   │   ├── ingress/         # Traefik Ingress (public-web only)
│   │   ├── jobs/            # DB migration Job
│   │   ├── network-policies/# admin-backend isolation NetworkPolicy
│   │   └── pvc/             # Longhorn PersistentVolumeClaims
│   └── scripts/             # Data population scripts (import_gnaf.py, etc.)
└── docker-compose.yml       # Local dev (all services)
```

> **Note:** K8s manifests are committed to `infra/k8s/`. Deploy with `make deploy tag=<tag> REGISTRY=<registry>`.
> See `docs/09-local-dev.md` §15 for the full deployment workflow.

---

## 12. Environment Variables (Master Reference)

```env
# ── Public App ─────────────────────────────────────────────────────
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_public_...
CLERK_SECRET_KEY=sk_live_public_...
NEXT_PUBLIC_MAPBOX_TOKEN=<Mapbox>
NEXT_PUBLIC_TURNSTILE_SITE_KEY=<Cloudflare>
CLERK_WEBHOOK_SECRET=<Svix webhook secret from Clerk dashboard>
INTERNAL_WEBHOOK_SECRET=<random hex — for user sync call to Public API>

# ── Admin App ───────────────────────────────────────────────────────
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_admin_...    # Admin Clerk instance
CLERK_SECRET_KEY=sk_live_admin_...
CLERK_ADMIN_ORG_ID=org_...
ADMIN_BACKEND_URL=http://admin-backend:8082             # K3s ClusterIP — internal only
ADMIN_SERVICE_TOKEN=<random 64-byte hex>               # Shared secret for service auth

# ── Public API ──────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://parceliq:pass@postgres:5432/parceliq
REDIS_URL=redis://redis:6379/0
CLERK_PUBLIC_JWKS_URL=https://clerk.ozpropertyreport.com/.well-known/jwks.json
TURNSTILE_SECRET_KEY=<Cloudflare>
RESEND_API_KEY=<Resend>
INTERNAL_WEBHOOK_SECRET=<same value as Admin App>

# ── Admin Backend API ───────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://parceliq:pass@postgres:5432/parceliq
REDIS_URL=redis://redis:6379/0
ADMIN_SERVICE_TOKEN=<same value as Admin App>           # Must match
FLOWER_INTERNAL_URL=http://flower:5555

# ── Scraper Workers ─────────────────────────────────────────────────
DATABASE_URL=postgresql+psycopg2://parceliq:pass@postgres:5432/parceliq
REDIS_URL=redis://redis:6379/0
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=<minio admin>
MINIO_SECRET_KEY=<minio password>
PROXY_URL=<residential proxy>
PROXY_USERNAME=<proxy user>
PROXY_PASSWORD=<proxy pass>
WORKER_CONCURRENCY=3

# ── LLM Parser Worker ───────────────────────────────────────────────
DATABASE_URL=postgresql+psycopg2://parceliq:pass@postgres:5432/parceliq
REDIS_URL=redis://redis:6379/0
OPENAI_API_KEY=<OpenAI API key>   # sk_...
OPENAI_MODEL=gpt-3.5-turbo        # or gpt-4o-mini, gpt-4o
OPENAI_DAILY_QUOTA=100000
OPENAI_MAX_RPM=60
RESEND_API_KEY=<Resend API key>
PUBLIC_WEB_URL=https://ozpropertyreport.com

# ── Public API (additional Stripe settings) ──────────────────────────
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_UNIT_PRICE_AUD_CENTS=100
STRIPE_MIN_CREDITS=5
FRONTEND_URL=https://ozpropertyreport.com
```

---

## 13. Observability

| Concern | Tool |
|---|---|
| Structured logging | `structlog` (JSON) in all Python services; Pino in Next.js |
| Log aggregation | Grafana Loki + Grafana (K3s internal pod) |
| Celery job monitoring | Flower (proxied via Admin Backend API → Admin App Server Action) |
| DB performance | `pg_stat_statements` + `auto_explain` (logs queries > 100ms) |
| Uptime | Traefik health checks + email alert on pod restart loops |
| DLQ alerting | Celery Beat task every 15 min — email if failed task count > 50 |

---

## 14. Celery Beat Schedule

Celery Beat is **not a separate service** — the beat schedule is embedded in the `llm-parser-worker`'s `celery_app.py`. One of the LLM parser worker pods is started with `--beat` to act as the Beat singleton.

Scrapes for individual properties are triggered on-demand (by users or admins via the priority queue), not by a cron. The Beat schedule handles recurring maintenance tasks and bulk state refreshes.

| Schedule Name | Task | Cron | Description |
|---|---|---|---|
| `refresh-vic-monthly` | `app.tasks.trigger_state_refresh` | 1st of month, 02:00 AEST | Re-scrape all VIC properties |
| `refresh-nsw-monthly` | `app.tasks.trigger_state_refresh` | 8th of month, 02:00 AEST | Re-scrape all NSW properties |
| `check-dlq-every-15m` | `app.tasks.check_dlq` | Every 15 minutes | DLQ alert if failed count > 50 |

```python
# services/llm-parser-worker/app/celery_app.py (excerpt)
celery_app.conf.beat_schedule = {
    "refresh-vic-monthly": {
        "task": "app.tasks.trigger_state_refresh",
        "schedule": crontab(minute=0, hour=2, day_of_month="1"),
        "kwargs": {"state": "VIC"},
    },
    "refresh-nsw-monthly": {
        "task": "app.tasks.trigger_state_refresh",
        "schedule": crontab(minute=0, hour=2, day_of_month="8"),
        "kwargs": {"state": "NSW"},
    },
    "check-dlq-every-15m": {
        "task": "app.tasks.check_dlq",
        "schedule": crontab(minute="*/15"),
    },
}
```

---

## 15. Shared Python Types (`shared/py-types/`)

Pydantic models shared across multiple Python services to avoid duplication and ensure schema consistency.

| Module | Models | Used By |
|---|---|---|
| `parceliq_types.llm_output` | `LlmOutput`, `ZoningAndPlanning`, `RiskFactors`, `RoiScenarios`, `DemographicSnapshot`, etc. | LLM Parser Worker (writes), Public API (reads + serves), Admin Backend (reads + patches) |
| `parceliq_types.scraped_data` | `ScrapedPropertyData` | Scraper Worker (writes), LLM Parser Worker (reads) |
| `parceliq_types.confidence` | `ConfidenceResult`, `compute_confidence()` | LLM Parser Worker (computes) |

**Package structure:**
```
shared/py-types/
├── pyproject.toml            # [project] name = "ozpr-types"
├── parceliq_types/
│   ├── __init__.py
│   ├── llm_output.py         # Full Pydantic v2 model (from doc 06)
│   ├── scraped_data.py       # ScrapedPropertyData dataclass (from doc 05)
│   └── confidence.py         # ConfidenceResult + compute_confidence()
```

Installed as a local path dependency in each service's `pyproject.toml`:
```toml
[tool.uv.sources]
ozpr-types = { path = "../../shared/py-types", editable = true }
```

---

## 16. Credit-Based Entitlement Model

OZ Property Report implements a credit-based consumption model for property report generation and downloads, replacing the legacy subscription tier model.

### 16.1 Database Tables

| Table | Purpose |
|---|---|
| `user_credit_wallet` | Per-user balance ledger (daily + purchased pools) |
| `credit_ledger` | Immutable audit trail of all credit movements (`DAILY_GRANT`, `DOWNLOAD_DEBIT`, `ADMIN_TOPUP`, `PURCHASE_CREDIT`) |
| `credit_purchase_orders` | One row per Stripe checkout session (PENDING → PAID / FAILED) |
| `payment_event_receipts` | Idempotency guard for Stripe webhook replay |

### 16.2 Wallet and Ledger Architecture
- **Wallet (`user_credit_wallet`)**: Tracks each user's credit balances across two pools: `daily_grant_credits` / `daily_used_credits` (free daily allocation) and `purchased_credits_balance` (paid credits).
- **Ledger (`credit_ledger`)**: Provides a complete audit trail of all credit movements. Every write contains a `balance_after` column to guarantee ledger consistency and simplify point-in-time reconciliation.
- **Advisory Lock**: Wallet mutations acquire `pg_advisory_xact_lock(hashtext('credit:' || user_id::text))` to prevent concurrent debit/credit race conditions (TOCTOU). The Stripe webhook handler uses the same lock.

### 16.3 Daily Reset and Spending Order
- **Daily Reset**: Free daily credits (`daily_grant_credits`) reset at midnight Australia/Sydney time via wallet reconciliation on access. Remaining daily credits do not roll over.
- **Spending Priority**: When a user unlocks a property report, the system debits daily free credits first, then purchased credits.

### 16.4 Payment Flow (Stripe)
1. User calls `POST /api/credits/checkout` → Stripe Checkout Session created → order row inserted as `PENDING`.
2. User completes payment on Stripe-hosted page.
3. Stripe calls `POST /api/credits/webhook/stripe` (signature verified) → credits granted, order marked `PAID`, ledger entry written.
4. Disputes: order marked `FAILED`, no credit clawback (credits are consumables).

### 16.5 Anonymous Claims (Cookie-Based)
- **Anonymous Session**: Guest users can trigger report generations. These requests are associated with a generated `anon_requester_id` stored in a secure, HTTP-only cookie.
- **Claim Window**: When the guest signs in or signs up, any anonymous requests generated within a 7-day window are linked/claimed to their authenticated account.
- **Cross-Device Claims (Non-Goal)**: Tracking of guest actions relies entirely on the browser-bound cookie. Associating or claiming anonymous requests across different devices/browsers is explicitly a **non-goal** for this system.

