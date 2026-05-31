## Context

OZ Property Report is a Next.js 15 (App Router) + FastAPI monorepo. Suburb and school catchment pages live at `apps/public-web/app/(map)/suburb/[state]/[slug]/page.tsx` and `apps/public-web/app/(map)/school/[state]/[slug]/page.tsx`. Both currently render only a `SharedMapView` client component — a Mapbox canvas with a zone overlay polygon. The `(map)` route group has a full-screen layout (`h-screen w-screen overflow-hidden`).

The database has the following relevant tables:
- `spatial_zones` — zone boundaries (LGA/SUBURB/SCHOOL_CATCHMENT) with slug, name, state, geom, metadata JSONB
- `properties` — 15M property rows with `suburb_id` FK to `spatial_zones`, estimated_value, beds, baths, land_size_sqm
- `property_reports` — per-property scrape results, `status` can be PENDING/SCRAPING/PENDING_LLM/PROCESSING_LLM/READY/FAILED_SCRAPE/FAILED_LLM/REVIEW_REQUIRED
- `schools` — school locations with name, type, sector, gender, enrolments, year_range, website, phone, `catchment_zone_id` FK
- `property_school_catchments` — junction table linking property_id to zone_id (school catchments)
- `abs_census_data` — region-based demographics cache (region_code + region_type), raw_data JSONB

The public API (`services/public-api`) uses asyncpg with parameterised `$1, $2` queries. All routes are in `app/routers/`.

## Goals / Non-Goals

**Goals**
- Suburb pages render server-side textual content: property count, median estimated value, and nearby schools
- School pages render server-side textual content: school metadata (name, type, sector, enrolments, website) and catchment property stats
- Content is rendered as HTML in the initial server response — crawlable by Googlebot without JavaScript
- JSON-LD structured data in `<head>` for rich search results
- Layout splits between map and detail panel (responsive)

**Non-Goals**
- Demographics on suburb pages at SA2 level (SAL-level via ABS API is now the approach — see Decision 7)
- Property listings on suburb/school pages (search-to-select flow handles this)
- Caching/ISR for summary queries (can be added later if performance is an issue)
- LGA detail pages (not prioritized)
- Populating census data in bulk upfront (fetch-on-demand per suburb is the strategy)

## Decisions

### Decision 1: Split layout — map + detail panel side-by-side

The current full-screen map layout works for the map-only experience. For detail pages, add a scrollable detail panel alongside the map:

```
Desktop (≥1024px):
┌──────────────────────────┬────────────────────┐
│                          │                    │
│        Map Canvas        │   Detail Panel     │
│      (flex: 1)           │   (w-96, scroll)   │
│                          │                    │
│                          │  - Property Count  │
│                          │  - Median Value    │
│                          │  - Nearby Schools  │
│                          │                    │
└──────────────────────────┴────────────────────┘

Mobile (<1024px):
┌──────────────────────────┐
│       Map Canvas         │
│       (h-[50vh])         │
├──────────────────────────┤
│     Detail Panel         │
│     (scrollable)         │
└──────────────────────────┘
```

The slug pages will import `SharedMapView` for the map portion and render the detail panel as a **sibling server component**. This keeps the map fully client-side while the detail panel is SSR.

### Decision 2: API endpoints for aggregated data

Two new endpoints on the public API, both public (no auth):

**`GET /api/zones/{zone_id}/summary`** — Returns aggregated stats for any zone (suburb or school catchment):

```python
@router.get("/{zone_id}/summary")
async def zone_summary(zone_id: UUID, db = Depends(get_db)):
    return {
        "zone": { "name": ..., "state": ..., "zone_type": ... },
        "property_stats": {
            "total_count": int,
            "with_reports": int,
            "median_estimated_value": float | None,
            "median_land_size_sqm": int | None,
        },
        "nearby_schools": [  # Only for SUBURB zones
            { "name": ..., "type": ..., "sector": ..., "distance_km": ... }
        ]
    }
```

