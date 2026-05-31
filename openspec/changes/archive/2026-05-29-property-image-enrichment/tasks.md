# Tasks: property-image-enrichment

## 0. Delete Orphan File

- [x] **0.1** Delete `services/admin-backend/app/services/report_pdf_generator.py`
  - Confirm it is not imported anywhere (`grep -r "report_pdf_generator" services/admin-backend/`)
  - The shared package `shared/pdf-renderer/pdf_renderer/full_report.py` is the sole source of truth

---

## 1. Config & Env Vars

- [x] **1.1** `services/admin-backend/app/config.py`
  - Remove: `MAP_ENRICHMENT_ENABLED`, `MAP_PROVIDER`, `MAP_STATIC_URL`, `MAP_API_KEY`, `MAPBOX_ACCESS_TOKEN`, `MAPBOX_STYLE_ID`, `MAPBOX_ZOOM`, `MAP_REQUEST_TIMEOUT_SECONDS`
  - Add: `PROPERTY_IMAGE_ENRICHMENT_ENABLED: bool = False`, `GOOGLE_MAPS_API_KEY: str | None = None`, `PROPERTY_IMAGE_REQUEST_TIMEOUT_SECONDS: float = 4.0`
  - Note: these fields are for documentation/discoverability — the shared PDF renderer reads via `os.getenv()`, not `settings.*`

- [x] **1.2** `services/admin-backend/.env.example`
  - Replace the `## Report Map Enrichment` block with the new `## Property Image Enrichment` block documenting `PROPERTY_IMAGE_ENRICHMENT_ENABLED` and `GOOGLE_MAPS_API_KEY`

- [x] **1.3** `infra/k8s/configmap.yaml`
  - Replace `MAP_ENRICHMENT_ENABLED: "false"` → `PROPERTY_IMAGE_ENRICHMENT_ENABLED: "false"`
  - Remove `MAP_PROVIDER: "osm_static"` and `MAP_STATIC_URL: "https://staticmap.openstreetmap.de/staticmap.php"`

- [x] **1.4** Root `.env.example`
  - Update the `GOOGLE_API_KEY` comment line to `GOOGLE_MAPS_API_KEY=` with a note that it's used for Maps Static + Street View APIs

- [x] **1.5** `services/admin-backend/.env` (live config)
  - Replace: `MAP_ENRICHMENT_ENABLED`, `MAP_PROVIDER`, `MAPBOX_ACCESS_TOKEN`, `MAPBOX_STYLE_ID`, `MAPBOX_ZOOM` with `PROPERTY_IMAGE_ENRICHMENT_ENABLED=true` and `GOOGLE_MAPS_API_KEY=<key>`

---

## 2. Shared PDF Renderer (single source of truth)

File: `shared/pdf-renderer/pdf_renderer/full_report.py`

> All PDF generation changes live here only. Both `admin-backend` and `public-api` consume this package.

- [x] **2.1** Add `import concurrent.futures` at the top of the file (if not already present)

- [x] **2.2** Replace `_fetch_static_map_bytes()` with `_fetch_satellite_bytes(lat, lng)`:
  - URL: `https://maps.googleapis.com/maps/api/staticmap`
  - Params: `center=lat,lng`, `zoom=20`, `size=640x640`, `scale=2`, `maptype=hybrid`, `markers=color:red|lat,lng`, `key=os.getenv("GOOGLE_MAPS_API_KEY")`
  - Return `(None, "disabled")` if `PROPERTY_IMAGE_ENRICHMENT_ENABLED` is false
  - Return `(None, "missing_api_key")` if key is not set
  - Handle `httpx.HTTPError` → `(None, f"request_error:{...}")`
  - Handle non-200 → `(None, f"status:{code}")`
  - Handle non-image content-type → `(None, "invalid_content_type")`

