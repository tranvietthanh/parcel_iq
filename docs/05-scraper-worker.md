# OZ Property Report – Scraper Worker Specification

## 1. Overview

**Technology:** Python 3.12, Celery, Playwright (Python), httpx, psycopg2  
**Purpose:** Acquires raw property data from national, state, and council sources, stores raw output in the database, then enqueues the LLM parser task.

Uses an **Adapter Pattern**: a registry maps each data source name to an adapter class. Workers load the correct adapter per task and merge outputs from multiple sources.

---

## 2. Project Structure

```
/scraper-worker
├── app/
│   ├── celery_app.py          # Celery app factory + queue config
│   ├── config.py              # pydantic-settings config
│   ├── tasks.py               # Celery task definitions (entry points)
│   ├── adapters/
│   │   ├── base.py            # Abstract BaseAdapter class
│   │   ├── registry.py        # Maps adapter_name → class
│   │   ├── national/
│   │   │   ├── abs_census.py      # ABS DataAPI (all states)
│   │   │   └── nbnco.py           # NBN Co connectivity API (all addresses)
│   │   ├── state/
│   │   │   ├── vic_plan.py        # VicPlan API (VIC)
│   │   │   └── generic_state.py   # Generic fallback (NSW/QLD/SA/WA/TAS/ACT/NT)
│   │   └── council/
│   │       ├── tech_one.py        # TechnologyOne planning portals
│   │       ├── objective.py       # Objective ECM / Pathway portals
│   │       └── generic_html.py    # Fallback: generic HTML extractor
│   ├── services/
│   │   ├── db.py              # psycopg2 connection (sync, for Celery)
│   │   ├── minio_client.py    # MinIO / S3 operations
│   │   └── proxy.py           # Rotating residential proxy pool
│   └── utils/
│       ├── retry.py           # Exponential backoff decorator
│       ├── robots.py          # robots.txt compliance checker
│       └── pdf_extract.py     # PDF text extraction (pdfminer.six)
├── Dockerfile
├── requirements.txt
└── pyproject.toml
```

---

## 3. Celery App Factory (`app/celery_app.py`)

```python
from celery import Celery

celery_app = Celery("ozpr_scraper")

celery_app.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Australia/Sydney",
    task_routes={
        "app.tasks.scrape_property":    {"queue": "data_acquisition_queue"},
        "app.tasks.parse_with_llm":     {"queue": "llm_processing_queue"},
    },
    task_acks_late=True,          # only ack after task completes (no data loss on worker crash)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # prevents workers hoarding tasks from the queue
    task_default_retry_delay=30,
    task_max_retries=3,
)
```

---

## 4. Task Definition (`app/tasks.py`)

