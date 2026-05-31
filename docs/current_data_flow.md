# OZ Property Report — Current Data Flow

## Summary

OZ Property Report has **two distinct data phases**:
1. **One-time bootstrap imports** — large reference datasets loaded at setup time
2. **Continuous scrape-and-ingest pipeline** — per-property enrichment via government APIs, council portals, and LLM parsing

---

## Phase 1 — One-Time Bootstrap Imports

These are bulk imports that seed the database before any scraping can occur. The pipeline must be run in order.

### Step 1 · ABS LGA Boundary Shapefiles → `spatial_zones`

| Attribute | Value |
|---|---|
| Source | Australian Bureau of Statistics (ABS) |
| URL | `abs.gov.au/statistics/standards/...asgs` |
| Format | `.shp` (Shapefile / GDA2020) |
| Volume | ~546 LGA polygons |
| Time | 1–2 minutes |

**What gets stored:**

```sql
spatial_zones (
  zone_type   = 'LGA' | 'SUBURB' | 'SCHOOL_CATCHMENT',
  name        TEXT,
  state       CHAR(3),
  geom        GEOMETRY(MultiPolygon, 4326),  -- GiST indexed
  metadata    JSONB
)
```

This table is also used for **suburb boundaries** and **school catchment zones** via the same import script with a different `type=` parameter.

---

### Step 2 · G-NAF (Geocoded National Address File) → `gnaf_addresses`

| Attribute | Value |
|---|---|
| Source | Geoscape Australia (open data) |
| URL | `data.gov.au/data/dataset/geocoded-national-address-file-g-naf` |
| Format | CSV (multiple files: STATE_DETAIL, ADDRESS_DETAIL, ADDRESS_DEFAULT_GEOCODE) |
| Volume | ~15 million rows (all of Australia) |
| Size | ~500 MB compressed, ~2 GB uncompressed |
| Time | 5–10 minutes (uses PostgreSQL `COPY` bulk loader) |
| Update freq | Monthly (Geoscape releases monthly) |

**What gets stored:**

```sql
gnaf_addresses (
  gnaf_pid        VARCHAR(50) PRIMARY KEY,   -- unique address identifier
  address_string  TEXT,
  latitude        DOUBLE PRECISION,
  longitude       DOUBLE PRECISION,
  postcode        CHAR(4),
  suburb          VARCHAR(100),
  state           CHAR(3),
  geom            GEOMETRY(Point, 4326)       -- generated column, GiST indexed
)
```

> G-NAF is a **read-only reference table** — the app never modifies it.

---

### Step 3 · GNAF → `properties` (thin import, no spatial join)

After Steps 1 and 2, a script performs a **thin insert** of GNAF addresses into `properties` — no spatial join at import time. `lga_id` starts as NULL and is resolved lazily when the first scrape is requested for each property.

```sql
INSERT INTO properties (gnaf_pid, address_string, geom, state)
SELECT gnaf_pid, address_string, geom, state
FROM gnaf_addresses
ON CONFLICT (gnaf_pid) DO NOTHING;
```

| Attribute | Value |
|---|---|
| Volume | ~15.3 million property records |
| Time | ~20 minutes (no spatial join) |
| `lga_id` | NULL at import — resolved lazily via `ST_Contains` at first scrape request |

**What gets stored per property:**

```sql
properties (
  gnaf_pid            -- link back to G-NAF
  address_string      TEXT,
  address_tokens      TSVECTOR,        -- full-text search
  geom                GEOMETRY(Point, 4326),
  parcel_geom         GEOMETRY(Polygon, 4326),
  state               CHAR(3),
  beds, baths, cars   SMALLINT,        -- populated later from scraping
  land_size_sqm       INT,
  estimated_value     NUMERIC(12,2),
  estimated_rent      NUMERIC(8,2),
  lga_id              UUID → spatial_zones,  -- NULL until first scrape request
  suburb_id           UUID → spatial_zones,
  last_scraped_at     TIMESTAMP
)
```

---

### Step 4 · ABS Census Pre-Cache → `abs_census_data` (optional but recommended)

An admin can trigger a Celery task that bulk-downloads all ~2,200 SA2-level census records in one shot (5–10 min), rather than fetching them one-by-one during scraping.

| Attribute | Value |
|---|---|
| Source | ABS DataAPI (`api.data.abs.gov.au`) |
| Datasets | G17_2021 (household income) + G46_2021 (dwelling ownership) |
| Volume | ~2,200 SA2 statistical areas |
| Per-property benefit | Eliminates a 3–6s API call (11× speedup after cache hit) |

**What gets stored:**

```sql
abs_census_data (
  sa2_code_2021                       VARCHAR(9) UNIQUE,
  median_household_income_weekly_aud  INTEGER,
  owner_occupier_percent              NUMERIC(5,2),
  raw_data                            JSONB   -- full SDMX-JSON for audit
)
```

---

## Phase 2 — Continuous Scrape & Ingest Pipeline

This is the main data ingestion engine. Each property moves through a pipeline of adapters and then the LLM.

### Trigger Sources

