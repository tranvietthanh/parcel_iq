## 0. Data Layer — ABS Census Schema Fix

- [x] 0.1 Create `shared/db-migrations/versions/028_abs_census_sal_unique.py`:
  - Drop the existing `UNIQUE` constraint on `abs_census_data.region_code` (currently `abs_census_data_region_code_key` from migration 012)
  - Add composite `UNIQUE(region_code, region_type)` constraint so the table can hold both `LGA2021` and `SAL2021` rows without collision
  - SQL (use `IF EXISTS` for both possible constraint names — PostgreSQL does not rename constraints when columns are renamed):
    ```sql
    ALTER TABLE abs_census_data DROP CONSTRAINT IF EXISTS abs_census_data_sa2_code_2021_key;
    ALTER TABLE abs_census_data DROP CONSTRAINT IF EXISTS abs_census_data_region_code_key;
    ALTER TABLE abs_census_data ADD CONSTRAINT uq_abs_census_region UNIQUE (region_code, region_type);
    DROP INDEX IF EXISTS idx_abs_census_region_code;
    CREATE INDEX idx_abs_census_region_code_type ON abs_census_data (region_code, region_type);
    ```


## 1. Public API — Zone Summary Endpoint

- [x] 1.1 Create `services/public-api/app/routers/zones.py`:
  - `router = APIRouter(tags=["zones"])` (prefix set in `main.py` via `include_router`, matching existing pattern)
  - `GET /{zone_id}/summary` — accepts zone UUID, returns zone info + property stats + nearby schools + census stats
  - Property stats query: `SELECT COUNT(*), PERCENTILE_CONT(0.5)...` from properties WHERE `suburb_id = $1` (for SUBURB zones) or via `property_school_catchments` / `ST_Contains` (for SCHOOL_CATCHMENT zones)
  - Nearby schools query (SUBURB only): `SELECT s.name, s.school_type, s.sector, s.enrolments, ST_Distance(...)` from schools within 5km of zone centroid, LIMIT 10
  - Census stats (SUBURB only): extract `sal_code = zone["metadata"].get("SAL_CODE21")`, then call `abs_census_service.get_or_fetch_suburb_census_stats(sal_code, db)` — wrap in `try/except` so ABS failures never break the response; include `census_stats: null` if unavailable
  - Rate limit: 200/hour
  - No auth required


- [x] 1.2 Create `services/public-api/app/routers/schools.py`:
  - `router = APIRouter(tags=["schools"])` (prefix set in `main.py`)
  - `GET /by-catchment/{zone_id}` — accepts zone UUID (SCHOOL_CATCHMENT), returns school metadata from `schools` table WHERE `catchment_zone_id = $1`
  - Return 404 if no school linked to this catchment
  - No auth required


- [x] 1.3 Modify `services/public-api/app/main.py`:
  - Import and include the two new routers:
    ```python
    app.include_router(zones.router, prefix="/api/zones")
    app.include_router(schools.router, prefix="/api/schools")
    ```


