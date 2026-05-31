## Why

Property reports currently include a generic street/road map via `MAP_ENRICHMENT_ENABLED` (backed by OSM Static or Mapbox). This provides little differentiation — a road map already exists on any phone. Investors want to *see* the property: its rooftop from above and its street presence from every direction.

While investigating the implementation, we also found that `services/admin-backend/app/services/report_pdf_generator.py` is an **orphan file** — it is not imported anywhere. The actual PDF generation code used at runtime lives exclusively in `shared/pdf-renderer/pdf_renderer/full_report.py` (consumed by both `admin-backend` and `public-api`). The orphan will be deleted as part of this change.

The Google Maps Platform unlocks two high-value views:

1. **Satellite Hybrid at Zoom 20** — crisp aerial imagery of the exact property parcel, with road labels. Far more useful than a road map for understanding lot size, orientation, surrounding density, and nearby amenities.
2. **Street View at 6 headings** — because property orientation relative to the street is unknown, providing a full 360° sweep (6 × 60° apart) gives investors a complete ground-level picture regardless of which way the property faces.

The existing OSM/Mapbox provider system is removed entirely. A single `GOOGLE_MAPS_API_KEY` replaces the current `MAP_PROVIDER`, `MAPBOX_*`, and `MAP_STATIC_URL` family of variables.

## What Changes

- **Delete** the orphan `services/admin-backend/app/services/report_pdf_generator.py` (not imported anywhere — dead code)
- **Replace** `_fetch_static_map_bytes()` in `shared/pdf-renderer/pdf_renderer/full_report.py` with two focused fetchers:
  - `_fetch_satellite_bytes(lat, lng)` — Google Static Maps API, `maptype=hybrid`, zoom 20, scale 2
  - `_fetch_streetview_bytes(lat, lng, heading)` — Google Street View Static API, 640×420, FOV 90
- **Replace** the cover page map block with the new satellite image
- **Add** `build_property_street_view()` — new full-report-only section inserted as page 2, showing a 3×2 grid of Street View images at headings 315°, 0°, 45°, 135°, 180°, 225°
- **Retire** `MAP_PROVIDER`, `MAP_STATIC_URL`, `MAP_API_KEY`, `MAPBOX_ACCESS_TOKEN`, `MAPBOX_STYLE_ID`, `MAPBOX_ZOOM` env vars
- **Add** `GOOGLE_MAPS_API_KEY` env var (single key serves both APIs)
- **Rename** the feature flag to `PROPERTY_IMAGE_ENRICHMENT_ENABLED` (replaces `MAP_ENRICHMENT_ENABLED`)
- All PDF generation changes apply **only** to `shared/pdf-renderer/pdf_renderer/full_report.py` — the single source of truth

## Capabilities

### Modified Capabilities

- `report-pdf-generation`: Full report now includes a satellite cover map and a dedicated Street View page (page 2) when `PROPERTY_IMAGE_ENRICHMENT_ENABLED=true`. Lite report includes only the satellite cover image.

### Retired Capabilities

- `osm-map-enrichment`: OSM Static provider removed
- `mapbox-map-enrichment`: Mapbox provider removed

## Impact

**Deduplication**
- `services/admin-backend/app/services/report_pdf_generator.py` — **deleted** (orphan, never imported)

**Config changes**
- `services/admin-backend/app/config.py` — remove old map vars, add `GOOGLE_MAPS_API_KEY` and rename flag
- `services/admin-backend/.env.example` — update docs
- `infra/k8s/configmap.yaml` — rename the env flag key
- Root `.env.example` — uncomment/update Google key placeholder

**PDF output changes (full report)**
- Cover page: satellite hybrid aerial replaces road map (same dimensions — `CONTENT_W × 130mm`)
- Page 2: new "Property Images" section — 3×2 grid of Street View shots, each `~(CONTENT_W/3) × 40mm`
- Attribution updated to `© Google Maps imagery` / `© Google Street View`

**PDF output changes (lite report)**
- Cover page: satellite hybrid replaces road map
- No Street View page (lite remains condensed)

## Rollout Strategy

1. Add `GOOGLE_MAPS_API_KEY` secret to K8s and staging `.env`
2. Deploy updated `admin-backend` with `PROPERTY_IMAGE_ENRICHMENT_ENABLED=true`
3. Deploy updated `shared/pdf-renderer` package (used by the same service)
4. Regenerate a test report and verify satellite cover + Street View page
5. Remove old `MAP_PROVIDER` / `MAPBOX_*` vars from all `.env` files and K8s configmap
