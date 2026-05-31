## Context

OZ Property Report is a Next.js 15 (App Router) + FastAPI monorepo. The public frontend (`apps/public-web`) uses Clerk for auth, Mapbox GL for the map, and SWR hooks for data fetching. The public API (`services/public-api`) uses asyncpg with parameterised queries. The database is PostgreSQL 16 + PostGIS. Import scripts live in `infra/scripts/` and run outside the app.

The current property URL is `/property/{uuid}` and no URL exists for suburb or school catchment views. The map page is a full client component at `/` — selecting a search result updates local state only, with no URL change.

The `(map)` route group uses a full-screen layout (`h-screen w-screen overflow-hidden`). The map page renders `MapContainer` + `SearchOmnibox` + `PropertyDetail` (panel mode) + `UserAvatar`. When a user selects a search result, the map pans/zooms and the PropertyDetail panel slides in from the right.

## Goals / Non-Goals

**Goals**
- Slug-based URLs for all three entity types: property, suburb, school catchment
- Slugs generated at import time, stored in DB, unique by constraint
- Search API returns slugs in suggestion payloads
- Map page updates browser URL to slug on search result selection
- Navigating directly to a slug URL shows the **same map + panel view** as searching + selecting (not a standalone detail page)
- All slug pages are SSR with entity-specific `<title>` / `<meta name="description">`
- Property slug pages are publicly accessible (not Clerk-protected) for SEO crawlability

**Non-Goals**
- LGA slug pages (LGA map pan still works, no URL change for LGA)
- Redirects from old UUID URLs (route is decommissioned, DB is being wiped)
- Slug regeneration on address updates (slugs are set at import time, immutable)
- Suburb/school page content beyond zone metadata and map (no property listings on these pages yet)

## Decisions

### Decision 1: Slug algorithm

```python
import re, random, string

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)   # strip all special chars
    text = re.sub(r"[\s-]+", "-", text)          # collapse spaces/hyphens
    return text.strip("-")

def ensure_unique_slug(base: str, seen: set[str]) -> str:
    if base not in seen:
        seen.add(base)
        return base
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    candidate = f"{base}-{suffix}"
    seen.add(candidate)
    return candidate
```

**Property slug:** `slugify(address_string)` — the address already contains suburb, state, and postcode, so slugs are naturally unique in the vast majority of cases. E.g.:
```
"8 St Lawrence Close, Werribee VIC 3030" → "8-st-lawrence-close-werribee-vic-3030"
```

**Zone slugs:**
- SUBURB: `slugify(name) + "-" + state.lower()` → `"werribee-vic"`
- LGA: `slugify(name) + "-" + state.lower()` → `"wyndham-city-council-vic"`
- SCHOOL_CATCHMENT: strip trailing catch-all suffixes first (`" catchment area"`, `" catchment"`, `" zone"`, `" zones"`) then `slugify(name) + "-" + state.lower()`:
  ```
  "Suzanne Cory High School Catchment Area" → "suzanne-cory-high-school-vic"
  ```

### Decision 2: Collision resolution is Python-side

Import scripts maintain a `seen_slugs: set[str]` in memory across the run. On collision, `ensure_unique_slug()` appends a random 4-char alphanumeric suffix. The DB `UNIQUE` constraint is a final integrity guard only.

This approach avoids extra DB round-trips (no `SELECT slug FROM ... WHERE slug = ?` per row) and is fast enough for the import volume.

### Decision 3: New Alembic migration 027 (not modifying 002/003)

There are 26+ existing migrations in the chain (002 through 026a). Editing old migrations breaks Alembic's revision tracking — even on a fresh DB, the revision hash won't match. A new `027_add_slugs.py` adds the columns:

```python
op.execute("ALTER TABLE spatial_zones ADD COLUMN slug VARCHAR(300) NOT NULL DEFAULT ''")
op.execute("CREATE UNIQUE INDEX idx_spatial_zones_slug ON spatial_zones (slug)")

op.execute("ALTER TABLE properties ADD COLUMN slug VARCHAR(400) NOT NULL DEFAULT ''")
op.execute("CREATE UNIQUE INDEX idx_properties_slug ON properties (slug)")
```

The `DEFAULT ''` is temporary — the import scripts populate real slugs. After import, the UNIQUE constraint holds.