SQL for property stats:
```sql
SELECT COUNT(*) AS total_count,
       COUNT(*) FILTER (WHERE pr.status = 'READY') AS with_reports,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.estimated_value)
           FILTER (WHERE p.estimated_value IS NOT NULL) AS median_estimated_value,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.land_size_sqm)
           FILTER (WHERE p.land_size_sqm IS NOT NULL) AS median_land_size_sqm
FROM properties p
LEFT JOIN property_reports pr ON pr.property_id = p.id
WHERE p.suburb_id = $1
```

For school catchments, use `ST_Contains(zone.geom, p.geom)` or the `property_school_catchments` junction table.

**`GET /api/schools/by-catchment/{zone_id}`** — Returns school metadata for a catchment zone:

```python
@router.get("/by-catchment/{zone_id}")
async def school_by_catchment(zone_id: UUID, db = Depends(get_db)):
    return {
        "school": {
            "name": ..., "address": ..., "school_type": ...,
            "sector": ..., "gender": ..., "enrolments": ...,
            "year_range": ..., "website": ..., "phone": ...
        }
    }
```

### Decision 3: Server components for detail panels

`SuburbDetailPanel` and `SchoolDetailPanel` are **React Server Components** — they fetch data directly via `serverApiRequest` and render HTML. No `"use client"` directive.

This ensures:
- Content is in the initial HTML response
- Googlebot sees text without executing JavaScript
- No client-side data fetching for the detail content

### Decision 4: JSON-LD structured data

Suburb pages use `Place` schema:
```json
{
  "@context": "https://schema.org",
  "@type": "Place",
  "name": "Werribee, VIC",
  "address": { "@type": "PostalAddress", "addressRegion": "VIC", "addressCountry": "AU" },
  "geo": { "@type": "GeoCoordinates", "latitude": -37.9, "longitude": 144.66 }
}
```

School pages use `EducationalOrganization` schema:
```json
{
  "@context": "https://schema.org",
  "@type": "EducationalOrganization",
  "name": "Suzanne Cory High School",
  "address": "...",
  "url": "https://...",
  "numberOfStudents": 1200
}
```

Both are injected via `generateMetadata` → `other: { "script:ld+json": ... }` or a `<script type="application/ld+json">` in the page body.

### Decision 5: Nearby schools for suburb pages

For suburb pages, query schools within or near the suburb boundary:

```sql
SELECT s.name, s.school_type, s.sector, s.enrolments,
       ST_Distance(s.geom::geography, ST_Centroid(sz.geom)::geography) / 1000 AS distance_km
FROM schools s, spatial_zones sz
WHERE sz.id = $1
  AND ST_DWithin(s.geom::geography, sz.geom::geography, 5000)  -- 5km radius
ORDER BY distance_km
LIMIT 10
```

### Decision 6: Suburb property stats use `suburb_id` FK (not spatial query)

Properties already have `suburb_id` populated (via import scripts or lazy resolution). Using `WHERE p.suburb_id = $1` is a simple index lookup — no spatial query needed. This is fast even for suburbs with thousands of properties.

For school catchments, use `property_school_catchments` junction table if populated, otherwise fall back to `ST_Contains`.

### Decision 7: ABS Census Data — Fetch-on-Demand at SAL Level

**Why not pre-populate?** There are ~15,000 SAL zones across Australia. Bulk-fetching all of them at import time is expensive and unnecessary. Most suburb pages get zero traffic initially. Fetch-on-demand means we only pay the API cost for suburbs users actually visit.

**Why SAL, not SA2?** The `SAL_2021_AUST_GDA2020.shp` shapefile is already imported into `spatial_zones` as SUBURB zones. The `SAL_CODE21` field (e.g. `"21267"` for Fitzroy VIC) is stored in `spatial_zones.metadata` by the import script. ABS provides the free, unauthenticated SDMX-REST API at SAL level — same geography, direct lookup.

**ABS API (free, no auth since Nov 2024):**
```
Base: https://data.api.abs.gov.au/rest/data/{DATAFLOW}/..{SAL_CODE}..?format=jsondata

Dataflows used:
  C21_G02_SAL  → Medians (age, household income, rent, mortgage)
  C21_G01_SAL  → Population (total, male, female, born overseas, Indigenous)
  ABS_SEIFA2021_SAL → Socio-economic index (IRSAD score + decile)
```

