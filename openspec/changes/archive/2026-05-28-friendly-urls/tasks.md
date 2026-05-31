## 1. Slug Utility

- [ ] 1.1 Create `infra/scripts/slug_utils.py` with:
  - `slugify(text: str) -> str` — lowercase, strip non-alphanumeric (keep hyphens/spaces), collapse to kebab-case
  - `make_property_slug(address_string: str) -> str` — `slugify(address_string)`
  - `make_zone_slug(name: str, state: str, zone_type: str) -> str` — strip school catchment suffixes for `SCHOOL_CATCHMENT` type, then `slugify(name) + "-" + state.lower()`
  - `ensure_unique_slug(base: str, seen: set[str]) -> str` — append random 4-char alphanumeric suffix on collision; add to `seen` and return

## 2. Database Migration

- [ ] 2.1 Create `shared/db-migrations/versions/027_add_slugs.py`:
  - `ALTER TABLE spatial_zones ADD COLUMN slug VARCHAR(300) NOT NULL DEFAULT ''`
  - `CREATE UNIQUE INDEX idx_spatial_zones_slug ON spatial_zones (slug)`
  - `ALTER TABLE properties ADD COLUMN slug VARCHAR(400) NOT NULL DEFAULT ''`
  - `CREATE UNIQUE INDEX idx_properties_slug ON properties (slug)`
  - Downgrade: drop indexes, drop columns
- [ ] 2.2 Update `docs/04-database.md` DDL section to include `slug` column in both table definitions

## 3. Import Scripts — Spatial Zones

- [ ] 3.1 Modify `infra/scripts/import_spatial_zones.py`:
  - Import `slug_utils` (relative import or add `infra/scripts` to `sys.path`)
  - Add `seen_slugs: set[str]` initialized before the feature loop in `import_zones()`
  - For each feature: call `make_zone_slug(name, state, zone_type)` then `ensure_unique_slug(base, seen_slugs)`
  - Add `slug` as a column in the INSERT statement
  - Add `slug = EXCLUDED.slug` to the `ON CONFLICT DO UPDATE SET` clause

## 4. Import Scripts — Properties

- [ ] 4.1 Modify `infra/scripts/create_properties_from_gnaf.py`:
  - Import `slug_utils`
  - Option A (SQL-based, preferred if fast enough): add slug generation as a SQL expression in the INSERT ... SELECT:
    ```sql
    trim(both '-' from regexp_replace(
        regexp_replace(lower(address_string), '[^a-z0-9\s-]', '', 'g'),
        '[\s-]+', '-', 'g'
    )) AS slug
    ```
  - Option B (Python-based, if SQL conflicts are problematic): fetch batch into Python, generate slugs with `make_property_slug()` + `ensure_unique_slug()`, insert with `executemany`
  - Maintain `seen_slugs: set[str]` across all batches (only for Option B)
  - Keep the `--state`, `--limit`, `--batch-size` CLI flags working as before
  - Use whichever approach is faster

## 5. Public API — Schema

- [ ] 5.1 Modify `services/public-api/app/schemas/search.py`:
  - Add `slug: str | None = None` to `SearchSuggestion`
  - Add `zone_state: str | None = None` to `SearchSuggestion`
- [ ] 5.2 Modify `services/public-api/app/schemas/property.py`:
  - Add `slug: str | None = None` to `PropertyDetail`

## 6. Public API — Search Router

- [ ] 6.1 Modify `services/public-api/app/routers/search.py`:
  - Update `TEXT_SEARCH_QUERY` ADDRESS branch: add `p.slug AS slug, NULL::text AS zone_state`
  - Update `TEXT_SEARCH_QUERY` zone branch: add `sz.slug AS slug, sz.state AS zone_state`
  - Update `_text_search()`: populate `slug=row["slug"]` and `zone_state=row["zone_state"]` in `SearchSuggestion` construction
  - Add new route `GET /zones/slug/{slug}` — resolves slug to zone GeoJSON (same payload as existing `GET /zones?zone_id=...`):
    ```python
    SELECT zone_type, name, state, ST_AsGeoJSON(geom)::json AS geometry, metadata
    FROM spatial_zones WHERE slug = $1
    ```