### Decision 4: `create_properties_from_gnaf.py` — slug generation within existing batch loop

The current script already uses a batched `INSERT ... SELECT FROM gnaf_addresses` loop (1000 rows per batch). The slug is added as a SQL expression inline in the INSERT:

```sql
INSERT INTO properties (gnaf_pid, address_string, slug, geom, state, ...)
SELECT
    gnaf_pid,
    address_string,
    -- Generate slug in SQL
    trim(both '-' from regexp_replace(
        regexp_replace(lower(address_string), '[^a-z0-9\s-]', '', 'g'),
        '[\s-]+', '-', 'g'
    )),
    geom, state, ...
FROM gnaf_addresses
```

If SQL-based slug generation is too slow or causes conflicts, fallback to Python-side generation (fetch batch into Python, generate slugs with `ensure_unique_slug()`, insert with `executemany`). Use whichever approach is faster.

### Decision 5: API slug resolver — dedicated route, not a redirect

The slug resolver is a new route that resolves slug → UUID internally and returns the same response shape:

```python
# New
GET /api/properties/slug/{slug}/detail
GET /api/search/zones/slug/{slug}

# Unchanged
GET /api/properties/{uuid}/detail
GET /api/search/zones?zone_id={uuid}
```

The UUID-based routes remain for internal use (e.g., `PropertyDetail` component still calls `/{uuid}/detail` after the map page resolves slug → data). The slug routes are used by the Next.js SSR pages.

**Route ordering concern:** FastAPI matches routes top-to-bottom. `GET /api/properties/slug/{slug}/detail` must be registered **before** `GET /api/properties/{property_id}/detail` to avoid `slug` being matched as a UUID path param. This is handled by registering slug routes first in the router.

### Decision 6: `zone_state` added to SearchSuggestion

The map page needs the state to construct `/suburb/{state}/{slug}` and `/school/{state}/{slug}` URLs. The `spatial_zones.state` column already exists — it's just not currently included in the search response. Adding `zone_state: str | None` to `SearchSuggestion` is a non-breaking addition.

### Decision 7: Slug pages render the full map + panel view (not standalone pages)

This is the key architectural decision. When a user navigates to `/property/8-st-lawrence-close-werribee-vic-3030`, they should see **the exact same display** as when they search for that address and select it from the omnibox — i.e., the map centered on the property with the PropertyDetail panel open on the right.

**Implementation approach: slug routes inside the `(map)` route group.**

The `(map)` route group already has a full-screen layout (`h-screen w-screen overflow-hidden`). The slug pages are added as nested routes within this group:

```
app/(map)/
├── layout.tsx                              # Full-screen map layout (existing)
├── page.tsx                                # / — map page (existing)
├── property/[slug]/page.tsx                # /property/[slug] — NEW
├── suburb/[state]/[slug]/page.tsx          # /suburb/[state]/[slug] — NEW
└── school/[state]/[slug]/page.tsx          # /school/[state]/[slug] — NEW
```

Each slug page:
1. Is a `"use client"` page that renders the same components as the map page: `MapContainer` + `SearchOmnibox` + `PropertyDetail` + `UserAvatar`
2. Resolves the slug to entity data on mount (client-side fetch)
3. Pre-selects the entity (sets `selectedId` for properties, or fits bounds + shows zone overlay for suburbs/schools)
4. Centers/zooms the map to the entity's location or bounding box

For SEO, each slug page also has a **server-side `generateMetadata`** function that fetches entity data from the API to populate `<title>` and `<meta name="description">`. The page body is client-rendered (map requires client-side JS), but the `<head>` is SSR with meaningful metadata.

**Shared logic:** Extract the map + panel + search + avatar composition into a shared `MapView` component (or simply share via the route group layout). Each slug page passes initial state (slug, entity type) to configure the pre-selection.

**Note on double-fetch:** The SSR `generateMetadata` call and the client-side `useProperty` call both hit the API. This is consistent with the existing `property/[id]/page.tsx` pattern and is acceptable — the SSR fetch populates metadata, the client fetch hydrates the interactive component.

### Decision 8: URL update on search select — `router.push` (replaceState)

When a user selects a result from the search omnibox on the map page:
1. Map pans/zooms to the entity
2. Panel opens (for properties) or zone overlay appears (for suburbs/schools)
3. `window.history.replaceState` or `router.replace` updates the URL to the friendly slug

