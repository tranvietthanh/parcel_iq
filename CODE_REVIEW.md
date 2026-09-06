# Code Review — parcel_iq (OZ Property Report)

Reviewed: 2026-07-09 · Branch `main` · ~32k LOC of source across 4 Python services (FastAPI + Celery), 2 Next.js apps, shared Pydantic/PDF/migration packages.

Scope: architecture-rule adherence, security & auth, payments/credits, scraper compliance, LLM pipeline, data layer, tests, and repo hygiene. Every concrete claim below was verified against the code; file:line references are given so you can jump straight there.

---

## Remediation status (2026-07-09)

Fixed in this pass: #1 fail-open defaults (all four services default to `production` + reject dev secrets in prod; `admin-action.ts` no longer ships a fallback token), #2 rate limiting (verified JWT + Redis storage), #3 credit-charging GET (now POST with a client `Idempotency-Key` and a truly idempotent `debit_credit`), #5 robots (fail-closed on unverifiable fetch + TTL cache), #7 CORS (config-driven, dev origin only in development), #8–11 hygiene (dead `stripe_service.py` and scratch files removed, settings-based daily grant, AGENTS.md tool paths), plus the UI polling bug. #4 handled by documentation only per decision (review gate stays removed; AGENTS.md corrected). Not done: #6 (admin-web frontend tests). Tests couldn't be executed in this environment (venvs/network unavailable); changes were syntax-checked and affected unit tests updated to match new contracts.

## Summary

The codebase is well-structured and the hardest security surface — the Stripe webhook and credit ledger — is handled with real care (signature verification, idempotency receipts, terminal-state guards, per-user advisory locks). The architecture rules in `AGENTS.md` are respected in the code: no client-side `fetch` to the admin backend, SQL is consistently parameterized, and anonymous-session cookies are hardened.

The issues worth acting on cluster in three places: **fail-open defaults** (secrets and `ENVIRONMENT` that silently degrade to insecure behavior if an env var is missing in prod), **abuse controls that don't hold up** (rate limiting keyed on unverified JWT claims and stored in-memory; a credit-charging `GET` whose idempotency guard is a no-op), and **a legal-compliance control that was removed without updating the risk docs** (the LLM low-confidence review gate).

---

## High priority

### 1. Fail-open secret and environment defaults
Every service config hardcodes insecure fallbacks and defaults `ENVIRONMENT` to `development`:

- `services/admin-backend/app/config.py:20` — `ADMIN_SERVICE_TOKEN = "dev-service-token-change-in-prod"`
- `apps/admin-web/lib/admin-action.ts:8` — same literal on the caller side
- `services/public-api/app/config.py:30` — `INTERNAL_WEBHOOK_SECRET = "dev-webhook-secret-change-in-prod"`
- `services/*/app/config.py` — `ENVIRONMENT: str = "development"` in all four services

If any of these env vars is unset in production, the app does not fail — it runs with a known secret. And because `ENVIRONMENT` defaults to `development`, an unset value silently (a) exposes `/docs` and `/redoc` (`services/public-api/app/main.py:33-34`) and (b) disables Turnstile bot protection, which skips verification entirely in dev (`services/public-api/app/middleware/turnstile.py:26`).

Recommendation: give secrets no default (let Pydantic raise on startup if missing), and default `ENVIRONMENT` to `production` (or require it explicitly). Fail closed, not open.

### 2. Rate limiting is both spoofable and per-pod
`services/public-api/app/core/rate_limit.py`:

- The key function calls `jwt.get_unverified_claims()` (line 20) to read `sub`. It's unverified, so a client can forge or rotate the `sub` value on each request to evade its per-user limit (e.g. the `60/hour` PDF-download cap) or to target another user's bucket.
- `Limiter(key_func=...)` (line 28) is constructed with no `storage_uri`, so slowapi uses in-memory storage. With more than one API replica (this is a K8s deployment), each pod counts independently, multiplying every limit by the replica count.

Recommendation: derive the rate-limit identity from the already-verified request context (the `require_auth`/`verify_clerk_token` payload) rather than re-decoding without verification, and point slowapi at Redis (which is already in the stack).

### 3. Credit-charging `GET` with a no-op idempotency guard
`services/public-api/app/routers/properties.py:215-312` — `GET /{property_id}/full/pdf` debits a credit as a side effect. Two problems:

- It's a **state-mutating GET**. Browsers, link prefetchers, and proxies may issue it speculatively, and it's safe to retry from the client's perspective — each hit can cost a credit.
- The idempotency key is `f"download:{user}:{report_id}:{uuid4().hex[:8]}"` (line 289) — a fresh random suffix per request. The ledger insert's `ON CONFLICT (idempotency_key) DO NOTHING` (`services/public-api/app/core/credits.py:283`) therefore never matches a prior row, so the dedup does nothing. The code comment claims it "prevents accidental double-submission … via ON CONFLICT," but a double-click or retry produces two different keys and charges twice.

Recommendation: make this a `POST`, and use a deterministic idempotency key (client-supplied token, or `user+report` scoped to a window) so genuine retries are truly idempotent while intentional re-downloads remain a deliberate action.