## 7. Public API — Properties Router

- [ ] 7.1 Modify `services/public-api/app/routers/properties.py`:
  - Add `p.slug` to `DETAIL_QUERY` SELECT
  - Populate `slug=row["slug"]` in `PropertyDetail` construction
  - Refactor existing `property_detail` handler: extract shared logic into `_get_property_detail(property_id, db)` helper
  - Add new route `GET /slug/{slug}/detail` **before** `GET /{property_id}/detail` in the router:
    1. `SELECT id FROM properties WHERE slug = $1`
    2. Return 404 if not found
    3. Delegate to `_get_property_detail(property_id, db)`

## 8. Public API — My Properties & Saved

- [ ] 8.1 Modify `services/public-api/app/routers/my_properties.py`:
  - Add `p.slug` to the `my/requested` SQL query SELECT (alongside `p.id AS property_id`)
  - Include `"slug": r["slug"]` in each item dict returned by `my_requested_properties()`
- [ ] 8.2 Modify `services/public-api/app/routers/saved.py`:
  - Add `p.slug` to `SAVED_LIST_QUERY` SELECT
  - Include `slug=row["slug"]` in `PropertyDetail` construction in `list_saved()`

## 9. Next.js — Types

- [ ] 9.1 Modify `apps/public-web/types/index.ts`:
  - Add `slug: string | null` to `SearchSuggestion` type
  - Add `zone_state: string | null` to `SearchSuggestion` type
  - Add `slug?: string` to `PropertyDetail` type

## 10. Next.js — Remove Old Route + Clerk Middleware

- [ ] 10.1 Delete `apps/public-web/app/property/[id]/page.tsx`
- [ ] 10.2 Modify `apps/public-web/proxy.ts`:
  - Remove `"/property/(.*)"` from the `isProtectedRoute` array
  - Keep `"/profile(.*)"` — profile pages still require auth

## 11. Next.js — Property Slug Page (Map + Panel)

- [ ] 11.1 Create `apps/public-web/app/(map)/property/[slug]/page.tsx`:
  - `generateMetadata({ params })`: call `serverApiRequest<PropertyDetail>("/api/properties/slug/${slug}/detail")` for property address; return `title: "${property.address} — OZ Property Report"` and `description`
  - Client component renders the same layout as the map page:
    - `MapContainer` + `SearchOmnibox` + `PropertyDetail` (panel mode) + `UserAvatar` + `Toast`
  - On mount (useEffect): fetch property data by slug → get coordinates + UUID → `map.flyTo(coordinates, zoom: 16)` → `setSelectedId(property.id)` to open the panel
  - Handle 404 gracefully (slug not found)

## 12. Next.js — Suburb Slug Page (Map + Zone Overlay)

- [ ] 12.1 Create `apps/public-web/app/(map)/suburb/[state]/[slug]/page.tsx`:
  - `generateMetadata`: fetch zone from `/api/search/zones/slug/${slug}`; return `title: "${zoneName}, ${STATE} — Suburb Overview | OZ Property Report"` and description
  - Client component renders same map layout
  - On mount: fetch zone GeoJSON → `map.fitBounds(zoneBbox)` → render zone boundary polygon as a map layer
  - Handle 404 gracefully

## 13. Next.js — School Slug Page (Map + Catchment Overlay)

- [ ] 13.1 Create `apps/public-web/app/(map)/school/[state]/[slug]/page.tsx`:
  - `generateMetadata`: fetch zone from `/api/search/zones/slug/${slug}`; return `title: "${zoneName} School Catchment — OZ Property Report"` and description
  - Client component renders same map layout
  - On mount: fetch zone GeoJSON → `map.fitBounds(catchmentBbox)` → render catchment boundary polygon as a map layer
  - Handle 404 gracefully