Using `replace` instead of `push` avoids polluting the history stack — the user can press Back to return to wherever they came from, not step through every search selection.

For suburb/school selections, the URL updates but the user stays on the map with the zone boundary visible. No full navigation occurs.

### Decision 9: Remove `/property/(.*)` from Clerk protected routes

The `proxy.ts` middleware currently protects `/property/(.*)` via Clerk. This blocks SEO crawlers from accessing property slug pages. Since the `PropertyDetail` component already handles anonymous users gracefully (shows disclaimer, limited data, sign-in CTA for full reports), removing this protection is safe. All existing anonymous handling continues to apply.

New `/suburb/` and `/school/` routes are also public — no Clerk protection needed.

### Decision 10: `my-properties` page — link to slug URLs

The `my-properties` page currently links to `/property/${item.property_id}` (UUID). After the change, this route won't exist. The fix:
1. API: Include `p.slug` in the `my/requested` and `list_saved` query SELECTs
2. Frontend: Link to `/property/${item.slug}` instead of `/property/${item.property_id}`

### Decision 11: School slug pages — future enrichment with school metadata

The URL `/school/vic/suzanne-cory-high-school-vic` resolves via `spatial_zones` (zone_type=`SCHOOL_CATCHMENT`). The `schools` table stores separate point-level metadata (enrolments, sector, gender) linked via `schools.catchment_zone_id`. For this change, the school slug page shows the catchment boundary on the map. Future enhancement: join school metadata from the `schools` table for richer content.

## File Layout

```
infra/scripts/
└── slug_utils.py                                # NEW: shared slugify + ensure_unique_slug

shared/db-migrations/versions/
└── 027_add_slugs.py                             # NEW: slug columns on spatial_zones + properties

infra/scripts/
├── import_spatial_zones.py                      # MODIFIED: generates + persists zone slugs
└── create_properties_from_gnaf.py               # MODIFIED: generates + persists property slugs

services/public-api/app/
├── schemas/search.py                            # MODIFIED: SearchSuggestion + slug + zone_state
├── schemas/property.py                          # MODIFIED: PropertyDetail + slug
├── routers/search.py                            # MODIFIED: TEXT_SEARCH_QUERY includes slug/zone_state; NEW /zones/slug/{slug} route
├── routers/properties.py                        # MODIFIED: DETAIL_QUERY + slug; NEW /slug/{slug}/detail route
├── routers/my_properties.py                     # MODIFIED: my/requested includes slug
└── routers/saved.py                             # MODIFIED: list_saved includes slug

apps/public-web/
├── proxy.ts                                     # MODIFIED: remove /property/(.*) from protected routes
├── app/property/[id]/page.tsx                   # DELETED
├── app/(map)/property/[slug]/page.tsx           # NEW: map + property panel
├── app/(map)/suburb/[state]/[slug]/page.tsx     # NEW: map + suburb zone overlay
├── app/(map)/school/[state]/[slug]/page.tsx     # NEW: map + school catchment overlay
├── app/(map)/page.tsx                           # MODIFIED: URL update on search select
├── app/my-properties/page.tsx                   # MODIFIED: links use slug instead of UUID
└── types/index.ts                               # MODIFIED: SearchSuggestion + slug + zone_state
```

## Data Flow

### Import time
```
GeoJSON/Shapefile feature
  → resolve name + state
  → make_zone_slug(name, state, zone_type)
  → ensure_unique_slug(base, seen_slugs)
  → INSERT INTO spatial_zones (..., slug) VALUES (..., $slug)

gnaf_addresses row (per batch)
  → build slug in SQL or Python
  → INSERT INTO properties (..., slug) VALUES (..., $slug)
```

### Search select flow (on map page)
```
User types "Werribee" → selects "Suzanne Cory High School (SCHOOL_CATCHMENT)"
  → SearchSuggestion { type: "SCHOOL_CATCHMENT", slug: "suzanne-cory-high-school-vic", zone_state: "VIC", ... }
  → map fits bounds to catchment bbox
  → router.replace("/school/vic/suzanne-cory-high-school-vic")
  → URL updates, no full navigation — user stays on map
```