```python
from celery import shared_task
from app.celery_app import celery_app
from app.adapters.registry import adapter_registry
from app.services.db import get_db_connection
from app.services.minio_client import minio_client

@celery_app.task(
    bind=True,
    name="app.tasks.scrape_property",
    queue="data_acquisition_queue",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def scrape_property(
    self,
    property_id: str,
    gnaf_pid: str,
    address_string: str,
    latitude: float,
    longitude: float,
    lga_name: str,
    state: str,
) -> None:
    db = get_db_connection()
    try:
        # 1. Mark report as PROCESSING
        with db.cursor() as cur:
            cur.execute(
                """UPDATE property_reports
                   SET status = 'PROCESSING', updated_at = NOW()
                   WHERE property_id = %s AND status = 'QUEUING'""",
                (property_id,)
            )
            db.commit()

        # 2. Load adapter config for this LGA
        with db.cursor() as cur:
            cur.execute(
                "SELECT adapter_name, base_url, config FROM data_source_configs "
                "WHERE lga_name = %s AND state = %s",
                (lga_name, state)
            )
            config_row = cur.fetchone()

        # 3. Run all relevant adapters (parallel via threading for I/O bound work)
        job_payload = {
            "property_id": property_id,
            "gnaf_pid": gnaf_pid,
            "address_string": address_string,
            "latitude": latitude,
            "longitude": longitude,
            "lga_name": lga_name,
            "state": state,
        }

        results = run_adapters_parallel(job_payload, config_row, state)
        merged_data = merge_adapter_results(results)

        # 4. Store raw data in MinIO (audit trail + LLM fallback)
        object_key = f"raw-scrapes/{property_id}/{self.request.id}.json"
        minio_client.put_object_json("raw-scrape-cache", object_key, merged_data)

        # 5. Insert new property_reports row (append model — one row per scrape cycle)
        #    NOTE: property_reports has no UNIQUE on property_id — multiple rows per
        #    property are expected. The latest report is resolved via
        #    ORDER BY created_at DESC LIMIT 1 in read queries.
        with db.cursor() as cur:
            cur.execute(
                """INSERT INTO property_reports
                   (property_id, status, raw_scraped_data, scraper_version)
                   VALUES (%s, 'PROCESSING', %s, %s)
                   RETURNING id""",
                (property_id, json.dumps(merged_data), SCRAPER_VERSION)
            )
            report_id = cur.fetchone()[0]
            cur.execute(
                "UPDATE properties SET last_scraped_at = NOW() WHERE id = %s",
                (property_id,)
            )
            db.commit()

        # 6. Dispatch LLM parsing task
        from app.tasks import parse_with_llm
        parse_with_llm.apply_async(
            kwargs={
                "property_id": property_id,
                "property_report_id": str(report_id),
                "address_string": address_string,
            },
            queue="llm_processing_queue",
        )

    except Exception as exc:
        db.rollback()
        if self.request.retries >= self.max_retries:
            # Final failure — mark as FAILED
            with db.cursor() as cur:
                cur.execute(
                    """UPDATE property_reports
                       SET status = 'FAILED', error_message = %s, updated_at = NOW()
                       WHERE property_id = %s""",
                    (str(exc), property_id)
                )
                db.commit()
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
    finally:
        db.close()
```

---

## 5. Base Adapter (`app/adapters/base.py`)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ScrapedPropertyData:
    """Merged output from all adapters for a single property."""
    # State-level planning data
    zoning_code: str | None = None
    zoning_label: str | None = None
    overlays: list[str] = field(default_factory=list)
    flood_risk: Literal["NONE", "LOW", "MEDIUM", "HIGH"] | None = None
    bushfire_risk: Literal["NONE", "LOW", "MEDIUM", "HIGH"] | None = None

    # National data
    nbn_type: str | None = None
    demographics: dict | None = None

    # Council-level data (unstructured text for LLM to parse)
    council_planning_applications_text: str | None = None
    council_meeting_minutes_text: str | None = None

    # Source attribution (for data quality + display)
    data_sources: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