| Who triggers | How | Priority |
|---|---|---|
| Authenticated User | Public API → `/api/properties/{id}/request-scrape` | High (5) |
| Anonymous User | Public API → `/api/properties/{id}/request-scrape` | Low (7) |
| Admin | Admin Backend API → `/properties/{id}/force-scrape` | Configurable |

---

### The Scrape Pipeline — Per Property

```
gnaf_addresses / properties
        │
        ▼  [Celery task: scrape_property → data_acquisition_queue]
┌───────────────────────────────────────────────┐
│  PARALLEL ADAPTER EXECUTION (ThreadPoolExecutor)
│
│  ① National: ABS Census Adapter
│  ② National: NBN Co Adapter
│  ③ State:    VicPlanAdapter (VIC) or GenericStateAdapter (other states)
│  ④ Council:  TechOneCouncilAdapter / ObjectiveCouncilAdapter / GenericHtmlAdapter
│              (only if data_source_configs row exists for this LGA)
└───────────────────────────────────────────────┘
        │
        ▼  merge_adapter_results()
        │  raw JSON stored in MinIO (audit trail)
        │  raw_scraped_data stored in property_reports
        ▼  [Celery task: parse_with_llm → llm_processing_queue]
┌────────────────────────────┐
│  LLM Parser (OpenAI)       │
│  Pydantic v2 validation    │
│  Confidence scoring        │
│  Email notification        │
└────────────────────────────┘
        │
        ▼  property_reports updated:
           llm_parsed_insights JSONB
           confidence_scores JSONB
           status = READY | FAILED
```

---

### What Each Adapter Ingests

#### ① ABS Census Adapter — Demographics (National)

- **Source:** `api.data.abs.gov.au`
- **Mechanism:** REST API (no browser)
- **Cache:** DB-first (checks `abs_census_data` by SA2 code; API only on miss)
- **Geo-resolution step:** lat/lng → SA2 code via ABS Geography API
- **Data extracted:**

| Field | Description |
|---|---|
| `sa2_code` | Statistical Area Level 2 code |
| `median_household_weekly_income_aud` | ABS Census 2021 G17 dataset |
| `owner_occupier_percent` | ABS Census 2021 G46 dataset |

#### ② NBN Co Adapter — Internet Connectivity (National)

- **Source:** `places.nbnco.net.au/places/v2` (unofficial/undocumented API)
- **Mechanism:** HTTP POST/GET with `Referer: https://www.nbnco.com.au/` header
- **Status:** Decommissioned for MVP (fragile `/suggest` endpoint); falls back to legacy flow
- **Data extracted:**

| Field | Description |
|---|---|
| `nbn_tech_type` | `FTTP`, `HFC`, `FTTN`, `FTTB`, `FTTC`, `WIRELESS`, `SATELLITE` |
| `nbn_service_status` | `available`, `in_construction`, etc. |
| `nbn_tech_change_status` | e.g. `Eligible To Order` |
| `nbn_target_eligibility_quarter` | e.g. `Q3 2025` |

#### ③ VicPlan Adapter — State Planning Zones & Overlays (VIC only)

- **Source:** Vicmap Planning ArcGIS FeatureServer (`services-ap1.arcgis.com/...Vicmap_Planning/FeatureServer`)
- **Mechanism:** ArcGIS REST API with spatial point query (lat/lng → polygon intersection)
- **Coverage:** All Victorian LGAs — no council-specific config needed
- **Layers queried:**

| Layer | Data |
|---|---|
| Layer 3 (PLAN_ZONE) | `ZONE_CODE`, `ZONE_STATUS`, `LGA_NAME` |
| Layer 2 (PLAN_OVERLAY) | Overlay codes (`HO`, `FO`, `LSIO`, `BMO`, `BAO`, etc.) |
| Layer 9 (BUSHFIRE_PRONE_AREA) | Bushfire prone area intersection flag |

- **Data extracted:**

| Field | How derived |
|---|---|
| `zoning_code` | e.g. `GRZ1`, `RGZ`, `C1Z` |
| `zoning_label` | e.g. `General Residential Zone` |
| `overlays` | List of overlay objects with code + description |
| `overlay_codes` | Flat list of codes |
| `flood_risk` | `HIGH` (FO/RFO codes), `MEDIUM` (LSIO), `LOW` (SBO), `NONE` |
| `bushfire_risk` | Derived from `BMO`/`BAO` codes + Layer 9 intersection |
| `heritage_overlay` | `true` if any `HO*` code present |
| `constraint_score` | Computed numeric summary of all active overlays |
| `requires_planning_permit` | Boolean derived from zone + overlay combination |

> **For NSW/QLD/SA/WA/TAS/ACT/NT:** `GenericStateAdapter` returns all null fields — state adapters for other states are not yet implemented.

#### ④ Council Adapters — Planning Applications & Meeting Minutes

