# OZ Property Report – Public API Specification

## 1. Overview

**Application:** `services/public-api`  
**Technology:** Python 3.12, FastAPI, asyncpg, Pydantic v2  
**URL:** Internal-only ClusterIP service; the public web app reaches it via same-origin `/api/*` rewrites and server-side fetches  
**Auth:** Clerk JWT verification (Public Clerk instance)  
**Scope:** Serves the public investor app only. It has no Traefik ingress in K3s and contains zero admin endpoints — those live in the Admin BFF.

---

## 2. Project Structure

```
/services/public-api
├── app/
│   ├── main.py                  # FastAPI app factory, middleware, lifespan
│   ├── config.py                # pydantic-settings (reads env vars)
│   ├── dependencies.py          # get_db, get_current_user, require_auth
│   ├── middleware/
│   │   ├── security_headers.py  # HSTS, X-Frame-Options, etc.
│   │   └── turnstile.py         # Cloudflare Turnstile verification
│   ├── routers/
│   │   ├── search.py            # GET /api/search, GET /api/search/zones
│   │   ├── properties.py        # GET /api/properties/{id}/detail + PDF downloads
│   │   ├── credits.py           # GET /api/credits/me
│   │   ├── credit_purchases.py  # POST /api/credits/checkout, webhook, purchases list
│   │   ├── my_properties.py     # GET /api/properties/my/requested
│   │   ├── users.py             # POST /api/users/sync (Clerk webhook), DELETE /api/users/me
│   │   ├── saved.py             # POST/DELETE/GET /api/saved/{property_id}
│   │   └── health.py            # GET /api/health
│   ├── schemas/
│   │   ├── search.py
│   │   ├── property.py
│   │   └── user.py
│   ├── services/
│   │   ├── property_service.py
│   │   └── email_service.py
│   └── core/
│       ├── clerk.py             # Clerk JWT verification (JWKS)
│       ├── rate_limit.py        # slowapi config
│       └── database.py          # asyncpg pool lifecycle
├── Dockerfile
└── pyproject.toml
```

---

## 3. Clerk JWT Verification (`app/core/clerk.py`)

The Public API verifies every JWT issued by the **Public Clerk instance** using Clerk's JWKS endpoint. No self-issued JWTs — Clerk is the single source of truth.

```python
import httpx
from jose import jwt, JWTError
from functools import lru_cache
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

CLERK_JWKS_URL = settings.CLERK_PUBLIC_JWKS_URL
# e.g. https://clerk.ozpropertyreport.com/.well-known/jwks.json

@lru_cache(maxsize=1)
def get_jwks() -> dict:
    """Cached JWKS fetch. Cache invalidated on app restart."""
    resp = httpx.get(CLERK_JWKS_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()


async def verify_clerk_token(
    credentials: HTTPAuthorizationCredentials = Security(HTTPBearer(auto_error=False)),
) -> dict | None:
    """
    Verifies the Clerk JWT. Returns the decoded payload or None if no token.
    Used for optional auth (anonymous endpoints that return more data when signed in).
    """
    if not credentials:
        return None
    try:
        jwks = get_jwks()
        payload = jwt.decode(
            credentials.credentials,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False},  # Clerk tokens don't use standard aud
        )
        return payload
    except JWTError:
        return None


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Security(HTTPBearer()),
) -> dict:
    """
    Requires a valid Clerk JWT. Raises 401 if missing or invalid.
    Returns decoded payload with sub = clerk_user_id.
    """
    payload = await verify_clerk_token(credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Valid authentication required.")
    return payload


async def get_current_user(
    payload: dict = Depends(require_auth),
    db=Depends(get_db),
) -> User:
    """Looks up the local users row using clerk_user_id from JWT sub claim."""
    clerk_user_id = payload.get("sub")
    row = await db.fetchrow(
        "SELECT * FROM users WHERE clerk_user_id = $1",
        clerk_user_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    return User(**dict(row))
```

---

## 4. REST API Endpoint Contracts

### 4.1 Search

#### `GET /api/search`
**Auth:** Anonymous (Turnstile token required + IP rate limit: 200/hr for bbox, 30/hr for text search)

> **Why different limits?** A user panning around the map can easily trigger dozens of bbox
> queries per minute. Text search (autocomplete) is more expensive and abuse-prone, so it
> has a tighter limit.

**Query Parameters:**
```python
class SearchParams(BaseModel):
    q: str | None = None          # free-text: address, suburb, LGA, school
    bbox: str | None = None       # "minLng,minLat,maxLng,maxLat"
    limit: int = Field(default=100, le=500)

    @model_validator(mode="after")
    def require_q_or_bbox(self):
        if not self.q and not self.bbox:
            raise ValueError("Either 'q' or 'bbox' is required.")
        return self
```

**Response — text search:**
```json
{
  "suggestions": [
    { "type": "ADDRESS", "label": "8 St Lawrence Close, Werribee VIC 3030",
      "property_id": "uuid", "coordinates": [144.6634, -37.9021] },
    { "type": "SCHOOL", "label": "Suzanne Cory High School",
      "zone_id": "uuid", "bbox": [144.5, -37.95, 144.75, -37.80] },
    { "type": "LGA", "label": "Wyndham City Council — VIC",
      "zone_id": "uuid", "bbox": [144.4, -38.1, 144.9, -37.7] }
  ]
}
```