class BaseAdapter(ABC):
    def __init__(self, base_url: str, config: dict):
        self.base_url = base_url
        self.config = config

    @abstractmethod
    def scrape(self, job: dict) -> dict:
        """Returns a partial ScrapedPropertyData dict to be merged."""
        ...

    def fetch_json(self, url: str, timeout: int = 15) -> dict:
        """Synchronous HTTP GET with retry. Use for simple API calls."""
        import httpx
        from app.utils.retry import retry_with_backoff

        def _get():
            resp = httpx.get(url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()

        return retry_with_backoff(_get, retries=3, delay=2.0)
```

---

## 6. National Adapters (No Browser Needed)

### 6.1 ABS Census Adapter (`national/abs_census.py`)

**Caching Strategy:** ABS Census data is persisted in the `abs_census_data` table to eliminate slow API downloads. Each SA2 is cached indefinitely at first load, then optionally refreshed via admin dashboard.

```python
class AbsCensusAdapter(BaseAdapter):
    """
    Fetches SA2-level demographic data from the ABS DataAPI.
    Uses database-backed caching — checks DB first, API on cache miss.
    Covers all Australian states — single national adapter.
    
    Performance:
    - DB hit: 0.1s (single row lookup)
    - API call: 3-6s (full national dataset download)
    - Net speedup: 11x after first cache hit (0.6s vs 6.5s per property)
    """

    def scrape(self, job: dict) -> dict:
        # 1. Resolve lat/lng to SA2 code via ABS Geography API (0.5s)
        sa2_code = self._resolve_sa2(job["latitude"], job["longitude"])
        if not sa2_code:
            return {"demographics": None}

        # 2. Check database cache first
        cached = get_census_data_from_db(db, sa2_code)
        if cached:
            return {
                "demographics": {
                    "sa2_code": sa2_code,
                    "median_household_weekly_income_aud": cached["median"],
                    "owner_occupier_percent": cached["owner_percent"],
                    "source": "ABS Census 2021 (cached)",  # ← DB read
                },
                "data_sources": [{
                    "name": "ABS Census Database Cache",
                    "cache_hit": True,
                    "fetched_at": datetime.utcnow().isoformat(),
                }],
            }

        # 3. Cache miss — download from API (3-6s)
        income_data = self.fetch_json(
            f"https://api.data.abs.gov.au/data/ABS,G17_2021_AUST_SA2/{sa2_code}"
            f"?format=jsondata&detail=dataonly"
        )
        dwelling_data = self.fetch_json(
            f"https://api.data.abs.gov.au/data/ABS,G46_2021_AUST_SA2/{sa2_code}"
            f"?format=jsondata&detail=dataonly"
        )

        median_income = self._extract_median_income(income_data)
        owner_percent = self._extract_owner_percent(dwelling_data)

        # 4. Store in database for reuse
        store_census_data_to_db(db, sa2_code, median_income, owner_percent, {
            "income_data": income_data,
            "dwelling_data": dwelling_data,
        })

        return {
            "demographics": {
                "sa2_code": sa2_code,
                "median_household_weekly_income_aud": median_income,
                "owner_occupier_percent": owner_percent,
                "source": "ABS Census 2021 (newly cached)",  # ← API source + stored
            },
            "data_sources": [{
                "name": "ABS DataAPI",
                "url": f"https://api.data.abs.gov.au/data/",
                "cache_hit": False,
                "fetched_at": datetime.utcnow().isoformat(),
            }],
        }

    def _resolve_sa2(self, lat: float, lng: float) -> str | None:
        """Resolve lat/lng to SA2 code using ABS boundaries API."""
        try:
            data = self.fetch_json(
                f"https://api.data.abs.gov.au/geography/point?lat={lat}&lng={lng}&level=SA2"
            )
            return data.get("sa2_code")
        except Exception:
            return None
```

**Database Functions** (in `app/services/abs_census_db.py`):

```python
def get_census_data_from_db(db, sa2_code: str) -> dict | None:
    """Query SA2 from cache. Returns {median, owner_percent} or None."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT median_household_income_weekly_aud, owner_occupier_percent "
            "FROM abs_census_data WHERE sa2_code_2021 = %s LIMIT 1",
            (sa2_code,)
        )
        row = cur.fetchone()
    return {
        "median": row[0],
        "owner_percent": float(row[1])
    } if row else None

def store_census_data_to_db(db, sa2_code: str, median: int, owner: float, raw_data: dict) -> bool:
    """Insert or update SA2 cache. Returns True on success."""
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO abs_census_data
               (sa2_code_2021, median_household_income_weekly_aud, owner_occupier_percent, raw_data)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (sa2_code_2021) DO UPDATE
               SET median_household_income_weekly_aud = EXCLUDED.median_household_income_weekly_aud,
                   owner_occupier_percent = EXCLUDED.owner_occupier_percent,
                   raw_data = EXCLUDED.raw_data,
                   updated_at = NOW()
            """,
            (sa2_code, median, owner, json.dumps(raw_data))
        )
        db.commit()
    return True
```

**Refresh Task** (Celery, in `app/tasks_census_refresh.py`):

```python
@celery_app.task(
    bind=True,
    name="app.tasks.refresh_abs_census_complete",
    queue="admin_queue",
    max_retries=1,
)
def refresh_abs_census_complete(self, delete_existing: bool = True, force: bool = False) -> dict:
    """
    Background job to download and cache Census data for all ~2,200 Australian SA2s.
    
    Args:
        delete_existing: If True, clear the cache before syncing (full refresh).
        force: If True, re-download even if cache exists.
    
    Returns:
        {
            "sa2s_found": 2180,
            "stored": 2180,
            "cache_count_before": 150,
            "cache_count_after": 2180,
        }
    
    Time: 5-10 minutes for full national sync.
    """
    db = get_db_connection()
    try:
        adapter = AbsCensusAdapter(base_url="", config={})
        
        # Download full national datasets
        income_data = adapter.fetch_json(
            "https://api.data.abs.gov.au/data/ABS,G17_2021_AUST_SA2"
            "?format=jsondata&detail=dataonly"
        )
        dwelling_data = adapter.fetch_json(...)
        
        # Extract all SA2 codes and compute statistics
        #... [extraction logic] ...
        
        # Store each SA2
        for sa2_code in distinct_sa2s:
            store_census_data_to_db(db, sa2_code, median, owner, raw_data)
        
        return {
            "sa2s_found": len(distinct_sa2s),
            "stored": stored_count,
            "cache_count_before": before_count,
            "cache_count_after": count_cached_census_data(db),
        }