- [x] 1.4 Create `services/public-api/app/services/abs_census.py`:
  - `get_or_fetch_suburb_census_stats(sal_code: str, db) -> dict | None`:
    1. Query: `SELECT raw_data FROM abs_census_data WHERE region_code=$1 AND region_type='SAL2021'`
    2. Cache HIT: parse `raw_data` via `_extract_display_stats()` and return
    3. Cache MISS: call `_fetch_from_abs(sal_code)` using `httpx.AsyncClient(timeout=10.0)`
    4. Upsert into `abs_census_data` with `ON CONFLICT (region_code, region_type) DO UPDATE`
    5. Return extracted display stats
  - `_fetch_from_abs(sal_code: str) -> dict`: fetch three ABS SDMX-REST dataflows concurrently:
    - `C21_G02_SAL` — medians (age, income, rent, mortgage)
    - `C21_G01_SAL` — population (total, male, female, born overseas, Indigenous)
    - `ABS_SEIFA2021_SAL` — socio-economic index (IRSAD score + decile, optional)
    - URL pattern: `https://data.api.abs.gov.au/rest/data/{DATAFLOW}/..{SAL_CODE}..?format=jsondata`
    - Store all three responses as `{"g02": {...}, "g01": {...}, "seifa": {...}}` in `raw_data`
  - `_parse_sdmx_series(data: dict) -> dict`: parse ABS SDMX-JSON into `{metric_name: value}` dict:
    ```python
    dims   = data["data"]["structure"]["dimensions"]["series"]
    series = data["data"]["dataSets"][0]["series"]
    return {
        dims[0]["values"][int(k.split(":")[0])]["name"]: v["observations"]["0"][0]
        for k, v in series.items()
    }
    ```
    *(Reference implementation in `/data/abs_suburb_explorer_v2.html`)*
  - `_extract_display_stats(raw_data: dict) -> dict`: extract human-readable fields from multi-dataflow response:
    - From G02: `median_age`, `median_weekly_household_income`, `median_weekly_rent`, `median_monthly_mortgage`
    - From G01: `population`, `born_overseas_pct`, `indigenous_pct`
    - From G46 (labour force, if added later): `unemployment_pct`
    - From SEIFA: `seifa_irsad_score`, `seifa_irsad_decile` (null if SEIFA fetch failed)
    - Use fuzzy metric name matching (G02 returns full phrases like "Median age of persons")
  - Handle all exceptions: return `None` on any failure — census unavailability must not raise HTTP 500
  - Note: `httpx>=0.28` is already a dependency in `services/public-api/pyproject.toml`


## 2. Frontend — Suburb Detail Panel

- [x] 2.1 Create `apps/public-web/components/zones/SuburbDetailPanel.tsx` (server component, no `"use client"`):
  - Props: `zoneId: string`, `zoneName: string`, `state: string`
  - Fetch zone summary via `serverApiRequest<ZoneSummary>(`/api/zones/${zoneId}/summary`)`
  - Render:
    - `<h1>` with suburb name + state (e.g., "Werribee, VIC")
    - Property stats section: total count, properties with reports, median estimated value, median land size
    - **Demographics section** (when `census_stats` is non-null): population, median age, median weekly household income, median weekly rent, renting %, born overseas %, SEIFA decile badge
    - Nearby schools list: school name, type, sector, distance (up to 10 schools)
  - Handle API errors gracefully (show "Data unavailable" fallback)
  - If `census_stats` is null, omit the demographics section entirely (not an error state)


- [x] 2.2 Modify `apps/public-web/app/(map)/layout.tsx`:
  - Change `overflow-hidden` to `overflow-auto` (or remove it) so the detail panel can scroll within the full-screen container
  - Current: `<div className="h-[calc(100vh-32px)] w-screen overflow-hidden">`
  - Updated: `<div className="h-[calc(100vh-32px)] w-screen overflow-auto">`


- [x] 2.3 Modify `apps/public-web/app/(map)/suburb/[state]/[slug]/page.tsx`:
  - Import `SuburbDetailPanel`
  - Change layout from full-screen map to split view:
    - Desktop: `flex flex-row` — map (flex-1) + detail panel (w-96 overflow-y-auto)
    - Mobile: `flex flex-col` — map (h-[50vh]) + detail panel (flex-1 overflow-y-auto)
  - Pass `zoneId`, `zoneName`, `state` to `SuburbDetailPanel`
  - Update `generateMetadata`:
    - Enhanced description: "Explore {count} properties in {suburb}, {state}. Median value ${value}."
    - Add JSON-LD `Place` schema with geo coordinates (centroid of zone boundary)


## 3. Frontend — School Detail Panel

- [x] 3.1 Create `apps/public-web/components/zones/SchoolDetailPanel.tsx` (server component):
  - Props: `zoneId: string`, `zoneName: string`, `state: string`
  - Fetch school metadata via `serverApiRequest<SchoolData>(`/api/schools/by-catchment/${zoneId}`)`
  - Fetch zone summary via `serverApiRequest<ZoneSummary>(`/api/zones/${zoneId}/summary`)`
  - Render:
    - `<h1>` with school name + " Catchment"
    - School info card: type (Primary/Secondary/Combined), sector (Government/Catholic/Independent), gender, enrolments, year range
    - Contact: website link, phone
    - Catchment stats: property count, median value
  - Handle missing school data gracefully (not all catchments have linked school records)


