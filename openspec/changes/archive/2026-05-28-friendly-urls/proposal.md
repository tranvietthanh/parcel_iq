## Why

OZ Property Report currently uses opaque UUID-based URLs for property detail pages (`/property/{uuid}`) and has no URL-addressable pages for suburbs or school catchments. This creates two problems:

1. **SEO dead-end.** Search engines cannot index meaningful property or location pages. A URL like `/property/3f8a2c1d-9b4e-4c7a-a8d2-b1f3e5c6d7e8` provides no contextual signal and is not shareable in a way that communicates intent.

2. **No shareable state for non-property entities.** When a user searches for "Suzanne Cory High School" and the map pans to that catchment, the URL doesn't change — the view cannot be shared or bookmarked.

Friendly slug URLs fix both problems simultaneously:

- `/property/8-st-lawrence-close-werribee-vic-3030` is meaningful, indexable, and shareable
- `/suburb/vic/werribee-vic` and `/school/vic/suzanne-cory-high-school` create addressable landing pages for location-level discovery

This also sets the foundation for organic search traffic: Australians searching for a specific address or suburb can land directly on a data-rich page rather than a generic homepage.

## What Changes

- **New:** `slug` column on `properties` and `spatial_zones` tables — unique, kebab-case, generated at import time
- **New:** `infra/scripts/slug_utils.py` — shared slug generation + collision resolution utility
- **Modified:** Both import scripts (`import_spatial_zones.py`, `create_properties_from_gnaf.py`) generate and persist slugs on every row
- **New:** Two API slug-resolver routes (`GET /api/properties/slug/{slug}/detail`, `GET /api/search/zones/slug/{slug}`)
- **Modified:** Search API includes `slug` and `zone_state` in suggestion responses
- **New:** Three Next.js slug-based route pages (`/property/[slug]`, `/suburb/[state]/[slug]`, `/school/[state]/[slug]`) — each renders the full map + detail panel view, identical to the search-select experience
- **Removed:** `/property/[id]` UUID route — decommissioned, replaced by slug route
- **Modified:** Map page updates browser URL to the friendly slug on search result selection
- **Modified:** `my-properties` page links updated from UUID to slug (`/property/{slug}`)
- **Modified:** `proxy.ts` — remove `/property/(.*)` from Clerk protected routes so slug pages are publicly accessible (existing anonymous handling still applies)
- **Modified:** `my/requested` and `list_saved` API responses include `slug` field alongside `property_id`

## Capabilities

### New Capabilities

- `seo-friendly-property-urls`: Property detail pages reachable and indexable via human-readable address slug
- `seo-friendly-suburb-urls`: Suburb landing pages at `/suburb/{state}/{slug}` with SSR metadata
- `seo-friendly-school-urls`: School catchment landing pages at `/school/{state}/{slug}` with SSR metadata
- `shareable-search-selection`: Selecting any search result navigates the browser to a friendly URL that can be copied and shared

### Modified Capabilities

- `property-detail-page`: Now served from `/property/[slug]` instead of `/property/[id]` — renders the same map + panel view as selecting from search
- `search-suggestions`: API response now includes `slug` and `zone_state` fields per suggestion
- `spatial-zone-import`: Import script now generates and persists slugs for all zone types
- `property-import`: `create_properties_from_gnaf.py` generates and persists slugs per property
- `my-properties`: Links now point to slug URLs instead of UUID URLs

### Removed Capabilities

- `uuid-property-urls`: `/property/[id]` route removed — single page per entity, slug only

## Impact

**Database:** Two new `slug` columns (one on `properties`, one on `spatial_zones`) with `UNIQUE` indexes. Added via a new Alembic migration `027_add_slugs.py` — preserves migration chain integrity even though the DB is being wiped.

**Import scripts:** `create_properties_from_gnaf.py` adds slug generation per row within its existing batch loop. `slug_utils.py` is shared across both import scripts — no duplication.

**API:** Two new slug-resolver routes. `my/requested` and `list_saved` responses gain a `slug` field. Search response schema gains two new nullable fields (`slug`, `zone_state`).

**Frontend:** One route removed (`/property/[id]`), three routes added inside the `(map)` route group. Each slug page renders the full map + panel view — identical to the search-select experience. The `my-properties` page links updated to use slugs. `/property/(.*)` removed from Clerk protected routes for SEO crawlability.

**SEO:** Every new slug page includes `generateMetadata` with address/zone-specific `<title>` and `<meta name="description">`. No changes to existing metadata.

## Rollout Strategy

Since the DB is being wiped: run migrations (`alembic upgrade head`) then re-import all data with the updated import scripts. Deploy API + frontend after import completes. No phased rollout needed.