```
            return None
```

### 6.2 NBN Co Adapter (`national/nbnco.py`)

**Status:** DECOMMISSIONED for MVP (Feb 28, 2026). The experimental GNAF→NBN local-mapping pipeline was removed to avoid blocking the release; the adapter currently falls back to the legacy suggest/details flow. See `NBN_API_FIX.md` for investigation notes and re-enable instructions.

**API (legacy):** Unofficial NBN Co places API v2 (reverse-engineered)
**Base URL:** `https://places.nbnco.net.au/places/v2`
**Authentication:** Requires `Referer: https://www.nbnco.com.au/` header

**Two-step flow (current behavior):**
1. **POST `/suggest`** with address string → resolves to NBN Location ID (`LOC000xxxxxxxx`)
2. **GET `/details/{locId}`** → retrieves tech type and service status

**Note:** The `/suggest` endpoint is fragile (404s / reCAPTCHA). We removed the large data import & migration for now to avoid blocking deployment. If you want to re-enable the robust local mapping approach, follow the steps in `NBN_API_FIX.md`.
- Size: ~15M premises across Australia
- Update frequency: Quarterly (user can refresh manually)

**Code**:
```python
class NbnCoAdapter(BaseAdapter):
    """Checks NBN connectivity type for a given address.
    
    Priority:
    1. Check nbn_locations table by GNAF PID (fast, local)
    2. Fall back to suggest API (slow, for addresses without GNAF mapping)
    3. Direct locId if already provided in job['nbn_loc_id']
    """

    NBN_BASE = "https://places.nbnco.net.au/places/v2"

    def scrape(self, job: dict) -> dict:
        loc_id = job.get("nbn_loc_id") or self._resolve_loc_id(job)
        if not loc_id:
            return {"nbn": None}
        return self._fetch_details(loc_id)

    def _resolve_loc_id(self, job: dict) -> str | None:
        """Resolve address to NBN Location ID (database → fallback API).
        
        1. Use legacy `/suggest` endpoint with address or GNAF fallback
        """
        query = job.get("address_string") or job.get("gnaf_pid")
        if not query:
            return None
        
        logger.debug("Using NBN suggest for query=%r", query)
        data = self.fetch_json(
            f"{self.NBN_BASE}/suggest",
            method="POST",
            json_body={"query": query},
            headers={"Referer": "https://www.nbnco.com.au/"},
        )
        suggestions = data.get("suggestions", [])
        return suggestions[0].get("id") if suggestions else None

    def _fetch_details(self, loc_id: str) -> dict:
        """Fetch NBN tech type and service details."""
        data = self.fetch_json(
            f"{self.NBN_BASE}/details/{loc_id}",
            headers={"Referer": "https://www.nbnco.com.au/"},
        )
        
        address_detail = data.get("addressDetail", {})
        
        return {
            "nbn": {
                "loc_id": loc_id,
                "tech_type": address_detail.get("techType"),           # "FTTP", "HFC", "FTTN"
                "service_type": address_detail.get("serviceType"),     # "Fixed line", "Wireless"
                "service_status": address_detail.get("serviceStatus"), # "available", "in_construction"
                "tech_change_status": address_detail.get("techChangeStatus"),         # "Eligible To Order"
                "target_eligibility_quarter": address_detail.get("targetEligibilityQuarter"),  # "Q3 2025"
                "formatted_address": address_detail.get("formattedAddress"),
            },
            "data_sources": [{
                "name": "NBN Co Places API v2 (unofficial)",
                "url": "https://places.nbnco.net.au/places/v2/",
                "fetched_at": datetime.now(UTC).isoformat(),
            }],
        }
```

**Note**: This is an unofficial, undocumented API that may break without notice.

---

## 7. State-Level Adapters

### 7.1 VIC — VicPlan Adapter (`state/vic_plan.py`)

