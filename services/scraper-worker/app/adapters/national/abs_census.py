"""ABS Regional Data adapter — LGA-level demographics from the ABS DataAPI.

Covers all Australian states — single national adapter.
Uses SDMX-JSON format from the ABS Data REST API.

Data is cached in the database after first fetch per LGA.
Can be refreshed via Admin action.

API base: https://data.api.abs.gov.au
Docs:     https://www.abs.gov.au/about/data-services/application-programming-interfaces-apis/data-api-user-guide

=== DATAFLOW: ABS_REGIONAL_LGA2021 ===

This adapter uses the "Data by Region" (DBR) dataflow which provides richer,
more up-to-date, and time-series data compared to the Census 2021 SA2 dataflows.

  Dataflow: ABS,ABS_REGIONAL_LGA2021,1.5.0
  Geography: LGA 2021 boundaries
  Frequency: Annual (some measures multi-year, some single-year)
  Coverage:  Population, Economy/Business, Building, Housing, Migration,
             Income/Pensions, Education, Environment

URL format:
    /rest/data/ABS,ABS_REGIONAL_LGA2021,1.5.0/..{lgaCode}.A
    ?dimensionAtObservation=AllDimensions&format=jsondata

NOTE: startPeriod is intentionally omitted so we retrieve all available
years, enabling LLMs to detect trends. Years with no data for a given
measure are silently skipped.

=== OBSERVATION KEY STRUCTURE ===

Obs keys are colon-separated positional indices into each dimension's values list:
    {measureIdx}:{regionTypeIdx}:{lgaIdx}:{freqIdx}:{timePeriodIdx}

Dimensions (keyPositions from structure metadata):
    0 - MEASURE      (data item / metric)
    1 - REGIONTYPE   (e.g. "LGA2021")
    2 - LGA_2021     (LGA code, e.g. "10050" for Albury)
    3 - FREQUENCY    (always "A" = Annual)
    4 - TIME_PERIOD  (e.g. "2023", "2024")

=== INVESTOR-RELEVANT MEASURES EXTRACTED ===

Population & Demographics:
  ERP_P_20  - Total persons (no.)
  ERP_21    - Population density (persons/km²)
  ERP_23    - Median age: Persons (years)
  BD_2      - Registered births (no.)
  BD_3      - Total fertility rate
  BD_5      - Standardised death rate (per 1,000)
  MIGRATION_2 - Internal migration arrivals (no.)
  MIGRATION_3 - Internal migration departures (no.)
  MIGRATION_4 - Net internal migration (no.)
  MIGRATION_5 - Overseas migration arrivals (no.)
  MIGRATION_7 - Net overseas migration (no.)

Economy & Business:
  CABEE_5   - Total businesses (no.)
  CABEE_10  - Total business entries (no.)
  CABEE_15  - Total business exits (no.)

Housing & Building:
  HOUSES_2  - Number of established house transfers (no.)
  HOUSES_3  - Median price of established house transfers ($)
  HOUSES_4  - Number of attached dwelling transfers (no.)
  HOUSES_5  - Median price of attached dwelling transfers ($)
  BUILDING_4 - Total dwelling units approved (no.)
  BUILDING_2 - Private sector houses approved (no.)
  BUILDING_10 - Total value of building approvals ($m)

Income & Welfare:
  PENSION_3 - DVA age pension recipients (no.)
  PENSION_4 - DVA service pension recipients (no.)

Education:
  PRESCH_8  - Children enrolled in preschool (no.)

Solar/Environment:
  SOLAR_7   - Solar panel installations (no.)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime

from app.adapters.base import BaseAdapter
from app.services.abs_census_db import (
    get_regional_data_from_db,
    store_regional_data_to_db,
)
from app.services.db import get_db_connection

logger = logging.getLogger(__name__)

ABS_BASE = "https://data.api.abs.gov.au"

# Dataflow identifier
DATAFLOW_ID      = "ABS_REGIONAL_LGA2021"
DATAFLOW_VERSION = "1.5.0"
DATAFLOW_AGENCY  = "ABS"

# REGIONTYPE filter value for LGA 2021 boundaries
REGION_TYPE_LGA = "LGA2021"

# ── Investor-relevant measures ──────────────────────────────────────────────
# Maps measure code → human-readable label used in the output dict.
# Grouped here for clarity; only these are extracted from the (large) response.
INVESTOR_MEASURES: dict[str, str] = {
    # Population & demographics
    "ERP_P_20":   "total_population",
    "ERP_21":     "population_density_per_sqkm",
    "ERP_23":     "median_age_persons_years",
    "BD_2":       "registered_births",
    "BD_3":       "total_fertility_rate",
    "BD_5":       "standardised_death_rate_per_1000",
    "MIGRATION_2": "internal_migration_arrivals",
    "MIGRATION_3": "internal_migration_departures",
    "MIGRATION_4": "net_internal_migration",
    "MIGRATION_5": "overseas_migration_arrivals",
    "MIGRATION_7": "net_overseas_migration",
    # Economy & business
    "CABEE_5":    "total_businesses",
    "CABEE_10":   "total_business_entries",
    "CABEE_15":   "total_business_exits",
    # Housing & building
    "HOUSES_2":   "established_house_transfers_count",
    "HOUSES_3":   "established_house_median_price_aud",
    "HOUSES_4":   "attached_dwelling_transfers_count",
    "HOUSES_5":   "attached_dwelling_median_price_aud",
    "BUILDING_4": "total_dwelling_approvals",
    "BUILDING_2": "private_house_approvals",
    "BUILDING_10": "total_building_approvals_value_aud_millions",
    # Income & welfare
    "PENSION_3":  "dva_age_pension_recipients",
    "PENSION_4":  "dva_service_pension_recipients",
    # Education
    "PRESCH_8":   "children_enrolled_preschool",
    # Environment
    "SOLAR_7":    "solar_panel_installations",
}

# Reverse lookup: label → measure code (for reference, not used in hot path)
_LABEL_TO_CODE = {v: k for k, v in INVESTOR_MEASURES.items()}


class AbsCensusAdapter(BaseAdapter):
    """Fetches LGA-level demographic & economic data from the ABS DataAPI.

    Uses the 'Data by Region' (DBR) dataflow ABS_REGIONAL_LGA2021 which
    provides annual time-series data across population, economy, housing,
    building, migration, and other indicators.

    Returns a structured demographics dict keyed by year so that downstream
    LLMs can identify trends and patterns across the time series.
    """

    def scrape(self, job: dict) -> dict:
        lga_code = self._resolve_lga(job["latitude"], job["longitude"])
        if not lga_code:
            logger.warning(
                "Could not resolve ABS LGA region for lat=%s lng=%s",
                job["latitude"], job["longitude"],
            )
            return {"demographics": None}

        try:
            force_refresh = job.get("mode") == "FORCE_ALL" or job.get("force") is True
            db = get_db_connection()

            if not force_refresh:
                cached = get_regional_data_from_db(db, lga_code)
                if cached:
                    enriched = cached.get("enriched_demographics") or {}

                    if _has_usable_cached_demographics(enriched):
                        logger.debug("Cache hit for LGA %s", lga_code)
                        db.close()

                        return {
                            "demographics": {
                                **enriched,
                                "lga_code": lga_code,
                                "source": "ABS Data by Region (cached)",
                                "cached_at": cached.get("cached_at"),
                            },
                            "data_sources": [
                                {
                                    "name": "ABS Database Cache",
                                    "cached_at": cached.get("cached_at"),
                                }
                            ],
                        }

                    logger.warning(
                        "Ignoring malformed ABS cache row for LGA %s; refreshing from API",
                        lga_code,
                    )

            logger.debug("Fetching DBR data for LGA %s from ABS API", lga_code)
            raw = self._fetch_lga_data(lga_code)
            demographics = self._parse_demographics(raw, lga_code)

            store_regional_data_to_db(
                db,
                region_code=lga_code,
                region_name=demographics.get("lga_name"),
                region_type=REGION_TYPE_LGA,
                raw_data={"regional": raw, "enriched_demographics": demographics},
            )
            db.close()

            return {
                "demographics": {
                    **demographics,
                    "source": "ABS Data by Region (newly cached)",
                },
                "data_sources": [
                    {
                        "name": "ABS DataAPI — Data by Region",
                        "dataflow": f"{DATAFLOW_AGENCY},{DATAFLOW_ID},{DATAFLOW_VERSION}",
                        "url": self._build_url(lga_code),
                        "fetched_at": datetime.now(UTC).isoformat(),
                    }
                ],
            }

        except Exception:
            logger.exception("ABS Regional adapter failed for LGA %s", lga_code)
            return {"demographics": None}

    # ── URL construction ─────────────────────────────────────────────────────

    def _build_url(self, lga_code: str) -> str:
        """Build the ABS DataAPI URL for a single LGA, all years."""
        # Dimension slots: MEASURE  REGIONTYPE  LGA_2021  FREQUENCY  TIME_PERIOD
        # Empty slots = all values; LGA slot and REGIONTYPE slot are pinned.
        # Slot order matches keyPosition from the datastructure.
        # Key: ..{lgaCode}.A  (REGIONTYPE omitted here — filtered in post-processing
        #                       to avoid inflating response with state/national rows)
        # Note: REGIONTYPE=LGA2021 is enforced in _parse_demographics by checking
        # the obs dimension values, not in the URL key, because the API will
        # still return sub-rows for parent geographies unless we pin it.
        # Pinning it: .<REGIONTYPE_IDX>.{lgaCode}.A  requires knowing the
        # index of "LGA2021" in the REGIONTYPE dimension at query time.
        # Simpler approach: pin in URL using the known static structure.
        #   Slot 0 (MEASURE):      empty → all
        #   Slot 1 (REGIONTYPE):   LGA2021 (code, not index — ABS accepts code values in key)
        #   Slot 2 (LGA_2021):     lga_code
        #   Slot 3 (FREQUENCY):    A
        #   Slot 4 (TIME_PERIOD):  empty → all years
        data_key = f".{REGION_TYPE_LGA}.{lga_code}.A."
        return (
            f"{ABS_BASE}/rest/data/"
            f"{DATAFLOW_AGENCY},{DATAFLOW_ID},{DATAFLOW_VERSION}"
            f"/{data_key}"
            f"?dimensionAtObservation=AllDimensions"
            f"&format=jsondata"
        )

    def _fetch_lga_data(self, lga_code: str) -> dict:
        """Fetch all available years of DBR data for a single LGA."""
        url = self._build_url(lga_code)
        logger.debug("ABS DBR fetch: %s", url)
        return self.fetch_json(url)

    # ── LGA resolution ───────────────────────────────────────────────────────

    def _resolve_lga(self, lat: float, lng: float) -> str | None:
        """Resolve lat/lng to an LGA_CODE_2021 via the ABS ASGS ArcGIS service."""
        try:
            url = (
                "https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/LGA/MapServer/0/query"
                f"?geometry={lng},{lat}"
                "&geometryType=esriGeometryPoint"
                "&inSR=4326"
                "&spatialRel=esriSpatialRelIntersects"
                "&outFields=LGA_CODE_2021"
                "&returnGeometry=false"
                "&f=json"
            )
            data = self.fetch_json(url)
            features = data.get("features", [])
            if features:
                attrs = {k.lower(): v for k, v in features[0].get("attributes", {}).items()}
                code = attrs.get("lga_code_2021")
                if code:
                    return str(int(code))  # normalise: strip float decimals if present
            logger.debug("No LGA feature found for lat=%s lng=%s", lat, lng)
            return None
        except Exception as exc:
            logger.debug("LGA resolution failed: %s", exc)
            return None

    # ── Response parsing ─────────────────────────────────────────────────────

    @staticmethod
    def _get_observations(data: dict) -> dict:
        """Extract observations dict from an SDMX-JSON data response."""
        try:
            return data["data"]["dataSets"][0]["observations"]
        except (KeyError, IndexError, TypeError):
            try:
                return data["dataSets"][0]["observations"]
            except (KeyError, IndexError, TypeError):
                return {}

    @staticmethod
    def _get_response_dimensions(data: dict) -> list[dict]:
        """Extract dimension metadata list from an SDMX-JSON data response."""
        try:
            # Try modern ABS API format: data.structures[0].dimensions.observation
            return data["data"]["structures"][0]["dimensions"]["observation"]
        except (KeyError, IndexError, TypeError):
            try:
                # Try older format: data.structure.dimensions.observation
                return data["data"]["structure"]["dimensions"]["observation"]
            except (KeyError, TypeError):
                try:
                    # Try format without nested data: structure.dimensions.observation
                    return data["structure"]["dimensions"]["observation"]
                except (KeyError, TypeError):
                    return []

    def _build_dimension_lookups(
        self, data: dict
    ) -> tuple[dict[str, int], dict[str, list[str]]]:
        """Build two lookup structures from the response dimensions.

        Returns:
            dim_positions:  {dimension_id_upper → index_in_obs_key}
            dim_code_lists: {dimension_id_upper → [code_at_index_0, code_at_index_1, ...]}
        """
        dims = self._get_response_dimensions(data)
        dim_positions: dict[str, int] = {}
        dim_code_lists: dict[str, list[str]] = {}

        for dim in dims:
            dim_id = dim.get("id", "").upper()
            dim_positions[dim_id] = dim.get("keyPosition", len(dim_positions))
            dim_code_lists[dim_id] = [
                v.get("id", "") for v in dim.get("values", [])
            ]

        return dim_positions, dim_code_lists

    def _parse_demographics(self, data: dict, lga_code: str) -> dict:
        """Parse the SDMX-JSON response into a structured demographics dict.

        Output structure:
        {
          "lga_code": "10050",
          "lga_name": "Albury",
          "time_series": {
            "2023": {
              "total_population": 57509,
              "established_house_median_price_aud": 555000,
              ...
            },
            "2024": { ... },
          },
          "latest_year": "2024",
          "latest": {
            "total_population": 58317,
            ...
          }
        }

        Only INVESTOR_MEASURES are extracted. Years with no data for a given
        measure are omitted for that measure (no nulls stored).
        """
        observations = self._get_observations(data)
        if not observations:
            logger.warning("No observations in DBR response for LGA %s", lga_code)
            return {"lga_code": lga_code, "time_series": {}, "latest_year": None, "latest": {}}

        dim_positions, dim_code_lists = self._build_dimension_lookups(data)

        measure_pos    = dim_positions.get("MEASURE", 0)
        time_pos       = dim_positions.get("TIME_PERIOD", 4)
        regiontype_pos = dim_positions.get("REGIONTYPE", 1)

        measure_codes  = dim_code_lists.get("MEASURE", [])
        time_codes     = dim_code_lists.get("TIME_PERIOD", [])
        regiontype_codes = dim_code_lists.get("REGIONTYPE", [])

        # Resolve LGA name from dimension metadata
        lga_dim_id = "LGA_2021"
        lga_names = {
            v.get("id", ""): v.get("name", "")
            for v in self._get_response_dimensions(data)
            if v.get("id", "").upper() == lga_dim_id
            # Flatten via the values list
            for v in v.get("values", [])  # type: ignore[assignment]
        }
        lga_name = lga_names.get(lga_code) or lga_names.get(lga_code.lstrip("0"), "")

        # time_series: year → {label: value}
        time_series: dict[str, dict[str, float | int]] = defaultdict(dict)

        for obs_key, obs_value in observations.items():
            if not obs_value or obs_value[0] is None:
                continue

            parts = obs_key.split(":")
            if len(parts) <= max(measure_pos, time_pos, regiontype_pos):
                continue

            # Filter: only LGA2021 region type rows (skip state/national totals)
            try:
                rt_idx = int(parts[regiontype_pos])
                if rt_idx < len(regiontype_codes) and regiontype_codes[rt_idx] != REGION_TYPE_LGA:
                    continue
            except (ValueError, IndexError):
                pass

            # Resolve measure code
            try:
                m_idx = int(parts[measure_pos])
                if m_idx >= len(measure_codes):
                    continue
                measure_code = measure_codes[m_idx]
            except (ValueError, IndexError):
                continue

            # Skip measures we don't care about (fast path)
            if measure_code not in INVESTOR_MEASURES:
                continue

            label = INVESTOR_MEASURES[measure_code]

            # Resolve year
            try:
                t_idx = int(parts[time_pos])
                if t_idx >= len(time_codes):
                    continue
                year = time_codes[t_idx]
            except (ValueError, IndexError):
                continue

            value = obs_value[0]
            # Sum in case there are multiple rows for the same measure+year
            # (e.g. multiple region sub-rows that slipped through the filter)
            existing = time_series[year].get(label)
            if existing is None:
                time_series[year][label] = value
            else:
                # Prefer the value already stored; duplicates shouldn't occur
                # after the REGIONTYPE filter but guard anyway
                logger.debug(
                    "Duplicate obs for LGA %s measure=%s year=%s — keeping first",
                    lga_code, label, year,
                )

        # Sort years chronologically
        sorted_years = sorted(time_series.keys())
        
        # Filter out years with insufficient data for investment analysis.
        # Require either total_population OR at least 5 meaningful metrics.
        # This excludes partial years (e.g., 2025 with only DVA pension data)
        # and early years with limited data coverage.
        filtered_years = [
            year for year in sorted_years
            if (
                "total_population" in time_series[year]  # Core metric present
                or len(time_series[year]) >= 8  # Or sufficient data points
            )
        ]
        
        latest_year = filtered_years[-1] if filtered_years else None

        # Compute derived growth metrics from the time series where possible
        time_series_final = {yr: time_series[yr] for yr in filtered_years}
        _add_growth_rates(time_series_final, filtered_years)

        return {
            "lga_code": lga_code,
            "lga_name": lga_name or None,
            "time_series": time_series_final,
            "latest_year": latest_year,
            "latest": time_series_final.get(latest_year, {}) if latest_year else {},
        }

# ── Derived metrics helpers ──────────────────────────────────────────────────

# Measures for which we compute year-on-year % growth in the time series.
_GROWTH_RATE_MEASURES: list[tuple[str, str]] = [
    ("total_population",                   "population_growth_pct_yoy"),
    ("established_house_median_price_aud", "house_price_growth_pct_yoy"),
    ("total_businesses",                   "business_count_growth_pct_yoy"),
    ("total_dwelling_approvals",           "dwelling_approvals_growth_pct_yoy"),
]


def _add_growth_rates(
    time_series: dict[str, dict[str, float | int]],
    sorted_years: list[str],
) -> None:
    """Mutates time_series in-place to add year-on-year growth rates.

    For each measure in _GROWTH_RATE_MEASURES, computes:
        growth_pct = (current - previous) / previous * 100
    and adds it to the current year's dict under the growth label.
    Years without a prior year or without data for both years are skipped.
    """


def _has_usable_cached_demographics(enriched: dict) -> bool:
    """Return True only when cached demographics include parsed ABS content."""
    if not isinstance(enriched, dict) or not enriched:
        return False

    latest = enriched.get("latest")
    time_series = enriched.get("time_series")
    return isinstance(latest, dict) and isinstance(time_series, dict) and bool(time_series)
    for i, year in enumerate(sorted_years):
        if i == 0:
            continue
        prev_year = sorted_years[i - 1]
        for measure_label, growth_label in _GROWTH_RATE_MEASURES:
            curr = time_series[year].get(measure_label)
            prev = time_series[prev_year].get(measure_label)
            if curr is not None and prev and prev != 0:
                growth = round((curr - prev) / prev * 100, 2)
                time_series[year][growth_label] = growth