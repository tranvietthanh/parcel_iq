## Context

The PDF report generator has **one source of truth**: `shared/pdf-renderer/pdf_renderer/full_report.py`. This package is imported by both `services/admin-backend` and `services/public-api` via a `file://` path dependency in their `pyproject.toml` files.

`services/admin-backend/app/services/report_pdf_generator.py` is a **dead orphan** — it is not imported by any module. It will be deleted as part of this change to eliminate future confusion.

The PDF is generated synchronously inside a Celery task (fire-and-forget). Latency during generation is acceptable; PDF is stored to MinIO and the user retrieves it after polling.

Property coordinates are always available via `data["_property_location"]["latitude"]` / `["longitude"]` when a report has been through the LLM parser. If coordinates are missing, all image blocks degrade gracefully to a placeholder.

## Goals / Non-Goals

**Goals**
- Replace cover page map with Google satellite hybrid (zoom 20, scale 2)
- Add Street View section (page 2, full report only) with 6 headings: 315°, 0°, 45°, 135°, 180°, 225°
- Skip any heading where Google returns a no-coverage placeholder (< 8 KB response)
- Single `GOOGLE_MAPS_API_KEY` env var replaces the old `MAP_PROVIDER` / `MAPBOX_*` / `MAP_STATIC_URL` cluster
- Graceful degradation: if API key missing or all images fail, show a styled placeholder, never crash

**Non-Goals**
- Street View on the lite report
- Detecting actual property orientation to pick the "best" heading
- Caching images between report regenerations
- Using the Street View Metadata API to pre-validate coverage

## Decisions

### Decision 1: Google-only, no provider abstraction

The old multi-provider pattern (`osm_static` | `mapbox`) is removed. A single `GOOGLE_MAPS_API_KEY` is sufficient — both Maps Static and Street View Static use the same key. No provider enum or dispatch logic is needed.

### Decision 2: Use lat/lng, not address strings

Both Google APIs accept `location=lat,lng`. Using coordinates is more precise than address strings, especially for rural properties or unusual address formats. Coordinates are already available in `data["_property_location"]`.

### Decision 3: 6 Street View headings — 3 pairs of opposites

Headings: **315°, 0°, 45°, 135°, 180°, 225°**

These are three opposite pairs (NW↔SE, N↔S, NE↔SW), providing complete spatial context without knowing the property's orientation. Rendered as a 3×2 grid.

Images with `len(response.content) < 8_000` bytes are skipped — Google returns a small grey placeholder when Street View has no coverage at that heading. The grid renders only available images, up to 6.

### Decision 4: Concurrent Street View fetches using ThreadPoolExecutor

6 Street View calls are dispatched in parallel via `concurrent.futures.ThreadPoolExecutor(max_workers=6)`. Each call has a 4-second timeout (`PROPERTY_IMAGE_REQUEST_TIMEOUT_SECONDS`). Worst-case latency is therefore ~4s for the Street View block rather than ~24s sequential.

The satellite call is made separately (sequential, before the Street View block is built).

### Decision 5: Feature flag rename

`MAP_ENRICHMENT_ENABLED` → `PROPERTY_IMAGE_ENRICHMENT_ENABLED`

The `os.getenv()` calls in `shared/pdf-renderer/pdf_renderer/full_report.py` are updated. The pydantic `Settings` class in `admin-backend/app/config.py` also gets the renamed field for documentation/discoverability (though the shared package reads env vars directly, not via `settings`). The old key is retired from all env files and the K8s configmap.

### Decision 6: Image sizing in the PDF

**Satellite (cover)**
- Google API: `size=640x640&scale=2` → 1280×1280 px actual
- PDF render: `width=CONTENT_W, height=130*mm` (same as current map block — no layout change)

**Street View (page 2 grid)**
- Google API: `size=640x420`
- PDF render: each image cell `width=CONTENT_W/3, height=40*mm`
- 3 images per row, 2 rows, with a 2mm gutter between cells

### Decision 7: Attribution strings

- Satellite: `© Google Maps imagery. Approximate location shown.`
- Street View: `© Google Street View. Images may not reflect current state of the property.`

### Decision 8: admin-backend config.py cleanup

The following fields are removed from `Settings`:
```
MAP_PROVIDER, MAP_STATIC_URL, MAP_API_KEY,
MAPBOX_ACCESS_TOKEN, MAPBOX_STYLE_ID, MAPBOX_ZOOM
```

New fields:
```python
PROPERTY_IMAGE_ENRICHMENT_ENABLED: bool = False
GOOGLE_MAPS_API_KEY: str | None = None
PROPERTY_IMAGE_REQUEST_TIMEOUT_SECONDS: float = 4.0
```

### Decision 9: Shared/pdf-renderer uses os.getenv — no Settings dependency