**API**: Vicmap Planning ArcGIS FeatureServer (officially published on data.vic.gov.au)  
**Base URL**: `https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/ArcGIS/rest/services/Vicmap_Planning/FeatureServer`  
**Coverage**: All Victorian LGAs — no council-level config required

**Layers used**:
- **Layer 3**: Planning scheme zones (`PLAN_ZONE`) → zone code, status, LGA name
- **Layer 2**: Planning scheme overlays (`PLAN_OVERLAY`) → overlay codes
- **Layer 9**: Bushfire Prone Areas (`BUSHFIRE_PRONE_AREA`) → dedicated bushfire risk layer

```python
class VicPlanAdapter(BaseAdapter):
    """
    Fetches zoning and overlay data from the Vicmap Planning ArcGIS FeatureServer.
    Covers all Victorian LGAs — no council-level config required.
    """

    def scrape(self, job: dict) -> dict:
        lat, lng = job["latitude"], job["longitude"]

        # Build ArcGIS spatial query parameters
        def _query(out_fields: str) -> str:
            return urlencode({
                "geometry": f"{lng},{lat}",
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",  # WGS84
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": out_fields,
                "returnGeometry": "false",
                "f": "json",
            })

        # Query three layers
        zone_data = self.fetch_json(f"{_ARCGIS_BASE}/{_LAYER_ZONES}/query?{_query('ZONE_CODE,ZONE_STATUS,LGA_NAME')}")
        overlay_data = self.fetch_json(f"{_ARCGIS_BASE}/{_LAYER_OVERLAYS}/query?{_query('SCHEME_CODE')}")
        bushfire_data = self.fetch_json(f"{_ARCGIS_BASE}/{_LAYER_BUSHFIRE}/query?{_query('OBJECTID')}")

        zone_feature = self._first_feature(zone_data)
        overlay_features = self._all_features(overlay_data)
        in_bushfire_prone = bool(self._all_features(bushfire_data))

        overlays = []
        for feature in overlay_features:
            code = feature.get("ZONE_CODE")
            if not code:
                continue
            overlays.append({
                "code": code,
                "description": feature.get("ZONE_DESCRIPTION"),
                "family": "other",  # resolved via overlay KB in real implementation
            })

        overlay_codes = [o["code"] for o in overlays]

        return {
            "zoning_code": zone_feature.get("ZONE_CODE") if zone_feature else None,
            "zoning_status": zone_feature.get("ZONE_STATUS") if zone_feature else None,
            "lga_name": zone_feature.get("LGA") if zone_feature else None,
            "overlays": overlays,
            "overlay_codes": overlay_codes,
            "flood_risk": self._classify_flood(overlay_codes),
            "bushfire_risk": self._classify_bushfire(overlay_codes, in_bushfire_prone),
            "heritage_overlay": any(code.startswith("HO") for code in overlay_codes),
            "constraint_score": self._constraint_score(overlays, in_bushfire_prone),
            "requires_planning_permit": self._requires_planning_permit(
                zone_feature.get("ZONE_CODE") if zone_feature else None,
                overlays,
            ),
            "data_sources": [{
                "name": "Vicmap Planning (data.vic.gov.au)",
                "url": _ARCGIS_BASE,
                "fetched_at": datetime.now(UTC).isoformat(),
            }],
        }

    def _classify_flood(self, overlay_codes: list[str]) -> str:
        codes_upper = {code.upper() for code in overlay_codes}
        if any(code.startswith("FO") or code.startswith("RFO") for code in codes_upper):
            return "HIGH"
        if any(code.startswith("LSIO") for code in codes_upper):
            return "MEDIUM"
        if any(code.startswith("SBO") for code in codes_upper):
            return "LOW"
        return "NONE"
```

**Note**: Flood risk is inferred from overlay codes; bushfire risk is derived from both overlay codes (`BMO`/`BAO`) and dedicated Layer 9 prone-area intersections (`LOW` when prone area only).

**Old API** (defunct): `https://api.planning.vic.gov.au/planning/v1`

### 7.2 NSW and Other States — Generic State Adapter (`state/generic_state.py`)

NSW is now intentionally routed through the generic state adapter (same as QLD/SA/WA/TAS/ACT/NT).
There is no dedicated NSW state adapter module in the current implementation.