- **Source:** Individual council planning portals (TechnologyOne, Objective ECM, or generic HTML)
- **Mechanism:** Playwright headless Chromium browser
- **Config-driven:** `data_source_configs` DB table maps each LGA → adapter class + base URL + CSS selectors. **No code change needed to add a new LGA — just insert a row.**
- **Compliance:** Checks `robots.txt` before every scrape; aborts silently if disallowed
- **Proxy:** Rotating residential proxy pool

| Adapter | Used by |
|---|---|
| `TechOneCouncilAdapter` | Many VIC, NSW, QLD councils |
| `ObjectiveCouncilAdapter` | VIC councils using Objective ECM |
| `GenericHtmlCouncilAdapter` | Any council without a dedicated adapter |

- **Data extracted (unstructured text — sent to LLM for parsing):**

| Field | Content |
|---|---|
| `council_planning_applications_text` | Raw text of recent DA/planning applications |
| `council_meeting_minutes_text` | Extracted PDF text from council meeting minutes (up to 3 PDFs) |

---

### What the LLM Extracts (OpenAI Chat Completions)

The LLM receives the merged raw scrape as a structured prompt and returns validated JSON:

```
Input:
  - State Planning API Response     (weight: HIGH)
  - NBN Co API Response             (weight: HIGH)
  - ABS Census Data                 (weight: HIGH)
  - Council Planning Applications   (weight: MEDIUM, scraped HTML)
  - Council Meeting Minutes         (weight: MEDIUM, extracted PDF text)

Output (Pydantic v2 validated):
```

| Section | Key fields |
|---|---|
| `zoning_and_planning` | `zoning_code`, `zoning_label`, `lga_name`, `epi_name`, `overlays`, `heritage_area`, `subdivision_potential`, `conflict_note` |
| `risk_factors.flood` | `risk` (NONE/LOW/MEDIUM/HIGH), `detail`, `confidence_score` |
| `risk_factors.bushfire` | Same shape as flood |
| `risk_factors.crime_density` | `rating` (BELOW_AVERAGE/AVERAGE/ABOVE_AVERAGE), `detail` |
| `connectivity` | `nbn_tech_type`, `nbn_service_status`, `nbn_tech_change_status`, `nbn_target_eligibility_quarter` |
| `infrastructure[]` | `type` (TRANSPORT/HEALTH/EDUCATION/COMMERCIAL/OTHER), `description`, `distance_km`, `expected_completion_year`, `source_url` |
| `roi_scenarios` | 3 scenarios (Conservative/Base/Optimistic), each with interest rate, rent, vacancy, maintenance, rates, insurance → gross/net yield + annual cash flow |


---

## Database Tables — Final State After Ingestion

| Table | Populated by | Purpose |
|---|---|---|
| `spatial_zones` | ABS shapefile import | LGA/suburb/school boundaries for spatial queries |
| `gnaf_addresses` | G-NAF bulk import | ~15M Australian addresses (read-only reference) |
| `properties` | PostGIS spatial join (GNAF × LGA) | Working property index — one row per address |
| `abs_census_data` | ABS Census pre-cache Celery task | SA2-level demographics cache (11× speedup) |
| `data_source_configs` | Admin INSERT | Maps LGA → scraper adapter + config |
| `property_reports` | Scraper workers + LLM worker | One row per scrape cycle per property |
| `property_reports.raw_scraped_data` | Scraper workers | JSONB: merged raw output from all adapters |
| `property_reports.llm_parsed_insights` | LLM worker | JSONB: structured intelligence (LlmOutput schema) |
| `property_reports.confidence_scores` | LLM worker | JSONB: per-field and overall confidence |
| `users` | Clerk webhook → Public API | Investor accounts (Clerk-keyed, no passwords) |
| `user_credit_wallet` | Public API (wallet reconciliation) | Per-user credit balance snapshot |
| `credit_ledger` | Public API (debit on download, Stripe webhook on purchase) | Immutable audit trail of credit movements |
| `credit_purchase_orders` | Public API (Stripe checkout + webhook) | One row per Stripe checkout session |
| `payment_event_receipts` | Public API (Stripe webhook) | Idempotency guard for webhook replay |
| `saved_properties` | Public API | User property bookmarks |
| `admin_activity_log` | Admin Backend API | Audit trail of every admin action |

---

## Data Freshness & Refresh Strategy

| Data | Refresh trigger | Frequency |
|---|---|---|
| G-NAF addresses | Manual admin import | Monthly (Geoscape releases) |
| ABS spatial zones | Manual admin import | Annually (ABS ASGS releases) |
| ABS Census data | Admin-triggered Celery task | On demand / after new Census |
| VIC property reports | On-demand priority queue | When requested |
| NSW property reports | On-demand priority queue | When requested |
| Individual property | User on-demand report generation | Any time |
| Stale detection | `last_scraped_at < NOW() - 30 days` | Checked on every admin scrape trigger |

---

## MinIO Object Storage

Raw scrape results are also stored as JSON objects in MinIO for audit and LLM fallback:

```
Bucket: raw-scrape-cache
Key:    raw-scrapes/{property_id}/{celery_task_id}.json
```

Daily database backups go to:

```
Bucket: ozpr-db-backups
Key:    pg_dump_{date}.sql.gz
```