---

## Medium priority

### 4. The LLM low-confidence review gate was removed — docs still call it non-negotiable
`services/llm-parser-worker/app/tasks.py:139-166` computes `confidence` and then sets `new_status = "READY"` **unconditionally** (line 143, under a comment "Determine final status"). Confidence is stored but never gates anything. Migration `023_on_demand_property_ingestion` confirms this was deliberate: it maps `REVIEW_REQUIRED → READY`, drops the `review_flag` column and its index, and collapses the status enum to `QUEUING/PROCESSING/READY/FAILED`. The admin stats field is a compat stub (`services/admin-backend/app/routers/stats.py:79` → hardcoded `0`).

The problem is governance, not a crash: `AGENTS.md` still lists "Disabling `review_flag` check … this is a legal risk mitigation" as a non-negotiable rule, and `docs/07-legal-compliance.md` is cited as its basis. A legally-motivated control was removed without updating the risk documentation. Either the removal is intended (then update `AGENTS.md` and the legal doc, and record the decision), or it's a regression that should be restored. This deserves an explicit product/legal decision rather than sitting as a silent contradiction.

### 5. robots.txt checker fails open and never expires its cache
`services/scraper-worker/app/utils/robots.py`:

- On any fetch error/timeout, and on any non-200, it sets `allow_all = True` (lines 35-39, 67-69) — i.e. it scrapes when it *couldn't confirm* the path is allowed. Given the module's own docstring calls compliance "non-negotiable," failing open on a transient error is inconsistent with that stance.
- `_fetch_robots` is wrapped in an unbounded `@lru_cache` with no TTL (line 23), so a fetched `robots.txt` is cached for the life of the worker process and never re-checked.

Recommendation: fail closed (or at least treat network errors differently from a confirmed-absent robots.txt), and add a TTL so policy changes are picked up.

### 6. No frontend tests for the admin app
`apps/admin-web` has 0 test files; all admin mutations flow through Server Actions in `apps/admin-web/actions/` (6 files) that are untested. The Python services are reasonably covered (public-api 15, scraper 15, admin-backend 7, llm 7 unit-test files) and `public-web` has 9. The admin surface — the one with privileged write access — is the least tested.

### 7. CORS ships a dev origin to production
`services/public-api/app/main.py:45-51` hardcodes `http://localhost:3000` in `allow_origins` alongside the prod domain, with `allow_credentials=True`. Low risk in practice, but dev origins shouldn't be in the prod allow-list; drive the list from `ENVIRONMENT`/config.

---

## Low priority / hygiene

### 8. Dead code contradicting current pricing
`services/public-api/app/services/stripe_service.py` implements the old per-report **$39** checkout (`REPORT_PRICE_CENTS = 3900`) and is not called anywhere — the product moved to the credit model. It also sets `stripe.api_key` at import time (line 9). Delete it to avoid confusion about which pricing path is live.

### 9. Scratch files committed to the repo
`test_stats.py` and `test_pydantic.py` at the repo root (the former with a hardcoded dev DB DSN) and `tmp/db_cols.py` are ad-hoc scripts, not part of any test target (nothing in the `Makefile` references them). `apps/admin-web/PHASE7_SUMMARY.md` is phase-notes clutter. Move to a `scratch/` dir that's gitignored, or delete.

### 10. Machine-specific paths in AGENTS.md
`AGENTS.md:15-17` hardcodes `/home/thanhtran/.nvm/versions/node/v24.6.0/bin/...` for tooling. This won't resolve for other contributors or CI; prefer `npx`/`$PATH` resolution or an env var.

### 11. `get_daily_grant_amount()` re-reads the environment on every call
`services/public-api/app/core/credits.py:31-37` calls `os.environ.get("DAILY_CREDIT_GRANT", …)` on each invocation instead of reading validated config once at startup. Minor, but it bypasses the settings layer and isn't validated on boot.

---

## What's done well (worth keeping)

- **Stripe webhook handling** (`services/public-api/app/routers/credit_purchases.py`): signature verification, event-receipt idempotency, `TERMINAL_STATES` guard, and the same per-user advisory lock as the debit path — this is the right shape.
- **SQL safety**: parameterized `$1/$2` throughout; the f-string queries in the admin routers interpolate only placeholder indices and static column lists, never user data.
- **Server Action boundary**: no client component fetches the admin backend; `admin-action.ts` verifies Clerk session + org before every call and forwards the actor ID for audit.
- **Anon-session cookies** (`my_properties.py:34-46`): `HttpOnly`, `Secure`, `SameSite=strict`, scoped path, 7-day claim window.
- **JWKS handling** (`core/clerk.py`): TTL cache with a rotation-aware retry on verification failure.

---

## Suggested order of fixes

1. Remove fail-open defaults (#1) — smallest change, largest risk reduction.
2. Fix rate-limit keying + storage (#2) and the credit-charging GET (#3) — direct abuse/revenue exposure.
3. Make a decision on the review gate and reconcile the docs (#4).
4. robots.txt fail-closed + TTL (#5), then the hygiene items.