**Response — bbox (GeoJSON FeatureCollection):**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [144.6634, -37.9021] },
      "properties": {
        "id": "uuid",
        "address": "8 St Lawrence Close, Werribee VIC 3030",
        "report_status": "READY",
        "estimated_value": 625000
      }
    }
  ]
}
```

**Key DB query (bounding box):**
```python
BBOX_QUERY = """
    SELECT p.id::text, p.address_string,
           ST_AsGeoJSON(p.geom)::json AS geometry,
           p.estimated_value, pr.status AS report_status
    FROM properties p
    LEFT JOIN LATERAL (
        SELECT status FROM property_reports
        WHERE property_id = p.id
        ORDER BY created_at DESC LIMIT 1
    ) pr ON TRUE
    WHERE p.geom && ST_MakeEnvelope($1, $2, $3, $4, 4326)
    LIMIT $5
"""
```

---

#### `GET /api/search/zones`
**Auth:** Anonymous  
**Query:** `?zone_id=uuid`  
**Response:** GeoJSON Feature with MultiPolygon geometry of the zone

---

### 4.2 Properties

#### `GET /api/properties/{property_id}/detail`
**Auth:** Anonymous (rate limited)

**Response (200):**
```json
{
  "id": "uuid",
  "address": "8 St Lawrence Close, Werribee VIC 3030",
  "state": "VIC",
    "report_status": "READY",
    "education": { "primary_schools": [], "secondary_schools": [] },
    "connectivity": { "nbn_tech_type": "FTTP", "nbn_service_status": "Serviceable" },
    "risk_factors": { "flood": { "risk": "LOW" } },
    "zoning_and_planning": { "zoning_code": "GRZ1" },
    "demographic_snapshot": { "total_population": 1000 }
}
```

#### `GET /api/properties/{property_id}/lite-report/pdf`
**Auth:** Anonymous (rate limited)

Returns a generated or cached lite PDF.

#### `GET /api/properties/{property_id}/full/pdf`
**Auth:** Clerk JWT required

Returns a generated or cached full PDF. Debits 1 credit on generation/first download. Subsequent downloads of the same property report by the same user do not charge credits.

#### `GET /api/properties/{property_id}/full/precheck`
**Auth:** Clerk JWT required

Prechecks if a user needs to pay a credit to view/download the full report, or if they have already unlocked it.

**Response (200):**
```json
{
  "unlocked": false,
  "credits_available": 3,
  "cost_credits": 1,
  "warning": "This property report has not been unlocked yet. Viewing it will consume 1 credit."
}
```

#### `GET /api/properties/my/requested`
**Auth:** Clerk JWT required

Returns a paginated list of properties requested by the current authenticated user.

**Query Parameters:**
- `page`: default 1
- `page_size`: default 20

**Response (200):**
```json
{
  "items": [
    {
      "property_id": "uuid",
      "address": "8 St Lawrence Close, Werribee VIC 3030",
      "state": "VIC",
      "report_id": "uuid",
      "report_status": "READY",
      "requested_at": "2026-05-27T10:00:00Z",
      "ready_at": "2026-05-27T10:05:00Z",
      "has_downloaded_before": true
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_count": 1,
    "total_pages": 1
  }
}
```

#### `POST /api/properties/claim-anonymous-requests`
**Auth:** Clerk JWT required

Claims anonymous requests made with the client's `anon_requester_id` cookie, linking them to the authenticated user's account if within the 7-day claim window.

**Response (200):**
```json
{
  "claimed_count": 2
}
```

### 4.3 Credits & Purchases

#### `GET /api/credits/me`
**Auth:** Clerk JWT required

Retrieves the authenticated user's credit balance details.

**Response (200):**
```json
{
  "daily_credits_balance": 3,
  "purchased_credits_balance": 10,
  "total_credits_balance": 13
}
```

#### `POST /api/credits/checkout`
**Auth:** Clerk JWT required

Initiates a Stripe Checkout Session to purchase credits.

**Request Body:**
```json
{
  "credits": 10
}
```

**Response (200):**
```json
{
  "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_...",
  "order_id": "uuid",
  "credits": 10,
  "total_aud": 10.00
}
```

#### `GET /api/credits/purchases`
**Auth:** Clerk JWT required

Retrieves a list of checkout orders/purchases for the authenticated user.

**Response (200):**
```json
[
  {
    "id": "uuid",
    "credits": 10,
    "unit_price_aud_cents": 100,
    "total_amount_aud_cents": 1000,
    "status": "PAID",
    "provider": "stripe",
    "provider_checkout_id": "cs_test_...",
    "created_at": "2026-05-27T10:15:00Z",
    "paid_at": "2026-05-27T10:16:00Z"
  }
]
```

#### `POST /api/credits/webhook/stripe`
**Auth:** Stripe signature header verification (`Stripe-Signature`)

Webhook endpoint called by Stripe on checkout completion or failure. Handles `checkout.session.completed`, `payment_intent.payment_failed`, and `charge.dispute.created` events. Idempotent — duplicate events are ignored via `payment_event_receipts` table.

---

### 4.3 Reports

#### `POST /api/reports/generate`
**Auth:** Clerk JWT required

> **Note:** This endpoint is defined in the router but calls through to report generation logic integrated into the properties and credits flow. The primary report generation entry point is the credit debit+generation path via the properties router.

```python
class GenerateReportRequest(BaseModel):
    property_id: UUID

@router.post("/generate")
async def generate_report(
    body: GenerateReportRequest,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    # Logic to queue report generation or return existing report
    return {"status": "Generating report"}
```

---

### 4.4 User Sync (Internal)

#### `POST /api/users/sync`
**Auth:** Internal webhook secret header (not Clerk JWT — called from Next.js webhook route)

```python
@router.post("/sync")
async def sync_user(
    body: UserSyncRequest,   # { clerk_user_id, email }
    x_webhook_secret: str = Header(alias="X-Webhook-Secret"),
    db = Depends(get_db),
):
    if x_webhook_secret != settings.INTERNAL_WEBHOOK_SECRET:
        raise HTTPException(401, "Invalid webhook secret.")

    await db.execute(
        """INSERT INTO users (clerk_user_id, email)
           VALUES ($1, $2)
           ON CONFLICT (clerk_user_id) DO UPDATE SET email = EXCLUDED.email""",
        body.clerk_user_id, body.email
    )
    return {"synced": True}
```

---

### 4.5 Saved Properties

#### `POST /api/saved/{property_id}`
**Auth:** Clerk JWT required  
Inserts into `saved_properties`. Returns `409` if already saved.

#### `DELETE /api/saved/{property_id}`
**Auth:** Clerk JWT required  
Deletes from `saved_properties`.

#### `GET /api/saved`
**Auth:** Clerk JWT required  
Returns list of saved property IDs + lite data for the current user.

---

### 4.6 User Account Management

#### `DELETE /api/users/me`
**Auth:** Clerk JWT required

Deletes the user's account and all associated data. Required by the Privacy Act 1988 (Cth) — right to erasure.

**Retention rules:** The credit ledger (`credit_ledger`) and wallet (`user_credit_wallet`) have ON DELETE CASCADE from `users(id)`, so they are automatically removed with the user row. Saved properties are also cascade-deleted. The operation does NOT revoke any credits already consumed.

```python
@router.delete("/me")
async def delete_account(
    current_user: User = Depends(get_current_user),
    db = Depends(get_db),
):
    # saved_properties + credit tables cascade on users.id FK, but run explicit deletes
    # for clarity and ordering control
    await db.execute(
        "DELETE FROM saved_properties WHERE user_id = $1", current_user.id
    )
    # Delete user row (cascades credit_ledger, user_credit_wallet via FK)
    await db.execute("DELETE FROM users WHERE id = $1", current_user.id)
    return {"deleted": True}
```

> **Note:** This only deletes OZ Property Report's local data. The Clerk identity must be deleted separately
> via the Clerk Dashboard or Clerk Backend API. Consider triggering a Clerk user deletion call
> from this endpoint in a future iteration.

---

### 4.7 Health Check

#### `GET /api/health`
**Auth:** None (public, used by K8s liveness/readiness probes and Traefik)

```python
@router.get("/health")
async def health(db = Depends(get_db)):
    try:
        await db.fetchval("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception:
        raise HTTPException(503, {"status": "unhealthy", "db": "unreachable"})
```

---

## 5. Rate Limiting (`app/core/rate_limit.py`)

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

def rate_limit_key(request: Request) -> str:
    """Use Clerk user ID for authenticated requests, IP for anonymous."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            # Decode without full verification just to extract sub for key
            payload = jwt.get_unverified_claims(auth[7:])
            return f"clerk:{payload.get('sub', get_remote_address(request))}"
        except Exception:
            pass
    return get_remote_address(request)

limiter = Limiter(key_func=rate_limit_key)
# Applied per route:
# @limiter.limit("200/hour")  → anonymous bbox search (map pan)
# @limiter.limit("30/hour")   → anonymous text search (autocomplete)
# @limiter.limit("100/hour")  → authenticated endpoints
```

---

## 6. App Factory (`app/main.py`)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_pool(app)
    yield
    await close_db_pool(app)

app = FastAPI(
    title="OZ Property Report Public API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ozpropertyreport.com"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Turnstile-Token"],
    allow_credentials=True,
)

app.include_router(search.router,              prefix="/api/search")
app.include_router(properties.router,          prefix="/api/properties")
app.include_router(credits_router,             prefix="/api/credits")
app.include_router(credit_purchases_router,    prefix="/api/credits")
app.include_router(precheck_router,            prefix="/api/properties")
app.include_router(my_properties.router,       prefix="/api/properties")
app.include_router(users.router,               prefix="/api/users")
app.include_router(saved.router,               prefix="/api/saved")
app.include_router(health.router,              prefix="/api")
```

---

## 7. Dockerfile

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
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
```