## 14. Next.js — Map Page URL Update

- [ ] 14.1 Modify `apps/public-web/app/(map)/page.tsx`:
  - Import `useRouter` from `next/navigation`
  - In `handleSearchSelect`: after map pan/fly + panel open, update URL via `router.replace()`:
    ```typescript
    if (result.type === "ADDRESS" && result.slug) {
      router.replace(`/property/${result.slug}`);
    } else if (result.type === "SUBURB" && result.slug && result.zone_state) {
      router.replace(`/suburb/${result.zone_state.toLowerCase()}/${result.slug}`);
    } else if (result.type === "SCHOOL_CATCHMENT" && result.slug && result.zone_state) {
      router.replace(`/school/${result.zone_state.toLowerCase()}/${result.slug}`);
    }
    ```
  - Note: uses `router.replace` (not `push`) to avoid polluting browser history

## 15. Next.js — My Properties Page Links

- [ ] 15.1 Modify `apps/public-web/app/my-properties/page.tsx`:
  - Update `RequestedItem` type: add `slug: string`
  - Line 149: change `href={`/property/${item.property_id}`}` → `href={`/property/${item.slug}`}`
  - Update `SavedProperty` type: add `slug: string`
  - Line 236: change `href={`/property/${p.id}`}` → `href={`/property/${p.slug}`}`

## 16. Shared Map View Component (optional refactor)

- [ ] 16.1 Consider extracting shared map + panel + search + avatar composition into a reusable `MapView` component to avoid code duplication across the 4 map pages (root, property slug, suburb slug, school slug). If duplication is minimal, skip this and inline the composition in each page.

## 17. Verification

- [ ] 17.1 Run `infra/scripts/import_spatial_zones.py --type SUBURB --source <test.geojson> --state VIC --truncate` against local DB; verify `SELECT slug FROM spatial_zones LIMIT 10` returns well-formed slugs, no NULLs, no duplicates
- [ ] 17.2 Run `infra/scripts/create_properties_from_gnaf.py --state VIC --limit 500`; verify `SELECT slug FROM properties LIMIT 10` returns well-formed slugs; verify `SELECT COUNT(DISTINCT slug) = COUNT(*) FROM properties` (uniqueness)
- [ ] 17.3 `GET /api/search?q=werribee` — verify response includes `slug` and `zone_state` fields on every suggestion
- [ ] 17.4 `GET /api/properties/slug/8-st-lawrence-close-werribee-vic-3030/detail` — returns 200 with full PropertyDetail payload including `slug` field
- [ ] 17.5 `GET /api/properties/slug/does-not-exist/detail` — returns 404
- [ ] 17.6 `GET /api/search/zones/slug/werribee-vic` — returns GeoJSON Feature with MultiPolygon geometry
- [ ] 17.7 Browse `/property/{valid-slug}` in dev server — page renders with map centered on property + PropertyDetail panel open on the right, correct address in `<title>`
- [ ] 17.8 Browse `/suburb/vic/werribee-vic` — page renders with map fitted to suburb boundary, zone boundary visible on map, correct title and metadata
- [ ] 17.9 Browse `/school/vic/suzanne-cory-high-school-vic` — page renders with map fitted to catchment boundary, correct title and metadata
- [ ] 17.10 On map page `/`, type "Werribee" in search, select an ADDRESS result — browser URL updates to `/property/{slug}`, map centers on property, panel opens
- [ ] 17.11 On map page `/`, type "Suzanne Cory" in search, select the SCHOOL result — browser URL updates to `/school/vic/{slug}`, map fits to catchment
- [ ] 17.12 Verify old `/property/{uuid}` returns 404 (route deleted)
- [ ] 17.13 Verify `my-properties` page links point to `/property/{slug}` and navigate correctly
- [ ] 17.14 Verify `/property/{slug}` is accessible without authentication (anonymous user sees disclaimer + limited data)