**Cache layer — extend `abs_census_data`:**
The existing table supports generic `region_code` + `region_type`. SAL data uses `region_type = 'SAL2021'`. The `raw_data` JSONB column stores the full multi-dataflow response. A composite unique constraint `UNIQUE(region_code, region_type)` (migration 028) replaces the old `UNIQUE(region_code)` to allow both LGA and SAL codes in the same table without collision.

**Fetch-on-demand flow:**
```
Request: GET /api/zones/{zone_id}/summary  (zone_type = SUBURB)
  1. Read sal_code = zone.metadata["SAL_CODE21"]
  2. SELECT * FROM abs_census_data WHERE region_code=$1 AND region_type='SAL2021'
  3a. Cache HIT  → parse raw_data → include census_stats in response (≤50ms overhead)
  3b. Cache MISS → fetch G02 + G01 + SEIFA from ABS API (async, ≤2s)
                 → upsert into abs_census_data
                 → include census_stats in response
  4. If ABS fetch fails → census_stats: null (page still renders with property stats)
```

**SDMX-JSON parsing (reference: abs_suburb_explorer_v2.html in /data):**
```python
def _parse_sdmx_series(data: dict) -> dict:
    dims   = data["data"]["structure"]["dimensions"]["series"]
    series = data["data"]["dataSets"][0]["series"]
    return {
        dims[0]["values"][int(k.split(":")[0])]["name"]: v["observations"]["0"][0]
        for k, v in series.items()
    }
```

**Display stats extracted:**
- Population, median age
- Median weekly household income
- Median weekly rent
- Renting %, owned outright %
- Born overseas %
- SEIFA IRSAD decile (1=most disadvantaged, 10=least)

**Where census stats appear:**
- `GET /api/zones/{zone_id}/summary` response → `census_stats` key (SUBURB zones only)
- `SuburbDetailPanel` → Demographics section below property stats

## File Layout

```
shared/db-migrations/versions/
└── 028_abs_census_sal_unique.py                # NEW: composite unique constraint on abs_census_data

services/public-api/app/
├── services/abs_census.py                      # NEW: fetch-on-demand ABS census service
├── routers/zones.py                            # NEW: zone summary endpoint (includes census_stats)
├── routers/schools.py                          # NEW: school-by-catchment endpoint
└── main.py                                     # MODIFIED: register new routers

apps/public-web/
├── app/(map)/suburb/[state]/[slug]/page.tsx    # MODIFIED: add detail panel + JSON-LD
├── app/(map)/school/[state]/[slug]/page.tsx    # MODIFIED: add detail panel + JSON-LD
├── components/zones/SuburbDetailPanel.tsx       # NEW: server component for suburb stats + census
└── components/zones/SchoolDetailPanel.tsx       # NEW: server component for school details
```

## Data Flow

### Suburb page load
```
Browser → /suburb/vic/werribee-vic
  → Next.js SSR:
    1. generateMetadata: fetch /api/search/zones/slug/werribee-vic → zone name/state for <title>
    2. SuburbDetailPanel (server component):
       fetch /api/zones/{zone_id}/summary → {
         property_stats: { total_count, median_estimated_value, ... },
         nearby_schools: [...],
         census_stats: {                     ← NEW (fetch-on-demand from ABS)
           population: 12450,
           median_age: 34,
           median_weekly_household_income: 1850,
           median_weekly_rent: 380,
           renting_pct: 58.2,
           born_overseas_pct: 36.4,
           seifa_irsad_decile: 7
         }
       }
       render HTML: "1,234 properties • Median $650,000 • Population 12,450"
    3. SharedMapView (client component): map + zone overlay
  → Googlebot sees: <title>, <meta>, <h1>, stats text, demographics, school list, JSON-LD
  → User sees: map with zone boundary + detail panel with property stats + demographics
```

### School page load
```
Browser → /school/vic/suzanne-cory-high-school-vic
  → Next.js SSR:
    1. generateMetadata: fetch zone data → school name for <title> + JSON-LD
    2. SchoolDetailPanel (server component):
       fetch /api/schools/by-catchment/{zone_id} → school metadata
       fetch /api/zones/{zone_id}/summary → catchment property stats
       render HTML: school info card + "423 properties in catchment"
    3. SharedMapView (client component): map + catchment overlay
  → Googlebot sees: school name, type, sector, enrolments, property count
```