```python
class GenericStateAdapter(BaseAdapter):
    """Placeholder for states without a dedicated implementation."""

    def scrape(self, job: dict) -> dict:
        logger.warning(
            "No state planning adapter for %s. Returning null planning data for %s",
            job.get("state", "UNKNOWN"),
            job.get("address_string", ""),
        )
        return {
            # VicPlan-compatible shape (strict contract)
            "zoning_code": None,
            "zoning_label": None,
            "zoning_status": None,
            "zoning_scheme": None,
            "zone_num": None,
            "gazetted_date": None,
            "lga_name": None,
            "lga_code": None,
            "overlays": [],
            "overlay_codes": [],
            "overlay_groups": {},
            "flood_risk": None,
            "bushfire_risk": None,
            "heritage_overlay": None,
            "has_design_overlay": None,
            "has_vegetation_overlay": None,
            "has_environment_overlay": None,
            "public_acquisition": None,
            "airport_corridor": None,
            "development_contributions": None,
            "development_plan_required": None,
            "incorporated_plan_applies": None,
            "contamination_audit_required": None,
            "constraint_score": None,
            "requires_planning_permit": None,
            "constraint_summary": None,
            "data_sources": [{"name": "Generic state planning adapter (no implementation)", "url": None}],
        }
```

### 7.3 State Adapter Contract

All state adapters must emit the same normalized schema:
- `overlays`: `list[dict]` enriched overlay objects (must include `code`)
- `overlay_codes`: `list[str]` canonical flat overlay code list
- Common risk/constraint keys (including `constraint_score` and `requires_planning_permit`)

This avoids adapter-specific branching in downstream merge and LLM steps.

---

## 8. Council-Level Adapter (Headless Browser)

All council adapters inherit from `BaseBrowserAdapter`, which handles browser lifecycle, proxy configuration, robots.txt checking, and common utilities. Subclasses only implement portal-specific logic.

### Base Browser Adapter (`adapters/browser_base.py`)

Shared foundation for all Playwright-based council adapters:

```python
from app.adapters.base import BaseAdapter
from app.utils.robots import is_scraping_allowed
from app.services.proxy import get_proxy_config
from playwright.sync_api import sync_playwright

class BaseBrowserAdapter(BaseAdapter):
    """
    Manages Playwright lifecycle for council portal adapters.
    
    Handles:
    - robots.txt compliance checking
    - Playwright browser launch/cleanup
    - Proxy configuration
    - PDF extraction (up to 3 PDFs per scrape)
    - Failure screenshot capture to MinIO
    - Resource cleanup via finally blocks
    """
    
    def scrape(self, job: dict) -> dict:
        """Main entry point - handles all browser lifecycle."""
        
        # 1. Check robots.txt compliance before launching browser
        if not is_scraping_allowed(self.base_url, "/"):
            return self._empty_result()
        
        proxy_config = get_proxy_config()
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, proxy=proxy_config)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            
            try:
                # Subclass implements portal-specific logic
                return self._run_scrape(page, job)
            except Exception as e:
                # Capture screenshot for debugging
                await self._save_failure_screenshot(page, job)
                # Return empty result on error
                return self._empty_result()
            finally:
                context.close()
                browser.close()
    
    async def _run_scrape(self, page, job: dict) -> dict:
        """Override in subclass with portal-specific logic."""
        raise NotImplementedError
    
    async def _extract_pdf(self, url: str, property_id: str, page) -> str | None:
        """Extract text from up to 3 PDFs using browser session (preserves cookies)."""
        # Shared implementation handles session-aware PDF download/extraction
        pass
    
    async def _save_failure_screenshot(self, page, job: dict) -> None:
        """Capture full-page screenshot to MinIO for debugging."""
        pass
    
    @staticmethod
    def _empty_result() -> dict:
        """Normalized empty/error result."""
        return {
            "council_planning_applications_text": None,
            "council_meeting_minutes_text": None,
            "data_sources": []
        }
```

### TechnologyOne Adapter (`council/tech_one.py`)

Subclass that only implements portal-specific navigation and extraction:

```python
from app.adapters.browser_base import BaseBrowserAdapter

class TechOneCouncilAdapter(BaseBrowserAdapter):
    """
    Scrapes council planning applications from TechnologyOne portals.
    Used by: many VIC, NSW, and QLD councils.
    
    All browser lifecycle, PDF extraction, and resource cleanup handled by BaseBrowserAdapter.
    This subclass only implements TechOne-specific navigation.
    """
    
    async def _run_scrape(self, page, job: dict) -> dict:
        """TechOne-specific: navigate, fill form, extract results."""
        
        # Navigate to portal (base class handles robots.txt and lifecycle)
        await page.goto(
            self.base_url,
            wait_until="domcontentloaded",  # ← Not "networkidle" (flaky on SPAs)
            timeout=30_000
        )
        
        # Non-blocking crawl delay (respects Celery worker availability)
        await page.wait_for_timeout(3_000)
        
        # Verify search field exists before interaction (pre-flight check)
        search_selector = self.config.get("search_input_selector", "#AddressSearch")
        await page.wait_for_selector(search_selector, state="visible", timeout=10_000)
        
        # Fill and submit
        await page.fill(search_selector, job["address_string"])
        await page.keyboard.press("Enter")
        
        # Wait for results
        results_selector = self.config.get("results_selector", ".application-list")
        await page.wait_for_selector(results_selector, timeout=15_000)
        
        # Extract planning text using parameterized selector (no f-string injection)
        planning_text = await page.evaluate(
            """
            (selector) => {
                const el = document.querySelector(selector);
                return el ? el.innerText : null;
            }
            """,
            results_selector  # ← Pass as parameter, never interpolate!
        )
        
        # Extract PDFs (inherited method handles up to 3 PDFs with session cookies)
        pdf_links = await page.evaluate_all(
            "document.querySelectorAll('a[href$=\".pdf\"]')",
            "els => els.map(e => e.href)"
        )
        minutes_text = None
        if pdf_links:
            minutes_text = await self._extract_pdf(
                pdf_links[0],
                job["property_id"],
                page  # ← Preserves browser session for auth-required PDFs
            )
        
        return {
            "council_planning_applications_text": planning_text,
            "council_meeting_minutes_text": minutes_text,
            "data_sources": [{
                "name": f"{job['lga_name']} Planning Portal",
                "url": self.base_url,
                "fetched_at": datetime.utcnow().isoformat(),
            }],
        }
```

### Objective Adapter (`council/objective.py`)

Similar pattern - inherits from `BaseBrowserAdapter`, implements only Objective-specific logic:

```python
from app.adapters.browser_base import BaseBrowserAdapter

class ObjectiveCouncilAdapter(BaseBrowserAdapter):
    """
    Scrapes planning data from Objective ECM / Pathway portals.
    Used by: VIC councils using Objective planning software.
    """
    
    async def _run_scrape(self, page, job: dict) -> dict:
        """Objective-specific navigation (resources/cleanup/PDFs handled in base)."""
        # Portal-specific form filling and extraction
        # Browser lifecycle, PDF extraction, screenshots all automatic
        pass
```

### Key Improvements Over Old Pattern

| Aspect | Old (Direct BaseAdapter) | New (BaseBrowserAdapter) |
|--------|--------------------------|--------------------------|
| Browser lifecycle | Manual in each adapter | Shared in base class |
| robots.txt checking | Duplicated in each adapter | Once in base class |
| PDF extraction | Duplicated code | Shared `_extract_pdf()` |
| Navigation pattern | `wait_until="networkidle"` (flaky) | `wait_until="domcontentloaded"` + explicit wait |
| Rate limiting | `time.sleep()` (blocking worker) | `page.wait_for_timeout()` (non-blocking) |
| Error handling | Silent `_adapter_error` | Descriptive errors + screenshots |
| Code duplication | ~90% between adapters | ~0% (shared base class) |
| Lines per adapter | 195+ | ~88 |

For detailed architecture and examples, see: [services/scraper-worker/BROWSER_ADAPTER_GUIDE.md](../services/scraper-worker/BROWSER_ADAPTER_GUIDE.md)

---

## 9. Adapter Registry (`app/adapters/registry.py`)