`shared/pdf-renderer` uses raw `os.getenv()` (it's a standalone package, not FastAPI). The same new env var names are read via:
```python
os.getenv("PROPERTY_IMAGE_ENRICHMENT_ENABLED", "false").lower() == "true"
os.getenv("GOOGLE_MAPS_API_KEY", "")
os.getenv("PROPERTY_IMAGE_REQUEST_TIMEOUT_SECONDS", "4.0")
```

## Module Structure

### New / replaced functions in shared PDF renderer

```
_fetch_satellite_bytes(lat, lng) → tuple[bytes | None, str | None]
    • Calls: maps.googleapis.com/maps/api/staticmap
    • Params: center=lat,lng, zoom=20, size=640x640, scale=2,
              maptype=hybrid, markers=color:red|lat,lng, key=API_KEY
    • Returns: (image_bytes, None) or (None, reason_str)

_fetch_streetview_bytes(lat, lng, heading) → tuple[bytes | None, str | None]
    • Calls: maps.googleapis.com/maps/api/streetview
    • Params: size=640x420, location=lat,lng, heading=heading,
              pitch=0, fov=90, key=API_KEY
    • Returns: (image_bytes, None) or (None, "no_coverage" | reason_str)
    • Skips if len(content) < 8_000 (placeholder detection)

_fetch_all_streetview_bytes(lat, lng) → dict[int, bytes]
    • Dispatches 6 headings concurrently via ThreadPoolExecutor
    • Returns dict of {heading: bytes} for headings with valid imagery only

_build_cover_map_block(data, styles) → list[Any]
    • Calls _fetch_satellite_bytes(); same signature, same cover placement
    • Updates attribution string to Google

_build_street_view_section(data, styles) → list[Any]
    • New function — builds the 3×2 grid table
    • Skips gracefully if no coordinates or no imagery available
    • Returns empty list if PROPERTY_IMAGE_ENRICHMENT_ENABLED=false

build_property_street_view(data, styles) → list[Any]
    • Public section builder — wraps _build_street_view_section
    • Includes section_title("Property Street View", styles)
```

### Changes to build_report()

```python
# Full report only — insert after cover, before narrative:
story += build_cover(data, address, styles)
story.append(PageBreak())
story += build_property_street_view(data, styles)  # ← NEW (no-op if enrichment disabled)
if build_property_street_view result is non-empty:
    story.append(PageBreak())
story += build_narrative(data, styles)
...
```

The Street View page only adds a `PageBreak` before narrative if there is actually content (avoids a blank page when enrichment is disabled or imagery unavailable).

## File Layout

```
services/admin-backend/
  app/config.py                             ← remove old MAP_* vars, add new ones
  app/services/report_pdf_generator.py     ← DELETE (orphan — not imported anywhere)
  .env.example                             ← replace MAP_* block, document new vars

shared/pdf-renderer/
  pdf_renderer/full_report.py              ← ALL PDF generation changes (single source of truth)

infra/k8s/
  configmap.yaml                           ← rename MAP_ENRICHMENT_ENABLED key

.env.example (root)                        ← update GOOGLE_API_KEY placeholder comment
```

## Error Handling & Graceful Degradation

| Condition | Satellite cover | Street View section |
|---|---|---|
| `PROPERTY_IMAGE_ENRICHMENT_ENABLED=false` | Grey placeholder with message | Section omitted (no page break) |
| `GOOGLE_MAPS_API_KEY` not set | Grey placeholder | Section omitted |
| No property coordinates | Grey placeholder | Section omitted |
| API returns HTTP error | Grey placeholder | Affected headings skipped |
| API returns < 8KB (no coverage) | N/A | That heading skipped |
| All 6 headings unavailable | N/A | Section shows "No Street View coverage available." |

## Risks / Mitigations

1. **Risk:** Google API costs — Maps Static + 6 SV calls per report = 7 API calls
   - **Mitigation:** Feature is off by default (`PROPERTY_IMAGE_ENRICHMENT_ENABLED=false`). Google $200/month free tier covers Maps Static at $2/1000 calls and SV Static at $7/1000 calls — ~600 reports/month before incurring costs.

2. **Risk:** ThreadPoolExecutor in Celery worker creates nested threads
   - **Mitigation:** Celery workers are multi-threaded by default; `ThreadPoolExecutor` with `max_workers=6` and short-lived tasks is safe. Each thread makes one HTTP call and exits.

3. **Risk:** `shared/pdf-renderer` is a separate package — changes must be deployed together with `admin-backend`
   - **Mitigation:** Both packages are in the same monorepo and deployed from the same Docker image build; they stay in sync.

4. **Risk:** The 8KB threshold for placeholder detection may clip real imagery in edge cases
   - **Mitigation:** Google's grey placeholder is consistently ~5–6KB. Real Street View images are typically 30KB+. 8KB is a safe cut-off.