## API Changes

### New service: `abs_census.py`

```python
# services/public-api/app/services/abs_census.py

import httpx

ABS_BASE = "https://data.api.abs.gov.au/rest/data"
DATAFLOWS = {"medians": "C21_G02_SAL", "population": "C21_G01_SAL", "seifa": "ABS_SEIFA2021_SAL"}

async def get_or_fetch_suburb_census_stats(sal_code: str, db) -> dict | None:
    """Return cached or freshly-fetched ABS Census 2021 stats for a suburb."""
    row = await db.fetchrow(
        "SELECT raw_data FROM abs_census_data WHERE region_code=$1 AND region_type='SAL2021'",
        sal_code,
    )
    if row and row["raw_data"]:
        return _extract_display_stats(row["raw_data"])
    # Cache miss — fetch from ABS API
    raw = await _fetch_from_abs(sal_code)   # raises on error
    await db.execute(
        """
        INSERT INTO abs_census_data (region_code, region_type, census_year, raw_data, fetched_at)
        VALUES ($1, 'SAL2021', 2021, $2::jsonb, now())
        ON CONFLICT (region_code, region_type)
        DO UPDATE SET raw_data=EXCLUDED.raw_data, fetched_at=now(), updated_at=now()
        """,
        sal_code, json.dumps(raw),
    )
    return _extract_display_stats(raw)
```

### New router: `zones.py`

```python
router = APIRouter(tags=["zones"])  # prefix set in main.py via include_router

@router.get("/{zone_id}/summary")
async def zone_summary(zone_id: UUID, db = Depends(get_db)) -> dict:
    """Aggregated property stats, nearby schools, and ABS census data for a zone."""
    # ... property stats query ...
    census_stats = None
    if zone["zone_type"] == "SUBURB":
        sal_code = (zone["metadata"] or {}).get("SAL_CODE21")
        if sal_code:
            try:
                census_stats = await abs_census.get_or_fetch_suburb_census_stats(sal_code, db)
            except Exception:
                pass  # census failure must not break the page
    return {
        "zone": {...},
        "property_stats": {...},
        "nearby_schools": [...],
        "census_stats": census_stats,   # None for school catchments / LGA zones
    }
```

### New router: `schools.py`

```python
router = APIRouter(tags=["schools"])  # prefix set in main.py via include_router

@router.get("/by-catchment/{zone_id}")
async def school_by_catchment(zone_id: UUID, db = Depends(get_db)) -> dict:
    """School metadata for a catchment zone."""
```

## Risks / Mitigations

| Risk | Mitigation |
|---|---|
| Suburb property count query slow for large suburbs (e.g., Melbourne CBD with 10K+ properties) | `suburb_id` index exists; PERCENTILE_CONT is single-pass; add `revalidate` ISR if needed |
| `suburb_id` is NULL for some properties (lazy resolution) | Query uses `WHERE p.suburb_id = $1` which naturally excludes NULL; stats represent resolved properties only |
| `property_school_catchments` junction table may not be populated | Fall back to `ST_Contains(zone.geom, p.geom)` spatial query; document this in the endpoint |
| School metadata missing for some zones (private schools don't have catchments) | Return `school: null` gracefully; detail panel shows "No school data available" |
| JSON-LD schema errors causing Google Search Console warnings | Validate with Google's Rich Results Test before deployment |
| ABS API unavailable or slow (first suburb page visit) | 10s timeout on `httpx.AsyncClient`; census failure returns `null`, not an error; property stats still render |
| `SAL_CODE21` missing from `spatial_zones.metadata` (suburb imported without shapefile) | `sal_code` check gates the fetch — `census_stats: null` gracefully if missing |
| ABS API rate limits (undocumented but fair-use applies) | Fetch-on-demand means only visited suburbs are fetched; DB cache means each suburb is fetched once |
| `region_code` collision between LGA and SAL codes (both are numeric strings) | Migration 028 replaces `UNIQUE(region_code)` with `UNIQUE(region_code, region_type)` |