- [x] 3.2 Modify `apps/public-web/app/(map)/school/[state]/[slug]/page.tsx`:
  - Import `SchoolDetailPanel`
  - Change layout to split view (same pattern as suburb page)
  - Pass `zoneId`, `zoneName`, `state` to `SchoolDetailPanel`
  - Update `generateMetadata`:
    - Enhanced description: "{schoolName} — {type} school ({sector}). {enrolments} students. View catchment area."
    - Add JSON-LD `EducationalOrganization` schema


## 4. Frontend — Types

- [x] 4.1 Add types to `apps/public-web/types/index.ts` or create `types/zones.ts`:
  - `ZoneSummary` type: zone info, property_stats (total_count, with_reports, median_estimated_value, median_land_size_sqm), nearby_schools array, **census_stats: CensusStats | null**
  - `CensusStats` type:
    ```typescript
    type CensusStats = {
      population: number | null
      median_age: number | null
      median_weekly_household_income: number | null
      median_weekly_rent: number | null
      renting_pct: number | null
      born_overseas_pct: number | null
      indigenous_pct: number | null
      seifa_irsad_score: number | null
      seifa_irsad_decile: number | null  // 1 (most disadvantaged) to 10 (least)
    }
    ```
  - `SchoolData` type: name, address, school_type, sector, gender, enrolments, year_range, website, phone


## 5. Frontend — Shared Layout Component

- [x] 5.1 Create `apps/public-web/components/zones/ZonePageLayout.tsx`:
  - Shared responsive layout wrapper for zone detail pages
  - Props: `mapSlot: React.ReactNode`, `detailSlot: React.ReactNode`
  - Desktop: side-by-side (map + panel)
  - Mobile: stacked (map on top + panel below)
  - Eliminates layout duplication between suburb and school pages


## 6. Verification

- [x] 6.1 `GET /api/zones/{suburb_zone_id}/summary` — returns 200 with property count, median values, nearby schools list
- [x] 6.2 `GET /api/zones/{school_catchment_id}/summary` — returns 200 with property count in catchment
- [x] 6.3 `GET /api/schools/by-catchment/{catchment_zone_id}` — returns 200 with school metadata (name, type, sector, enrolments)
- [x] 6.4 `GET /api/schools/by-catchment/{non_existent_id}` — returns 404
- [x] 6.5 Browse `/suburb/vic/{valid-slug}` — page shows map + detail panel with property stats and nearby schools; view page source confirms stats are in HTML (not client-rendered)
- [x] 6.6 Browse `/school/vic/{valid-slug}` — page shows map + detail panel with school info; view page source confirms school data is in HTML
- [x] 6.7 Right-click → View Page Source on suburb page — confirm JSON-LD `Place` script tag is present
- [x] 6.8 Right-click → View Page Source on school page — confirm JSON-LD `EducationalOrganization` script tag is present
- [x] 6.9 Test mobile viewport (< 1024px) — map and detail panel stack vertically
- [x] 6.10 Test suburb with no properties (edge case) — panel shows "No property data available" instead of NaN/errors
- [x] 6.11 Test school catchment with no linked school record — panel shows "School details not available" gracefully
- [x] 6.12 Call `GET /api/zones/{suburb_zone_id}/summary` for a suburb with no prior ABS data — verify `census_stats` is populated in response and a new row exists in `abs_census_data` with `region_type='SAL2021'`
- [x] 6.13 Call same endpoint again — verify response is immediate (DB cache hit, no ABS API call)
- [x] 6.14 Test a suburb where `SAL_CODE21` is absent from `spatial_zones.metadata` — verify `census_stats: null` in response, no error
- [x] 6.15 Run `alembic upgrade head` in `shared/db-migrations` — migration 028 applies cleanly, `UNIQUE(region_code, region_type)` constraint exists, old `region_code` unique index is gone
- [x] 6.16 View Page Source on suburb page with census data — confirm demographics (population, median income, renting %) appear in HTML body (SSR, not client-rendered)