### Direct navigation flow (slug URL)
```
Browser opens /property/8-st-lawrence-close-werribee-vic-3030
  → Next.js SSR: generateMetadata fetches /api/properties/slug/8-st-lawrence.../detail
  → <head> populated with title + description (SEO)
  → Client renders: MapContainer + SearchOmnibox + PropertyDetail panel
  → useEffect: fetch property by slug → get coordinates + UUID
  → map.flyTo(property.coordinates, zoom: 16)
  → setSelectedId(property.id) → PropertyDetail panel opens
```

## API Changes

### `SearchSuggestion` schema (search.py)

```python
class SearchSuggestion(BaseModel):
    type: str
    label: str
    property_id: UUID | None = None
    zone_id: UUID | None = None
    coordinates: list[float] | None = None
    bbox: list[float] | None = None
    slug: str | None = None          # NEW
    zone_state: str | None = None    # NEW — populated for zone results only
```

### `PropertyDetail` schema (property.py)

```python
class PropertyDetail(BaseModel):
    id: UUID
    address: str
    state: str
    slug: str | None = None          # NEW
    report_status: str | None = None
    education: dict | None = None
    connectivity: dict | None = None
    risk_factors: dict | None = None
    zoning_and_planning: dict | None = None
    demographic_snapshot: dict | None = None
```

### TEXT_SEARCH_QUERY (search.py)

```sql
(
    SELECT 'ADDRESS' AS type, p.address_string AS label,
           p.id::text AS property_id, NULL::text AS zone_id,
           ST_X(p.geom) AS lng, ST_Y(p.geom) AS lat,
           NULL::json AS bbox,
           p.slug AS slug,           -- NEW
           NULL::text AS zone_state  -- NEW
    FROM properties p
    WHERE ...
    LIMIT $2
)
UNION ALL
(
    SELECT sz.zone_type AS type, sz.name || ' — ' || sz.state AS label,
           NULL::text AS property_id, sz.id::text AS zone_id,
           NULL::numeric AS lng, NULL::numeric AS lat,
           ST_AsGeoJSON(ST_Envelope(sz.geom))::json AS bbox,
           sz.slug AS slug,          -- NEW
           sz.state AS zone_state    -- NEW
    FROM spatial_zones sz
    WHERE sz.name ILIKE '%' || $1 || '%'
    LIMIT $2
)
```

### New route: `GET /api/properties/slug/{slug}/detail`

```python
@router.get("/slug/{slug}/detail")  # Must be registered BEFORE /{property_id}/detail
@limiter.limit("200/hour")
async def property_detail_by_slug(
    request: Request,
    slug: str,
    db: asyncpg.Connection = Depends(get_db),
) -> PropertyDetail:
    row = await db.fetchrow("SELECT id FROM properties WHERE slug = $1", slug)
    if not row:
        raise HTTPException(status_code=404, detail="Property not found.")
    return await _get_property_detail(row["id"], db)  # reuse existing logic
```

### New route: `GET /api/search/zones/slug/{slug}`

```python
@router.get("/zones/slug/{slug}")
async def search_zones_by_slug(
    slug: str,
    db: asyncpg.Connection = Depends(get_db),
) -> ZoneFeature:
    row = await db.fetchrow(
        "SELECT id, zone_type, name, state, ST_AsGeoJSON(geom)::json AS geometry, metadata "
        "FROM spatial_zones WHERE slug = $1",
        slug
    )
    if not row:
        raise HTTPException(status_code=404, detail="Zone not found.")
    return ZoneFeature(geometry=row["geometry"], properties={...})
```

## Risks / Mitigations

| Risk | Mitigation |
|---|---|
| FastAPI route ordering — `slug` matched as UUID | Register `/slug/{slug}/detail` before `/{property_id}/detail` in router |
| Property slug collision (15M rows, rare but possible) | `ensure_unique_slug` with 4-char suffix; DB UNIQUE is final guard |
| `my-properties` links break after decommissioning UUID route | Include `slug` in API responses; update links before deleting old route |
| Clerk middleware blocks SEO crawling | Remove `/property/(.*)` from protected routes |
| Map doesn't center correctly on direct slug URL navigation | Slug resolver returns coordinates/bbox; useEffect centers map on mount |
| School slug pages lack school metadata (enrolments, sector) | MVP shows catchment boundary only; join school data as future enhancement |
