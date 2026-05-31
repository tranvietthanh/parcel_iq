# OZ Property Report – Admin Console Specification

## 1. Overview

The Admin Console is a **completely separate Next.js application** (`apps/admin-web`) from the public app. All communication with backend services happens through **Next.js Server Actions** — the browser never directly calls any API. Server Actions verify the Clerk admin session and then make server-to-server HTTP calls to the Admin Backend API (`services/admin-backend`), which is a ClusterIP-only FastAPI service with no internet ingress.

/**
Browser (Admin Console via port-forward, e.g. localhost:3001)
  │  only receives shaped UI data — never raw DB rows, tokens, or task IDs
  │
  ▼  (same-origin HTTPS POST to /actions/*)
Next.js Server Actions  ← runs on the admin-web pod, NOT in the browser
  │  1. Verify Clerk admin JWT + org membership
  │  2. Attach ADMIN_SERVICE_TOKEN
  │
  ▼  (HTTP — K3s internal network only)
Admin Backend API (FastAPI, ClusterIP:8082, no internet ingress)
  │  Verifies ADMIN_SERVICE_TOKEN on every request
  │
  ├──▶ PostgreSQL
  ├──▶ Redis / Celery
  └──▶ Flower (ClusterIP:5555)
```

**The Admin Backend API has no Traefik ingress. It is physically unreachable from the internet regardless of auth.**

## 2. Admin App (`apps/admin-web`)

### 2.1 Technology

Next.js 16 (App Router), TypeScript, Tailwind CSS, Clerk Admin Instance, Server Actions

### 2.2 Authentication

Uses a **separate Clerk application** from the public app (`CLERK_ADMIN_*` keys). Requirements:
- Users must be a member of the `ozpr-admins` Clerk Organisation
- Sign-in is **email/password only** (no Google OAuth — intentional for admin accounts)

### 2.3 Clerk Middleware (`apps/admin-web/middleware.ts`)

```typescript
import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server';
import { NextResponse } from 'next/server';

const isPublicRoute = createRouteMatcher(['/sign-in(.*)']);

export default clerkMiddleware(async (auth, req) => {
  if (isPublicRoute(req)) return;

  const { userId, orgId } = await auth();

  // Not signed in → redirect to Clerk sign-in
  if (!userId) {
    return auth().redirectToSignIn({ returnBackUrl: req.url });
  }

  // Signed in but wrong org → hard reject (do not redirect to public app)
  if (orgId !== process.env.CLERK_ADMIN_ORG_ID) {
    return new NextResponse('Access denied. Admin organisation membership required.', {
      status: 403,
    });
  }
});

export const config = { matcher: ['/((?!_next|.*\\..*).*)'] };
```

### 2.4 Server Action Pattern

Every admin operation follows this pattern. The Clerk check and the internal API call both happen on the server — nothing sensitive reaches the browser.

```typescript
// apps/admin-web/lib/admin-action.ts
'use server';

import { auth } from '@clerk/nextjs/server';

const ADMIN_BACKEND_URL = process.env.ADMIN_BACKEND_URL!;        // http://admin-backend:8082
const ADMIN_SERVICE_TOKEN = process.env.ADMIN_SERVICE_TOKEN!;    // K8s Secret

/**
 * Base wrapper for all Server Actions.
 * Verifies Clerk session + org, then calls the Admin Backend API.
 */
