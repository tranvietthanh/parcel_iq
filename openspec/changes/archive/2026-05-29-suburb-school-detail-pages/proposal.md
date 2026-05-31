## Why

Suburb and school catchment pages (`/suburb/[state]/[slug]`, `/school/[state]/[slug]`) currently render only a map with a zone boundary overlay. They have zero textual content — Googlebot sees an empty `<canvas>` element. These pages are SEO dead weight despite having high-value URLs (15K+ suburbs, 10K+ school catchments across Australia).

The database already contains rich data that could populate these pages:

- **Suburbs:** The `properties` table has counts, estimated values, and report status per suburb (via `suburb_id` FK). The `spatial_zones.metadata` JSONB stores `SAL_CODE21` (ABS suburb code) from the import script, enabling direct lookup against the free ABS SDMX-REST API. The `abs_census_data` table caches the fetched demographics.

- **Schools:** The `schools` table stores name, address, type (Primary/Secondary/Combined), sector (Government/Catholic/Independent), gender, enrolments, year range, website, and phone. The `property_school_catchments` junction table links properties to school catchments. The `spatial_zones` table holds the catchment boundary polygon.

Enriching these pages with server-rendered textual content would:
1. Create ~25K crawlable, content-rich pages with strong local SEO signals
2. Provide immediate value to users navigating via search engines
3. Position the platform as a property intelligence destination rather than just a map tool

## What Changes

- **New:** Public API endpoints to serve suburb summary data (`GET /api/zones/{zone_id}/summary`) and school detail data (`GET /api/schools/by-catchment/{zone_id}`)
- **Modified:** Suburb slug page — adds a server-rendered detail panel below/beside the map with property counts, median estimated values, demographics, and a list of nearby schools
- **Modified:** School slug page — adds a server-rendered detail panel with school metadata (type, sector, enrolments, year range, website) and catchment property stats
- **New:** `SuburbDetailPanel` server component — renders suburb stats + ABS Census 2021 demographics as crawlable HTML
- **New:** `SchoolDetailPanel` server component — renders school metadata as crawlable HTML
- **New:** JSON-LD structured data for both page types (LocalBusiness schema for suburbs, EducationalOrganization for schools)

## Capabilities

### New Capabilities

- `suburb-detail-content`: Suburb pages display property stats (count, median value), ABS Census 2021 demographics (population, median age, median income, renting %, born overseas %, SEIFA decile), and nearby schools in crawlable HTML
- `school-detail-content`: School catchment pages display school metadata (name, type, sector, enrolments, contact), catchment property count, and median values
- `structured-data-suburbs`: JSON-LD `Place` schema on suburb pages for rich search results
- `structured-data-schools`: JSON-LD `EducationalOrganization` schema on school pages

### Modified Capabilities

- `seo-friendly-suburb-urls`: Suburb pages now render text content alongside the map, not just the map overlay
- `seo-friendly-school-urls`: School catchment pages now render school details alongside the map

## Impact

**Database:** One migration (028) — adds a composite `UNIQUE(region_code, region_type)` constraint to `abs_census_data`, replacing the single `UNIQUE(region_code)` constraint to support both LGA and SAL data in the same table. All other queries are read-only aggregations on existing tables.

**API:** Three new read-only endpoints on the public API. Two standard zone/school endpoints plus ABS Census data fetched on-demand from the free `data.api.abs.gov.au` SDMX-REST API. A new service `services/abs_census.py` handles the fetch-on-demand caching logic. No auth required. Rate-limited to prevent abuse.

**Frontend:** Two new server components for the detail panels. The suburb and school slug pages gain a split layout: map + detail panel. Detail panels are server-rendered for SEO crawlability. Suburb panels include a demographics section sourced from ABS Census 2021 data. JSON-LD `<script>` tags added to page `<head>` via `generateMetadata`.

**Performance:** Suburb summary queries aggregate across potentially thousands of properties. Mitigated by: (a) the `idx_properties_state` and `suburb_id` indexes already exist, (b) results can be cached with ISR/`revalidate` if needed.

## Rollout Strategy

Deploy migration 028 first (adds constraint, non-breaking for existing LGA data). Then deploy API endpoints (zone summary now includes `census_stats` key, initially `null` for all suburbs until first visit). Then deploy frontend changes. On the first visit to any suburb page, the backend fetches ABS data and caches it — subsequent visits serve from DB. No manual data population step required.
