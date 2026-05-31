# OZ Property Report – Database Schema & Indexing Specification

## 1. Overview

**Engine:** PostgreSQL 16 + PostGIS 3.4  
**Deployment:** StatefulSet in K3s, 50Gi PVC, internal ClusterIP only  
**Connection Pooling:** PgBouncer sidecar (transaction mode: API 20 conns, Admin BFF 10 conns, Workers 10 conns)

**Key design decision — Clerk as identity provider:** The `users` table does **not** store passwords or OAuth tokens. Clerk owns all authentication state. The `users` table stores only the `clerk_user_id` (from Clerk's JWT `sub` claim) as the link between Clerk's identity and OZ Property Report's local data (saved properties, unlocked reports). Admin users are managed entirely in Clerk's Dashboard and have **no row** in the `users` table.

---

## 2. Full DDL (Run in Order)

```sql
-- ============================================================
-- EXTENSIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

> **Important:** `pg_stat_statements` requires `shared_preload_libraries = 'pg_stat_statements'`
> in `postgresql.conf`. In local development, this is configured via the Docker Compose command:
> ```yaml
> postgres:
>   command: postgres -c shared_preload_libraries=pg_stat_statements -c pg_stat_statements.track=all
> ```
> In production K3s, add this to the PostgreSQL StatefulSet as a command override or
> via a custom `postgresql.conf` mounted as a ConfigMap.


-- ============================================================
-- TABLE: spatial_zones
-- LGA boundaries, suburb boundaries, school catchments.
-- Covers all Australian states/territories.
-- ============================================================
CREATE TABLE spatial_zones (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_type   VARCHAR(30) NOT NULL
                    CHECK (zone_type IN ('LGA', 'SUBURB', 'SCHOOL_CATCHMENT')),
    name        VARCHAR(255) NOT NULL,
    state       CHAR(3) NOT NULL
                    CHECK (state IN ('VIC','NSW','QLD','SA','WA','TAS','ACT','NT')),
    slug        VARCHAR(300) NOT NULL DEFAULT '',
    geom        GEOMETRY(MultiPolygon, 4326) NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_spatial_zones_geom       ON spatial_zones USING GiST (geom);
CREATE INDEX idx_spatial_zones_type       ON spatial_zones (zone_type);
CREATE INDEX idx_spatial_zones_state      ON spatial_zones (state);
CREATE INDEX idx_spatial_zones_type_state ON spatial_zones (zone_type, state);
CREATE INDEX idx_spatial_zones_name_trgm  ON spatial_zones USING GIN (name gin_trgm_ops);
CREATE UNIQUE INDEX idx_spatial_zones_slug ON spatial_zones (slug);


-- ============================================================
-- TABLE: properties
-- One row per unique Australian address (GNAF ID).
-- ============================================================
CREATE TABLE properties (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gnaf_pid            VARCHAR(50) UNIQUE NOT NULL,
    address_string      TEXT NOT NULL,
    address_tokens      TSVECTOR,
    slug                VARCHAR(400) NOT NULL DEFAULT '',
    geom                GEOMETRY(Point, 4326) NOT NULL,
    parcel_geom         GEOMETRY(Polygon, 4326),
    state               CHAR(3) NOT NULL
                            CHECK (state IN ('VIC','NSW','QLD','SA','WA','TAS','ACT','NT')),
    beds                SMALLINT,
    baths               SMALLINT,
    cars                SMALLINT,
    land_size_sqm       INT,
    estimated_value     NUMERIC(12, 2),
    estimated_rent      NUMERIC(8, 2),
    lga_id              UUID REFERENCES spatial_zones(id),
    suburb_id           UUID REFERENCES spatial_zones(id),
    last_scraped_at     TIMESTAMP WITH TIME ZONE,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_properties_geom       ON properties USING GiST (geom);
CREATE INDEX idx_properties_parcel     ON properties USING GiST (parcel_geom);
CREATE INDEX idx_properties_fts        ON properties USING GIN (address_tokens);
CREATE INDEX idx_properties_trgm       ON properties USING GIN (address_string gin_trgm_ops);
CREATE INDEX idx_properties_scraped_at ON properties (last_scraped_at);
CREATE INDEX idx_properties_state      ON properties (state);
CREATE UNIQUE INDEX idx_properties_slug ON properties (slug);

CREATE OR REPLACE FUNCTION sync_address_tokens()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.address_tokens := to_tsvector('english', COALESCE(NEW.address_string, ''));
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_properties_address_tokens
    BEFORE INSERT OR UPDATE OF address_string ON properties
    FOR EACH ROW EXECUTE FUNCTION sync_address_tokens();


-- ============================================================
-- TABLE: property_school_catchments
-- Many-to-many: properties ↔ school zones (PostGIS-populated).
-- ============================================================
CREATE TABLE property_school_catchments (
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    zone_id     UUID NOT NULL REFERENCES spatial_zones(id) ON DELETE CASCADE,
    PRIMARY KEY (property_id, zone_id)
);

CREATE INDEX idx_psc_property ON property_school_catchments (property_id);
CREATE INDEX idx_psc_zone     ON property_school_catchments (zone_id);


-- ============================================================
-- TABLE: property_reports
-- One row per scrape cycle per property.
-- ============================================================
CREATE TABLE property_reports (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id             UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    requested_by_user_id    UUID REFERENCES users(id) ON DELETE SET NULL,
    status                  VARCHAR(30) NOT NULL DEFAULT 'QUEUING'
                                CHECK (status IN (
                                    'QUEUING',
                                    'PROCESSING',
                                    'READY',
                                    'FAILED'
                                )),
    raw_scraped_data        JSONB,
    llm_parsed_insights     JSONB,
    confidence_scores       JSONB,
    overall_confidence      VARCHAR(10)
                                CHECK (overall_confidence IN ('HIGH', 'MEDIUM', 'LOW')),
    scraper_version         VARCHAR(20),
    llm_model_version       VARCHAR(60),
    error_message           TEXT,
    retry_count             SMALLINT NOT NULL DEFAULT 0,
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_reports_property_id  ON property_reports (property_id);
CREATE INDEX idx_reports_status       ON property_reports (status);
CREATE INDEX idx_reports_ready_latest ON property_reports (property_id, created_at DESC)
    WHERE status = 'READY';
CREATE INDEX idx_reports_requested_by ON property_reports (requested_by_user_id)
    WHERE requested_by_user_id IS NOT NULL;


-- ============================================================
-- TABLE: users
-- Local mirror of Clerk user identities for public investors.
-- NOTE: Passwords and OAuth tokens are NOT stored here.
--       Clerk is the single source of truth for authentication.
--       Admin users are NOT in this table — they exist only in Clerk.
-- ============================================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clerk_user_id   VARCHAR(255) UNIQUE NOT NULL,  -- Clerk's user ID (from JWT sub)
    email           VARCHAR(255) UNIQUE NOT NULL,  -- mirrored from Clerk for display
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen_at    TIMESTAMP WITH TIME ZONE
);

-- Primary lookup: Clerk user ID from JWT sub claim
CREATE INDEX idx_users_clerk_id ON users (clerk_user_id);
CREATE INDEX idx_users_email    ON users (email);


-- ============================================================
-- CREDIT SYSTEM TABLES
-- Implements ledger-backed credit entitlement replacing unlocked_reports.
-- Migration 022 drops unlocked_reports; migrations 024, 026a, 026 add these.
-- ============================================================

-- user_credit_wallet: per-user balance snapshot
CREATE TABLE user_credit_wallet (
    user_id                   UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    daily_grant_credits       INT  NOT NULL DEFAULT 0 CHECK (daily_grant_credits >= 0),
    daily_used_credits        INT  NOT NULL DEFAULT 0 CHECK (daily_used_credits >= 0),
    purchased_credits_balance INT  NOT NULL DEFAULT 0 CHECK (purchased_credits_balance >= 0),
    wallet_day_au             DATE NOT NULL DEFAULT CURRENT_DATE,
    updated_at                TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_wallet_user_id ON user_credit_wallet (user_id);


-- credit_entry_type: allowed ledger entry types
CREATE TYPE credit_entry_type AS ENUM (
    'DAILY_GRANT',       -- free daily credit reset
    'DOWNLOAD_DEBIT',    -- report generation debit (negative)
    'ADMIN_TOPUP',       -- admin-granted credits (positive)
    'PURCHASE_CREDIT'    -- paid Stripe purchase (positive)
);

-- credit_ledger: immutable audit trail
CREATE TABLE credit_ledger (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entry_type          credit_entry_type NOT NULL,
    delta_credits       INT  NOT NULL
                             CHECK (
                                 (entry_type = 'DOWNLOAD_DEBIT' AND delta_credits < 0)
                                 OR (entry_type IN ('DAILY_GRANT', 'ADMIN_TOPUP', 'PURCHASE_CREDIT') AND delta_credits > 0)
                             ),
    balance_after       INT  NOT NULL,
    idempotency_key     VARCHAR(255) UNIQUE,
    related_property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    related_report_id   UUID REFERENCES property_reports(id) ON DELETE SET NULL,
    related_order_id    UUID,  -- FK to credit_purchase_orders, added in migration 026
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_ledger_user_id    ON credit_ledger (user_id, created_at DESC);
CREATE INDEX idx_ledger_entry_type ON credit_ledger (entry_type, created_at DESC);
CREATE INDEX idx_ledger_property   ON credit_ledger (related_property_id)
    WHERE related_property_id IS NOT NULL;
CREATE UNIQUE INDEX ux_ledger_idempotency ON credit_ledger (idempotency_key)
    WHERE idempotency_key IS NOT NULL;


-- credit_purchase_status enum
CREATE TYPE credit_purchase_status AS ENUM ('PENDING', 'PAID', 'FAILED');

-- credit_purchase_orders: one row per Stripe checkout session
CREATE TABLE credit_purchase_orders (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                     UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    credits                     INT  NOT NULL CHECK (credits >= 5),
    unit_price_aud_cents        INT  NOT NULL CHECK (unit_price_aud_cents > 0),
    total_amount_aud_cents      INT  NOT NULL GENERATED ALWAYS AS (credits * unit_price_aud_cents) STORED,
    status                      credit_purchase_status NOT NULL DEFAULT 'PENDING',
    provider                    TEXT NOT NULL DEFAULT 'stripe',
    provider_checkout_id        TEXT UNIQUE,
    provider_payment_intent_id  TEXT UNIQUE,
    provider_event_id_last      TEXT,
    created_at                  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    paid_at                     TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_purchase_orders_user_id ON credit_purchase_orders (user_id, created_at DESC);
CREATE INDEX idx_purchase_orders_status  ON credit_purchase_orders (status, created_at DESC);


-- payment_event_receipts: idempotency guard for Stripe webhook replays
CREATE TABLE payment_event_receipts (
    provider_event_id   TEXT PRIMARY KEY,
    provider            TEXT NOT NULL DEFAULT 'stripe',
    order_id            UUID REFERENCES credit_purchase_orders(id) ON DELETE SET NULL,
    processed_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);


-- ============================================================
-- TABLE: saved_properties
-- User bookmarks (free feature, requires login).
-- ============================================================
CREATE TABLE saved_properties (
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    notes       TEXT,
    saved_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (user_id, property_id)
);

CREATE INDEX idx_saved_user ON saved_properties (user_id);


-- ============================================================
-- TABLE: data_source_configs
-- Admin-configured adapter registry. One row per LGA.
-- Adding a new LGA = one INSERT, no code change.
-- ============================================================
CREATE TABLE data_source_configs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lga_name         VARCHAR(255) NOT NULL,
    state            CHAR(3) NOT NULL
                         CHECK (state IN ('VIC','NSW','QLD','SA','WA','TAS','ACT','NT')),
    adapter_name     VARCHAR(100) NOT NULL,
    base_url         TEXT NOT NULL,
    config           JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    last_verified_at TIMESTAMP WITH TIME ZONE,
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (lga_name, state)
);

CREATE INDEX idx_dsc_state ON data_source_configs (state);


-- ============================================================
-- TABLE: admin_activity_log
-- Audit trail of all admin actions. Clerk admin user ID stored
-- as a string (not FK — admin users are not in the users table).
-- ============================================================
CREATE TABLE admin_activity_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clerk_admin_id  VARCHAR(255) NOT NULL,   -- Clerk admin user ID (not FK)
    admin_email     VARCHAR(255),            -- mirrored from Clerk JWT for display
    action          VARCHAR(50) NOT NULL,
                        -- 'SCRAPE_TRIGGERED', 'AI_VALIDATE_TRIGGERED',
                        -- 'REPORT_DELETED', 'CONFIG_CREATED', 'CONFIG_UPDATED'
    target_id       VARCHAR(255),            -- UUID of affected resource
    detail          TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_activity_clerk_admin ON admin_activity_log (clerk_admin_id);
CREATE INDEX idx_activity_created     ON admin_activity_log (created_at DESC);
CREATE INDEX idx_activity_action      ON admin_activity_log (action);


-- ============================================================
-- TABLE: abs_census_data
-- Persistent cache of ABS Census demographics by SA2 code.
-- Downloaded once via Celery refresh task, queried per-property.
-- Eliminates 6.5s API latency per property (11x speedup after first cache hit).
-- ============================================================
CREATE TABLE abs_census_data (
    id                                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sa2_code_2021                       VARCHAR(9) UNIQUE NOT NULL,
    median_household_income_weekly_aud  INTEGER,
    owner_occupier_percent              NUMERIC(5, 2),
    raw_data                            JSONB NOT NULL,  -- Full SDMX-JSON response for audit
    fetched_at                          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at                          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at                          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_abs_census_sa2_code ON abs_census_data (sa2_code_2021);
CREATE INDEX idx_abs_census_fetched_at ON abs_census_data (fetched_at DESC);


-- ============================================================
-- TABLE: gnaf_addresses (Read-Only Reference Table)
-- Bulk imported from open data. Never modified by the app.
-- ~15 million rows covering all of Australia.
-- ============================================================
CREATE TABLE gnaf_addresses (
    gnaf_pid       VARCHAR(50) PRIMARY KEY,
    address_string TEXT NOT NULL,
    latitude       DOUBLE PRECISION NOT NULL,
    longitude      DOUBLE PRECISION NOT NULL,
    postcode       CHAR(4),
    suburb         VARCHAR(100),
    state          CHAR(3) NOT NULL
                       CHECK (state IN ('VIC','NSW','QLD','SA','WA','TAS','ACT','NT')),
    geom           GEOMETRY(Point, 4326)
                       GENERATED ALWAYS AS (
                           ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
                       ) STORED
);

CREATE INDEX idx_gnaf_geom     ON gnaf_addresses USING GiST (geom);
CREATE INDEX idx_gnaf_postcode ON gnaf_addresses (postcode);
CREATE INDEX idx_gnaf_state    ON gnaf_addresses (state);
CREATE INDEX idx_gnaf_suburb   ON gnaf_addresses USING GIN (suburb gin_trgm_ops);
```

---

## 3. Critical Queries

### 3.1 Bounding Box Map Load (< 150ms target)

```sql
SELECT p.id::text, p.address_string,
       ST_AsGeoJSON(p.geom)::json AS geometry,
       p.estimated_value, pr.status AS report_status
FROM properties p
LEFT JOIN LATERAL (
    SELECT status FROM property_reports
    WHERE property_id = p.id ORDER BY created_at DESC LIMIT 1
) pr ON TRUE
WHERE p.geom && ST_MakeEnvelope($1, $2, $3, $4, 4326)
LIMIT $5;
```

### 3.2 Properties Within a School Catchment

```sql
SELECT p.id, p.address_string, p.estimated_value
FROM properties p
JOIN spatial_zones z ON ST_Contains(z.geom, p.geom)
WHERE z.zone_type = 'SCHOOL_CATCHMENT'
  AND z.name = $1 AND z.state = $2;
```

### 3.3 Address Autocomplete (Trigram)

```sql
SELECT id::text, address_string, state,
       ST_X(geom) AS lng, ST_Y(geom) AS lat,
       similarity(address_string, $1) AS score
FROM properties
WHERE address_string % $1
ORDER BY score DESC
LIMIT 10;
```

### 3.4 Credit Balance Check (Called Before Full Report Download)

```sql
-- Check if user has sufficient credits before debiting
SELECT
    user_id,
    GREATEST(0, daily_grant_credits - daily_used_credits) AS daily_remaining,
    purchased_credits_balance,
    GREATEST(0, daily_grant_credits - daily_used_credits)
        + purchased_credits_balance AS total_balance
FROM user_credit_wallet
WHERE user_id = $1;
```

### 3.5 Stale Properties in an LGA (Admin Batch Trigger)

```sql
SELECT p.id::text, p.gnaf_pid, p.address_string,
       ST_Y(p.geom) AS lat, ST_X(p.geom) AS lng
FROM properties p
JOIN spatial_zones z ON p.lga_id = z.id
WHERE z.name = $1 AND z.state = $2
  AND (p.last_scraped_at IS NULL
       OR p.last_scraped_at < NOW() - INTERVAL '30 days')
ORDER BY p.last_scraped_at ASC NULLS FIRST;
```

### 3.6 G-NAF Addresses Within an LGA Boundary

```sql
SELECT g.gnaf_pid, g.address_string, g.latitude, g.longitude
FROM gnaf_addresses g
JOIN spatial_zones z ON ST_Contains(z.geom, g.geom)
WHERE z.name = $1 AND z.state = $2 AND z.zone_type = 'LGA';
```

---

## 4. `llm_parsed_insights` JSONB Schema

All LLM output is stored as JSONB. Fields the LLM cannot determine must be explicitly `null`.

```json
{
  "zoning_and_planning": {
    "zoning_code": "GRZ1",
    "zoning_label": "General Residential Zone (Schedule 1)",
    "overlays": ["DCPO2"],
    "overlay_descriptions": ["Development Contribution Plan Overlay (Schedule 2)"],
    "subdivision_potential": "Minimum lot size 300sqm. Dual-occupancy likely feasible.",
    "confidence_score": 0.91
  },
  "risk_factors": {
    "flood": { "risk": "LOW", "detail": "Outside 1-in-100 year flood zone.", "confidence_score": 0.97 },
    "bushfire": { "risk": "NONE", "detail": "Not within a Bushfire Management Overlay.", "confidence_score": 0.99 },
    "crime_density": { "rating": "BELOW_AVERAGE", "detail": "12% below LGA average (2024).", "confidence_score": 0.75 }
  },
  "infrastructure": [
    {
      "type": "TRANSPORT",
      "description": "Wyndham Vale Station upgrade",
      "distance_km": 3.2,
      "expected_completion_year": 2028,
      "source_url": "https://...",
      "confidence_score": 0.88
    }
  ],
  "roi_scenarios": {
    "disclaimer": "Illustrative scenarios only. Not financial advice.",
    "scenarios": [
      {
        "label": "Conservative",
        "assumptions": { "interest_rate_percent": 6.5, "weekly_rent_aud": 430,
                         "vacancy_rate_percent": 5.0, "maintenance_percent": 1.0,
                         "council_rates_annual_aud": 1800, "insurance_annual_aud": 1400 },
        "gross_yield_percent": 3.58, "net_yield_percent": 2.91, "annual_cash_flow_aud": -4200
      },
      {
        "label": "Base",
        "assumptions": { "interest_rate_percent": 6.0, "weekly_rent_aud": 450,
                         "vacancy_rate_percent": 3.0, "maintenance_percent": 0.8,
                         "council_rates_annual_aud": 1800, "insurance_annual_aud": 1400 },
        "gross_yield_percent": 3.74, "net_yield_percent": 3.12, "annual_cash_flow_aud": -1800
      },
      {
        "label": "Optimistic",
        "assumptions": { "interest_rate_percent": 5.5, "weekly_rent_aud": 470,
                         "vacancy_rate_percent": 2.0, "maintenance_percent": 0.5,
                         "council_rates_annual_aud": 1800, "insurance_annual_aud": 1400 },
        "gross_yield_percent": 3.91, "net_yield_percent": 3.45, "annual_cash_flow_aud": 1200
      }
    ]
  },
  "demographic_snapshot": {
    "suburb": "Werribee",
    "median_household_weekly_income_aud": 82400,
    "owner_occupier_percent": 62.0,
    "median_age": 34,
    "primary_household_type": "Families with children",
    "source": "ABS Census 2021",
    "confidence_score": 1.0
  }
}
```

---

## 5. `confidence_scores` JSONB Schema

```json
{
  "zoning_and_planning": 0.91,
  "flood": 0.97,
  "bushfire": 0.99,
  "crime_density": 0.75,
  "infrastructure": 0.88,
  "demographics": 1.0,
  "overall_avg": 0.917
}
```

**`overall_confidence` mapping (stored in `property_reports.overall_confidence`):**
- `HIGH` — overall_avg ≥ 0.85
- `MEDIUM` — overall_avg ≥ 0.65
- `LOW` — overall_avg < 0.65

Reports with `overall_confidence = 'LOW'` are still visible to users — confidence is informational only.

---

## 6. Database Migrations (Alembic)

```
/shared/db-migrations/
├── alembic.ini
├── env.py
└── versions/
    ├── 001_create_extensions.py
    ├── 002_create_spatial_zones.py
    ├── 003_create_properties.py
    ├── 004_create_property_school_catchments.py
    ├── 005_create_property_reports.py
    ├── 006_create_users.py              ← clerk_user_id, no password_hash
    ├── 007_create_unlocked_reports.py   ← dropped by 022
    ├── 008_create_saved_properties.py
    ├── 009_create_data_source_configs.py
    ├── 010_create_admin_activity_log.py ← clerk_admin_id (string, not FK)
    ├── 011_create_gnaf_addresses.py
    ├── 012_add_abs_census_data.py
    ├── 013_add_nbn_locations.py
    ├── 014_create_vic_plan_cache.py
    ├── 015_add_property_report_columns.py
    ├── 016_add_lga_id_to_properties.py
    ├── 017_create_schools_table.py
    ├── 018_add_report_id_to_unlocked.py
    ├── 019_add_anon_request_columns.py
    ├── 020_add_suburbs.py
    ├── 021_add_credit_precheck_columns.py
    ├── 022_drop_unlocked_reports.py     ← removes unlocked_reports table
    ├── 023_add_stripe_columns.py
    ├── 024_create_credit_system.py      ← user_credit_wallet, credit_ledger
    ├── 025_add_requested_by_to_reports.py
    ├── 026a_add_purchase_credit_enum.py ← adds PURCHASE_CREDIT to credit_entry_type
    └── 026_credit_purchase_orders.py   ← credit_purchase_orders, payment_event_receipts
```

Run before deploying:
```bash
DATABASE_URL=postgresql://... alembic upgrade head
```

G-NAF bulk import (one-time):
```bash
python infra/scripts/import_gnaf.py --state ALL --source /data/gnaf_feb2026.zip
# Uses COPY for bulk performance — ~15 min for all states
```

---

## 7. Backup Strategy (MVP)

- WAL archiving to MinIO `ozpr-db-backups` bucket (continuous)
- Daily `pg_dump` via Celery Beat (compressed, 30-day retention)
- `gnaf_addresses` backed up from source file — not via WAL