- [x] **2.3** Add `_fetch_streetview_bytes(lat, lng, heading)`:
  - URL: `https://maps.googleapis.com/maps/api/streetview`
  - Params: `size=640x420`, `location=lat,lng`, `heading=heading`, `pitch=0`, `fov=90`, `key=os.getenv("GOOGLE_MAPS_API_KEY")`
  - Return `(None, "no_coverage")` if `len(content) < 8_000`
  - Same error handling pattern as satellite

- [x] **2.4** Add `_fetch_all_streetview_bytes(lat, lng) -> dict[int, bytes]`:
  - Headings: `[315, 0, 45, 135, 180, 225]`
  - Dispatch all 6 concurrently via `ThreadPoolExecutor(max_workers=6)`
  - Return dict of `{heading: bytes}` for successful fetches only (skip None results)

- [x] **2.5** Update `_build_cover_map_block()`:
  - Call `_fetch_satellite_bytes()` instead of `_fetch_static_map_bytes()`
  - Update attribution to `"Map imagery © Google. Approximate location shown."`
  - Keep same PDF Image dimensions (`width=CONTENT_W, height=130*mm`)

- [x] **2.6** Update `_map_unavailable_detail()`:
  - Remove Mapbox/OSM-specific reason strings
  - Add `"disabled"` → `"Property imagery disabled (set PROPERTY_IMAGE_ENRICHMENT_ENABLED=true)."`
  - Add `"missing_api_key"` → `"GOOGLE_MAPS_API_KEY is not configured."`

- [x] **2.7** Add `_build_street_view_grid(images: dict[int, bytes], styles) -> list[Any]`:
  - Heading labels: `{315: "NW 315°", 0: "N 0°", 45: "NE 45°", 135: "SE 135°", 180: "S 180°", 225: "SW 225°"}`
  - Build `Image` flowables at `width=CONTENT_W/3 - 2*mm, height=40*mm` for each available heading
  - Arrange in a 3-column `Table`, 2 rows (row 1: 315°, 0°, 45° — row 2: 135°, 180°, 225°)
  - Empty cells for missing headings (show light-grey placeholder cell with "No coverage" text)
  - Add attribution paragraph below the table

- [x] **2.8** Add `build_property_street_view(data, styles) -> list[Any]`:
  - Return `[]` if `PROPERTY_IMAGE_ENRICHMENT_ENABLED` is false
  - Return `[]` if coordinates unavailable
  - Call `_fetch_all_streetview_bytes(lat, lng)`
  - If no images returned: return section title + "No Street View coverage available at this location." paragraph
  - Otherwise: return `section_title("Property Street View", styles)` + grid table

- [x] **2.9** Update `_build_location_context()` in Connectivity section:
  - Remove the existing map image block (it called `_fetch_static_map_bytes()`)
  - Keep only the `"Coordinates: lat, lng"` paragraph

- [x] **2.10** Update `build_report()`:
  - After `build_cover()` + `PageBreak()`, call `build_property_street_view()`
  - Only add a second `PageBreak()` before `build_narrative()` if street view returned non-empty content
  - Full report only (`variant == "full"`)

---

## 3. Verification

- [x] **3.1** Set `PROPERTY_IMAGE_ENRICHMENT_ENABLED=true` and `GOOGLE_MAPS_API_KEY=<real key>` in `services/admin-backend/.env`

- [x] **3.2** Trigger a full report regeneration via admin panel for a known address with Street View coverage (e.g. `8 St Lawrence Close, Werribee VIC 3030`)

- [x] **3.3** Open the generated PDF and verify:
  - Cover page shows the satellite hybrid aerial image (not a road map)
  - Page 2 is the "Property Street View" section with up to 6 images in a 3×2 grid
  - Attribution lines are present on both pages
  - No crash, no blank pages inserted when enrichment is disabled

- [x] **3.4** Test degradation: set `PROPERTY_IMAGE_ENRICHMENT_ENABLED=false`, regenerate — confirm both image blocks show placeholder text, no Street View page is added

- [x] **3.5** Test degradation: set `GOOGLE_MAPS_API_KEY=` (empty), regenerate — confirm graceful placeholder with "GOOGLE_MAPS_API_KEY is not configured." message