```python
from app.adapters.base import BaseAdapter
from app.adapters.national.abs_census import AbsCensusAdapter
from app.adapters.national.nbnco import NbnCoAdapter
from app.adapters.state.vic_plan import VicPlanAdapter
from app.adapters.state.generic_state import GenericStateAdapter
from app.adapters.council.tech_one import TechOneCouncilAdapter
from app.adapters.council.objective import ObjectiveCouncilAdapter
from app.adapters.council.generic_html import GenericHtmlCouncilAdapter

STATE_ADAPTER_MAP: dict[str, type[BaseAdapter]] = {
    "VIC": VicPlanAdapter,
    "NSW": GenericStateAdapter,
    "QLD": GenericStateAdapter,
    "SA":  GenericStateAdapter,
    "WA":  GenericStateAdapter,
    "TAS": GenericStateAdapter,
    "ACT": GenericStateAdapter,
    "NT":  GenericStateAdapter,
}

COUNCIL_ADAPTER_MAP: dict[str, type[BaseAdapter]] = {
    "TechOne_Council":    TechOneCouncilAdapter,
    "Objective_Council":  ObjectiveCouncilAdapter,
    "GenericHtml_Council": GenericHtmlCouncilAdapter,
}

# National adapters always run for every property
NATIONAL_ADAPTERS: list[type[BaseAdapter]] = [AbsCensusAdapter, NbnCoAdapter]
```

---

## 10. Parallel Adapter Execution

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_adapters_parallel(job: dict, council_config: dict | None, state: str) -> list[dict]:
    """
    Runs national + state + council adapters concurrently.
    Failed adapters are logged but don't block the scrape.
    """
    tasks = []

    # National adapters (always run)
    for AdapterClass in NATIONAL_ADAPTERS:
        tasks.append(("national", AdapterClass, {}))

    # State adapter
    StateAdapter = STATE_ADAPTER_MAP.get(state, GenericStateAdapter)
    tasks.append(("state", StateAdapter, {}))

    # Council adapter (only if configured for this LGA)
    if council_config:
        CouncilAdapter = COUNCIL_ADAPTER_MAP.get(council_config["adapter_name"])
        if CouncilAdapter:
            tasks.append(("council", CouncilAdapter, council_config))

    results = []
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {
            executor.submit(AdapterClass(base_url or "", cfg).scrape, job): name
            for name, AdapterClass, cfg in tasks
            for base_url in [cfg.get("base_url", "")]
        }
        for future in as_completed(futures):
            adapter_name = futures[future]
            try:
                results.append(future.result())
            except Exception as e:
                logger.warning(f"Adapter {adapter_name} failed: {e}. Continuing.")
                results.append({})  # empty partial — won't block LLM

    return results
```

**Merge Contract (current):**
- `merge_adapter_results` treats `overlays` as `list[dict]` and ignores legacy string entries.
- `overlay_codes` is merged separately and canonicalized from both partial `overlay_codes` and `overlays[*].code`.
- This strict contract prevents mixed overlay shapes from propagating into `raw_scraped_data` and LLM prompts.

---

## 11. Error Handling Reference

| Scenario | Behaviour |
|---|---|
| State API returns 5xx | `retry_with_backoff` (3 attempts, exp. backoff). If all fail, field = null, continue with available data. |
| Council site returns 403 | Rotate proxy, retry once. If still blocked, log `ADAPTER_BLOCKED`, continue without council data. |
| Playwright selector not found | `TimeoutError` caught, logs `SELECTOR_BROKEN:{lga_name}` — fires alert to admin DLQ. Report continues with state data only. |
| robots.txt disallows path | Skip council scrape entirely, log `ROBOTS_DISALLOWED`. Never violate. |
| PDF download fails | Non-fatal. `council_meeting_minutes_text = null`. LLM processes available data. |
| All adapters fail | Report status → `FAILED`. Task moves to dead letter queue. Admin alerted. |

---

## 12. Dockerfile

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy AS base
WORKDIR /app
RUN pip install uv

FROM base AS builder
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM base AS runner
COPY --from=builder /app/.venv ./.venv
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
# Celery worker — concurrency controlled by WORKER_CONCURRENCY env var
CMD ["celery", "-A", "app.celery_app", "worker",
     "--queues", "data_acquisition_queue",
     "--concurrency", "${WORKER_CONCURRENCY:-3}",
     "--loglevel", "info"]
```

> Use the official Microsoft Playwright Python Docker image — it bundles all Chromium system dependencies. Do NOT use `python:alpine` for this service.