export async function adminAction<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<T> {
  // Step 1: Verify Clerk session and org membership
  const { userId, orgId } = await auth();
  if (!userId || orgId !== process.env.CLERK_ADMIN_ORG_ID) {
    throw new Error('Unauthorised');
  }

  // Step 2: Call Admin Backend API with service token
  // This call happens server-side — the token never leaves the pod
  const res = await fetch(`${ADMIN_BACKEND_URL}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Service-Token': ADMIN_SERVICE_TOKEN,
      'X-Admin-User-Id': userId,   // forwarded for audit logging
    },
    body: body ? JSON.stringify(body) : undefined,
    // No caching — admin data must always be fresh
    cache: 'no-store',
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `Admin backend error: ${res.status}`);
  }

  return res.json();
}
```

### 2.5 Example Server Actions

```typescript
// apps/admin-web/actions/scrape.ts
'use server';
import { adminAction } from '@/lib/admin-action';

export async function triggerScrape(formData: FormData) {
  const scope = formData.get('scope') as string;
  const state = formData.get('state') as string;
  const lga = formData.get('lga') as string;
      #### `GET /tasks`
  return adminAction('POST', '/properties/trigger-scrape', {
    scope, state, lga, priority, dry_run: dryRun,
  });
}

// apps/admin-web/actions/reports.ts
'use server';
import { adminAction } from '@/lib/admin-action';

export async function approveReport(reportId: string) {
  return adminAction('POST', `/reports/${reportId}/approve`);
}
  ### 2.6 Tasks Monitoring via Direct Backend API
export async function rejectReport(reportId: string) {
  return adminAction('POST', `/reports/${reportId}/reject`);
}

export async function patchReportInsight(
  reportId: string,
  fieldPath: string,
  newValue: unknown,
) {
  return adminAction('PATCH', `/reports/${reportId}/insights`, {
    field_path: fieldPath,
    new_value: newValue,
  });
}

// apps/admin-web/actions/data-sources.ts
'use server';
import { adminAction } from '@/lib/admin-action';

export async function createDataSource(data: DataSourceFormValues) {
  return adminAction('POST', '/data-sources', data);
}

export async function testDataSource(configId: string) {
  return adminAction('POST', `/data-sources/${configId}/test`);
}

// apps/admin-web/actions/refresh_census.ts
'use server';
import { adminAction } from '@/lib/admin-action';
import { z } from 'zod';

const RefreshCensusSchema = z.object({
  delete_existing: z.boolean().default(true),
  force: z.boolean().default(false),
});

type RefreshCensusRequest = z.infer<typeof RefreshCensusSchema>;

export interface RefreshAbsCensusResponse {
  task_id: string;
  cache_count_before: number;
  status: string;
}

/**
 * Trigger bulk download and cache of ABS Census data for all ~2,200 SA2s.
 * 
 * This runs as a background Celery task (5-10 minutes). Returns the task ID
 * so admins can monitor progress in Flower.
 * 
 * Options:
 * - delete_existing: If true, clear the cache before syncing (full refresh)
 * - force: If true, re-download even if SA2 already cached
 */
export async function refreshAbsCensusData(
  request: RefreshCensusRequest
): Promise<RefreshAbsCensusResponse> {
  const validated = RefreshCensusSchema.parse(request);
  return adminAction<RefreshAbsCensusResponse>(
    'POST',
    '/data/refresh-census',
    validated
  );
}

### 2.6 Flower Proxy via Server Action

Flower is not embedded as an iframe pointing at the Admin Backend API directly. Instead, every Flower request is proxied server-side through a Next.js Route Handler (which applies the same Clerk check):
import { NextRequest, NextResponse } from 'next/server';

const ADMIN_BACKEND_URL = process.env.ADMIN_BACKEND_URL!;
const ADMIN_SERVICE_TOKEN = process.env.ADMIN_SERVICE_TOKEN!;

export async function GET(
  req: NextRequest,
  { params }: { params: { path: string[] } }
) {
  // Verify Clerk session
  const { userId, orgId } = await auth();
  if (!userId || orgId !== process.env.CLERK_ADMIN_ORG_ID) {
    return new NextResponse('Unauthorised', { status: 403 });
  }

  const flowerPath = params.path.join('/');
  const query = req.nextUrl.search;
  const target = `${ADMIN_BACKEND_URL}/flower/proxy/${flowerPath}${query}`;

  const upstream = await fetch(target, {
    headers: {
      'X-Service-Token': ADMIN_SERVICE_TOKEN,
      'Accept': req.headers.get('Accept') ?? '*/*',
    },
    cache: 'no-store',
  });

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: upstream.headers,
  });
}
```

The iframe `src` in the admin UI points to `/api/flower/` (same-origin Next.js route), not to the Admin Backend API:

```typescript
// apps/admin-web/components/admin/FlowerEmbed.tsx
export default function FlowerEmbed() {
  return (
    <iframe
      src="/api/flower/"          // same-origin — Clerk session cookie is sent automatically
      className="w-full h-screen border-0"
      title="Celery Job Monitor"
    />
  );
}
```

### 2.7 Project Structure

```
/apps/admin-web
├── app/
│   ├── layout.tsx                       # ClerkProvider (admin instance)
│   ├── middleware.ts                    # Clerk org gate
│   ├── sign-in/[[...sign-in]]/page.tsx
│   ├── dashboard/page.tsx               # Stats + queue health + activity feed
│   ├── scrape/
│   │   ├── page.tsx                     # Trigger form (uses triggerScrape action)
│   │   └── history/page.tsx
│   ├── data-sources/
│   │   ├── page.tsx
│   │   ├── new/page.tsx
│   │   └── [id]/page.tsx
│   ├── reports/
│   │   ├── page.tsx
│   │   ├── review/page.tsx              # Uses approveReport / rejectReport actions
│   │   └── [id]/page.tsx               # Uses patchReportInsight action
│   ├── properties/
│   │   ├── page.tsx
│   │   └── [id]/page.tsx
│   ├── tasks/page.tsx                   # Celery task monitoring with auto-refresh
│   ├── analytics/page.tsx
│   └── api/                              # Removed Flower API route
│       └── tasks/
│           └── [...path]/route.ts       # New tasks API route
├── actions/
│   ├── reports.ts                       # Server Actions for report review/patch
│   ├── tasks.ts                         # Server Actions for task monitoring
│   ├── stats.ts                         # Server Actions for dashboard stats
│   ├── sources.ts                       # Server Actions for LGA data source configs
│   ├── properties.ts                    # Server Actions for property management
│   └── users.ts                         # Server Actions for user management
├── lib/
│   └── admin-action.ts                  # Base Server Action wrapper
├── components/admin/
│   ├── AdminSidebar.tsx
│   ├── StatCard.tsx
│   ├── QueueHealthPanel.tsx
│   ├── ScrapeForm.tsx
│   ├── ReportReviewCard.tsx
│   ├── DataSourceForm.tsx
│   ├── PropertyTable.tsx
│   ├── CoverageMap.tsx
│   └── TaskMonitor.tsx                  # New component for task monitoring
└── middleware.ts
```

---

## 3. Admin Backend API (`services/admin-backend`)

### 3.1 Overview

**Technology:** Python 3.12, FastAPI, asyncpg, httpx  
**Network:** ClusterIP only — `admin-backend:8082`. **Zero internet exposure.**  
**Auth:** `X-Service-Token` header must match `ADMIN_SERVICE_TOKEN` env var. No Clerk verification here — Clerk is already verified by the Server Action before this service is called.

This is intentional. The Admin Backend API is a trusted internal service. It does not need to re-verify Clerk because it is physically unreachable from anywhere other than the `admin-web` pod (enforced by K8s NetworkPolicy).

### 3.2 Project Structure

```
/services/admin-backend
├── app/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py           # verify_service_token dependency
│   ├── routers/
│   │   ├── stats.py              # GET /stats
│   │   ├── reports.py            # GET/POST/PATCH /reports/*
│   │   ├── properties.py         # GET /properties/* + POST /properties/{id}/force-scrape
│   │   ├── data_sources.py       # CRUD /data-sources/*
│   │   ├── queue.py              # GET /queue/health, POST /queue/control
│   │   ├── lgas.py               # GET /lgas
│   │   ├── analytics.py          # GET /analytics
│   │   ├── tasks.py              # GET/POST /tasks/* (Celery inspector)
│   │   ├── users.py              # GET /users/*
│   │   └── reconciliation.py     # POST /reconcile (wallet/ledger reconciliation)
│   └── core/
│       ├── service_auth.py       # X-Service-Token verification
│       └── database.py
├── Dockerfile
└── pyproject.toml
```

### 3.3 Service Token Auth (`app/core/service_auth.py`)

```python
from fastapi import Header, HTTPException
from app.config import settings

async def verify_service_token(
    x_service_token: str = Header(alias="X-Service-Token"),
    x_admin_user_id: str = Header(alias="X-Admin-User-Id", default="unknown"),
) -> str:
    """
    Verifies the shared service token on every request.
    Returns the admin user ID (forwarded from Server Action for audit logging).
    
    This is the ONLY auth check on this service. Clerk is already verified
    upstream in the Next.js Server Action before this endpoint is reached.
    """
    if x_service_token != settings.ADMIN_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid service token.")
    return x_admin_user_id

# Applied to every route via router dependency:
# router = APIRouter(dependencies=[Depends(verify_service_token)])
```

### 3.4 Key Endpoints

#### `GET /stats`

```python
@router.get("/stats")
async def get_stats(db=Depends(get_db)):
    row = await db.fetchrow("""
        SELECT
            (SELECT COUNT(*) FROM properties)                                    AS total_properties,
            (SELECT COUNT(*) FROM property_reports WHERE status = 'READY')       AS reports_ready,
            0                                                                    AS awaiting_review,  -- review queue removed
            (SELECT COUNT(*) FROM property_reports
              WHERE status = 'FAILED'
                AND updated_at > NOW() - INTERVAL '7 days')                     AS failed_7d,
            (SELECT COUNT(DISTINCT lga_id) FROM properties p
              JOIN property_reports pr ON pr.property_id = p.id
              WHERE pr.status = 'READY')                                         AS lga_coverage,
            (SELECT COUNT(DISTINCT user_id) FROM credit_ledger
              WHERE entry_type = 'DOWNLOAD_DEBIT'
                AND created_at >= date_trunc('month', NOW()))                    AS sales_mtd,
            0.0                                                                   AS revenue_mtd  -- payment integration deferred
    """)
    return dict(row)
```

> **Note on `sales_mtd`:** This counts unique users who downloaded a report this month, using the `credit_ledger` table. The `revenue_mtd` field is hardcoded to 0 — dollar revenue tracking is deferred to a separate change once Stripe reconciliation is integrated into the dashboard.

#### `POST /scrape/trigger`

```python
class ScrapeRequest(BaseModel):
    scope: Literal["STATE", "LGA", "POSTCODE"]
    state: Literal["VIC","NSW","QLD","SA","WA","TAS","ACT","NT"] | None = None
    lga: str | None = None
    postcode: str | None = None
    priority: Literal["NORMAL", "HIGH"] = "NORMAL"
    mode: Literal["STALE_ONLY", "FORCE_ALL"] = "STALE_ONLY"
    dry_run: bool = False

@router.post("/scrape/trigger")
async def trigger_scrape(
    body: ScrapeRequest,
    admin_user_id: str = Depends(verify_service_token),
    db = Depends(get_db),
):
    properties = await resolve_target_properties(db, body)

    if body.dry_run:
        return {"dry_run": True, "estimated_jobs": len(properties)}

    for prop in properties:
        scrape_property.apply_async(
            kwargs={
                "property_id": str(prop["id"]),
                "gnaf_pid": prop["gnaf_pid"],
                "address_string": prop["address_string"],
                "latitude": float(prop["lat"]),
                "longitude": float(prop["lng"]),
                "lga_name": prop["lga_name"],
                "state": prop["state"],
            },
            queue="data_acquisition_queue",
            priority=9 if body.priority == "HIGH" else 5,
        )

    await log_admin_activity(
        db, admin_user_id, "SCRAPE_TRIGGERED",
        f"{body.scope} — {len(properties)} jobs queued"
    )
    return {
        "jobs_queued": len(properties),
        "estimated_completion_minutes": round(len(properties) / 3 * 2),
    }
```

#### `POST /properties/{property_id}/force-scrape`

Triggers a full re-scrape for a property regardless of `last_scraped_at`. Admin can choose `priority` and `mode` (defaults to `FORCE_ALL`). Dispatches to `data_acquisition_queue`.

#### `POST /properties/{property_id}/re-ai-validate`

Re-queues the LLM parsing step for the latest existing report. Useful when the LLM model or prompt changes. Dispatches to `llm_processing_queue`.

#### `PATCH /reports/{report_id}/insights`

```python
class InsightPatch(BaseModel):
    field_path: str    # e.g. "risk_factors.flood.risk"
    new_value: str | float | int | bool | None

@router.patch("/reports/{report_id}/insights")
async def patch_insights(
    report_id: UUID,
    body: InsightPatch,
    admin_user_id: str = Depends(verify_service_token),
    db = Depends(get_db),
):
    pg_path = "{" + body.field_path.replace(".", ",") + "}"
    await db.execute(
        """UPDATE property_reports
           SET llm_parsed_insights = jsonb_set(
               llm_parsed_insights, $2::text[], $3::jsonb, false
           ), updated_at = NOW()
           WHERE id = $1""",
        report_id, pg_path, json.dumps(body.new_value)
    )
    await log_admin_activity(
        db, admin_user_id, "INSIGHT_EDITED",
        f"{report_id}: {body.field_path} → {body.new_value}"
    )
    return {"patched": True}
```

#### `GET /flower/proxy/{path}`

```python
import httpx

@router.api_route("/flower/proxy/{path:path}", methods=["GET", "POST"])
async def proxy_flower(path: str, request: Request):
    """
    Reverse-proxies Flower requests. Service token already verified by
    the router-level dependency — this function just forwards the request.
    """
    target = f"{settings.FLOWER_INTERNAL_URL}/{path}"
    if request.url.query:
        target += f"?{request.url.query}"

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=target,
            # Strip auth headers — Flower has no auth of its own
            headers={k: v for k, v in request.headers.items()
                     if k.lower() not in ("host", "x-service-token", "x-admin-user-id")},
            content=await request.body(),
            timeout=30,
        )
    return Response(content=resp.content, status_code=resp.status_code,
                    headers=dict(resp.headers))
```

#### `POST /data/refresh-census`

```python
from app.celery_app import celery_app
from app.tasks import refresh_abs_census_complete

class RefreshCensusRequest(BaseModel):
    delete_existing: bool = True
    force: bool = False

class RefreshCensusResponse(BaseModel):
    task_id: str
    cache_count_before: int
    status: str

@router.post("/data/refresh-census")
async def refresh_census(
    body: RefreshCensusRequest,
    admin_user_id: str = Depends(verify_service_token),
    db = Depends(get_db),
):
    """
    Trigger bulk download and cache of ABS Census data for all ~2,200 SA2s.
    
    This is a background task (5-10 minutes). The response includes the task ID
    which can be monitored via Flower at /flower/proxy/tasks/{task_id}.
    
    Args:
        delete_existing: If true, clear abs_census_data table before syncing (full refresh)
        force: If true, re-download even if SA2 already in cache
    
    Returns:
        {
            "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            "cache_count_before": 1200,
            "status": "QUEUED"
        }
    """
    from app.services.abs_census_db import count_cached_census_data
    
    # Get current cache size before refresh
    cache_count_before = count_cached_census_data(db)
    
    # Dispatch Celery task to priority queue
    task = refresh_abs_census_complete.apply_async(
        kwargs={
            "delete_existing": body.delete_existing,
            "force": body.force,
        },
        queue="admin_queue",
        priority=10,  # High priority
    )
    
    # Log admin activity
    await log_admin_activity(
        db, admin_user_id, "CENSUS_REFRESH_TRIGGERED",
        f"Task {task.id} — delete_existing={body.delete_existing}, force={body.force}"
    )
    
    return RefreshCensusResponse(
        task_id=str(task.id),
        cache_count_before=cache_count_before,
        status="QUEUED"
    )
```

### 3.5 Admin Backend API Dockerfile

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app
RUN pip install uv

FROM base AS builder
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM base AS runner
COPY --from=builder /app/.venv ./.venv
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
EXPOSE 8082
# Single worker — ClusterIP service, low concurrency needed
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8082", "--workers", "1"]
```

---

## 4. Admin Pages: Specification

### 4.1 Dashboard (`/dashboard`)

**Stat Cards** — loaded via Server Component (calls `adminAction('GET', '/stats')` at render time, no client-side fetch):

| Card | Metric |
|---|---|
| Total Properties | Count from `properties` |
| Reports Ready | Count `status = 'READY'` |
| Failed (7d) | Count `status = 'FAILED'` last 7 days |
| LGA Coverage | Distinct LGAs with ≥ 1 READY report |
| Sales MTD | Distinct users with DOWNLOAD_DEBIT in `credit_ledger` this month |

**Queue Health Panel** — client component, polls `adminAction('GET', '/queue/health')` every 10s via SWR. Shows per queue: waiting / active / completed 24h / failed 24h.

**"Pause / Resume Workers" toggle** — calls `adminAction('POST', '/queue/control', { action, queue })` Server Action.

**Recent Activity Feed** — last 20 rows from `admin_activity_log`, rendered server-side.

---

### 4.2 Scrape Jobs (`/scrape`)

**Trigger Form** — uses `<form action={triggerScrape}>` (Server Action form):

- Scope: radio — By State / By LGA / By Postcode
- State: dropdown (8 options)
- LGA: autocomplete (populated server-side from `adminAction('GET', '/lgas?state=...')`)
- Priority: Normal / High
- Mode: Stale Only / Force Re-scrape
- Dry Run: toggle

On submit → `triggerScrape` Server Action → returns `{ jobs_queued, estimated_completion_minutes }` → toast notification rendered.

**Job History** (`/scrape/history`) — server-rendered table, paginated. Columns: Started At | Scope | Jobs Queued | Completed | Failed | Triggered By.

---

### 4.3 Data Sources (`/data-sources`)

List of all `data_source_configs` rows — server-rendered, filterable by state.

**Add/Edit form** — uses Server Actions `createDataSource` / `updateDataSource`. Fields:
- State (required)
- LGA Name (required) — validated against `spatial_zones`
- Adapter Name (required): dropdown of known adapter classes
- Base URL (required)
- Config JSON (optional): Monaco Editor for adapter-specific selectors
- Enabled toggle

**"Test Adapter"** button → `testDataSource(configId)` Server Action → inline result preview showing `{ success, response_time_ms, sample_text_excerpt }`.

---

### 4.4 Reports (`/reports`)

**Server-rendered list**, filterable + searchable. Filters: State | Status | Confidence.

**Status colour coding:**
- `READY` → green | `PROCESSING` → blue | `QUEUING` → gray | `FAILED` → red

**Single report page** (`/reports/[id]`) — server-rendered two-panel layout:

```
┌──────────────────────────┬─────────────────────────────────────────┐
│  RAW SCRAPED DATA        │  LLM PARSED INSIGHTS                    │
│                          │                                         │
│  Collapsible JSON tree   │  Field-by-field render                  │
│  (syntax highlighted)    │  Each field: value + confidence badge   │
│                          │  [Edit] button → inline form            │
│  Source attribution list │                                         │
│  [Download Raw JSON]     │  overall_confidence badge at top        │
└──────────────────────────┴─────────────────────────────────────────┘
```

Edit flow: clicking [Edit] on a field shows an inline input. On save → `patchReportInsight(id, fieldPath, newValue)` Server Action.

---

### 4.5 Property Detail (`/properties/[id]`)

Shows scrape status, report status, confidence, and raw/parsed data for a single property.

**Action buttons** (invoke Server Actions — no client API calls):
- **Re-scrape** → calls `forceRescrape(propertyId)` → `POST /properties/{id}/force-scrape`
- **Re-AI Validate** → calls `forceAiValidate(propertyId)` → `POST /properties/{id}/re-ai-validate`
- **Delete Report** → calls `deletePropertyReport(propertyId, reportId)` → only if no downloads

---

### 4.6 Properties (`/properties`)

Server-rendered list. Columns: Address | State | LGA | Report Status | Last Scraped | Actions.

**"Trigger Scrape"** action per row → `triggerScrape` Server Action with single `property_id`.

**Coverage Map** — Mapbox GL JS client component showing LGA polygons coloured by scrape %. Polygon data fetched server-side and passed as props.

---

### 4.7 Jobs (`/jobs`) — Flower

```typescript
// apps/admin-web/app/jobs/page.tsx
export default function JobsPage() {
  return (
    <div className="flex flex-col h-screen">
      <div className="p-4 bg-white border-b">
        <h1 className="text-xl font-semibold">Celery Job Monitor</h1>
        <p className="text-sm text-gray-500">
          All Celery queue data. Retry failed tasks, revoke queued tasks, inspect workers.
        </p>
      </div>
      {/* Points to Next.js Route Handler — NOT to admin-backend directly */}
      <iframe src="/api/flower/" className="flex-1 w-full border-0" title="Flower" />
    </div>
  );
}
```

---

### 4.8 Analytics (`/analytics`)

Server-rendered metrics + Recharts (client components for charts, data fetched server-side).

---

## 5. What Flower Handles vs the Admin UI

| Concern | Flower (via `/jobs`) | Admin UI |
|---|---|---|
| Live task list, retry, revoke | ✅ | ❌ |
| Worker health / rate charts | ✅ | Summary panel only |
| Trigger new scrape jobs | ❌ | ✅ `/scrape` |
| Review low-confidence reports | ❌ | ✅ `/reports/review` |
| Edit LLM output fields | ❌ | ✅ Report detail page |
| LGA adapter config management | ❌ | ✅ `/data-sources` |
| Property coverage map | ❌ | ✅ `/properties` |
| Business analytics | ❌ | ✅ `/analytics` |

---

## 6. Flower K3s Deployment

```yaml
# infra/k3s/flower/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flower
  namespace: parceliq
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: flower
          image: mher/flower:2.0
          ports:
            - containerPort: 5555
          env:
            - name: CELERY_BROKER_URL
              valueFrom:
                secretKeyRef: { name: parceliq-secrets, key: REDIS_URL }
            - name: FLOWER_PORT
              value: "5555"
            # No FLOWER_BASIC_AUTH — Admin Backend API + Server Actions handle auth
---
apiVersion: v1
kind: Service
metadata:
  name: flower
  namespace: parceliq
spec:
  type: ClusterIP    # ← NO LoadBalancer, NO NodePort, NO Traefik ingress
  selector:
    app: flower
  ports:
    - port: 5555
      targetPort: 5555
```
