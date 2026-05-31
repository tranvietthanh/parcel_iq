"""VicPlan adapter — zoning and overlay data from the Vicmap Planning ArcGIS FeatureServer.

Covers all Victorian LGAs — no council-level config required.

Data source: Vicmap Planning REST API (officially published on data.vic.gov.au)
  https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/ArcGIS/rest/services/Vicmap_Planning/FeatureServer

Layers used:
  Layer 3 — Planning scheme zones    (PLAN_ZONE)            → zone code + description
  Layer 2 — Planning scheme overlays (PLAN_OVERLAY)         → overlay codes
  Layer 9 — Bushfire Prone Areas     (BUSHFIRE_PRONE_AREA)  → bushfire risk

Enrichments:
  - Constraint severity score (0–10) weighted by overlay impact on development
  - Plain-English constraint summaries per overlay
  - requires_planning_permit flag derived from zone + overlays
  - Overlay family grouping (heritage, flood, environment, development, infrastructure, other)
  - PAO (Public Acquisition Overlay) hard flag — kills investment value
  - Airport corridor flags (AEO, MAEO)
  - Development contribution flags (DCPO, ICO)
  - Heritage register cross-reference hint for HO overlays
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import urlencode

from app.adapters.base import BaseAdapter
from app.config import settings
from app.services.db import get_db_connection
from app.services.vic_plan_db import get_cached_vic_plan_data, store_vic_plan_data

logger = logging.getLogger(__name__)

_ARCGIS_BASE = (
    "https://services-ap1.arcgis.com/P744lA0wf4LlBZ84"
    "/ArcGIS/rest/services/Vicmap_Planning/FeatureServer"
)

_LAYER_ZONES    = 3
_LAYER_OVERLAYS = 2
_LAYER_BUSHFIRE = 9

_ZONE_FIELDS    = "zone_code,zone_description,zone_status,zone_num,scheme_code,lga,lga_code,gaz_begin_date"
_OVERLAY_FIELDS = "zone_code,zone_description,zone_status,zone_num,scheme_code,lga,lga_code,gaz_begin_date"
_BUSHFIRE_FIELDS = "OBJECTID"


# ── Overlay knowledge base ─────────────────────────────────────────────────
#
# Each entry defines:
#   severity  : 1–10 contribution to the constraint score (10 = most restrictive)
#   family    : logical grouping for UI/reporting
#   permit    : True if this overlay typically triggers a planning permit requirement
#   summary   : plain-English one-liner shown to end users
#   detail    : fuller explanation of what the overlay means in practice
#   heritage_register : True if the overlay has a corresponding heritage register entry
#
# Codes are prefix-matched (e.g. "HO" matches "HO544", "HO12").

_OVERLAY_KB: dict[str, dict] = {
    # ── Public Acquisition ────────────────────────────────────────────────
    "PAO": {
        "severity": 10,
        "family": "acquisition",
        "permit": True,
        "summary": "Government intends to acquire this land in the future.",
        "detail": (
            "A Public Acquisition Overlay (PAO) means a public authority (council, VicRoads, "
            "utility, etc.) has reserved the right to purchase the land. Development is severely "
            "restricted and long-term investment value is undermined. Check the schedule to "
            "identify the acquiring authority and intended purpose."
        ),
        "heritage_register": False,
    },
    # ── Flood ─────────────────────────────────────────────────────────────
    "FO": {
        "severity": 9,
        "family": "flood",
        "permit": True,
        "summary": "High flood risk — land is within a designated floodway.",
        "detail": (
            "The Floodway Overlay (FO) identifies land that forms part of the flood conveyance "
            "system. Buildings and works are highly restricted to protect flood flow capacity. "
            "Most development requires a planning permit and referral to the relevant floodplain "
            "management authority."
        ),
        "heritage_register": False,
    },
    "RFO": {
        "severity": 9,
        "family": "flood",
        "permit": True,
        "summary": "High flood risk — land is within a rural floodway.",
        "detail": (
            "The Rural Floodway Overlay (RFO) functions similarly to the FO in rural areas, "
            "protecting the rural flood conveyance system. Residential development and subdivision "
            "are significantly constrained."
        ),
        "heritage_register": False,
    },
    "LSIO": {
        "severity": 7,
        "family": "flood",
        "permit": True,
        "summary": "Medium flood risk — land is subject to inundation.",
        "detail": (
            "The Land Subject to Inundation Overlay (LSIO) identifies land that may be inundated "
            "in a 1-in-100-year flood event. A planning permit is required for most buildings and "
            "works, and floor levels must typically be set above the flood level."
        ),
        "heritage_register": False,
    },
    "SBO": {
        "severity": 4,
        "family": "flood",
        "permit": True,
        "summary": "Low flood/drainage risk — Special Building Overlay applies.",
        "detail": (
            "The Special Building Overlay (SBO) identifies land subject to overland flooding from "
            "stormwater drainage systems. Floor levels must be set above the applicable flood level. "
            "A planning permit is required for buildings and works."
        ),
        "heritage_register": False,
    },
    # ── Heritage ──────────────────────────────────────────────────────────
    "HO": {
        "severity": 7,
        "family": "heritage",
        "permit": True,
        "summary": "Heritage Overlay — demolition, alterations, and subdivision require a permit.",
        "detail": (
            "The Heritage Overlay (HO) protects places of cultural heritage significance. "
            "A planning permit is required for demolition, external alterations, tree removal, "
            "and subdivision. The schedule number corresponds to a specific entry in the "
            "Victorian Heritage Register or local heritage study. Internal works to non-contributory "
            "buildings may be exempt — check the schedule."
        ),
        "heritage_register": True,
    },
    "NCO": {
        "severity": 4,
        "family": "heritage",
        "permit": True,
        "summary": "Neighbourhood Character Overlay — demolition and new development are regulated.",
        "detail": (
            "The Neighbourhood Character Overlay (NCO) protects the established character of "
            "residential areas. A planning permit is required for demolition and must demonstrate "
            "the proposal responds to the neighbourhood character objectives in the schedule."
        ),
        "heritage_register": False,
    },
    # ── Development controls ──────────────────────────────────────────────
    "DDO": {
        "severity": 5,
        "family": "development",
        "permit": True,
        "summary": "Design & Development Overlay — height, setback, and design controls apply.",
        "detail": (
            "The Design and Development Overlay (DDO) sets specific design requirements including "
            "height limits, setbacks, wall-to-boundary controls, and design objectives. A planning "
            "permit is required for buildings and works. The schedule contains the specific controls "
            "and should be consulted before any design work."
        ),
        "heritage_register": False,
    },
    "DPO": {
        "severity": 8,
        "family": "development",
        "permit": True,
        "summary": "Development Plan Overlay — an approved development plan is required before any permit.",
        "detail": (
            "The Development Plan Overlay (DPO) requires an overall development plan to be approved "
            "before individual planning permits can be issued. This is common in growth area "
            "precincts. Until a development plan is in place, subdivision and development are "
            "effectively frozen."
        ),
        "heritage_register": False,
    },
    "IPO": {
        "severity": 7,
        "family": "development",
        "permit": True,
        "summary": "Incorporated Plan Overlay — development must comply with an incorporated plan.",
        "detail": (
            "The Incorporated Plan Overlay (IPO) requires that use and development comply with "
            "an incorporated plan that forms part of the planning scheme. The incorporated plan "
            "must be obtained and reviewed before any development is contemplated."
        ),
        "heritage_register": False,
    },
    "SCO": {
        "severity": 6,
        "family": "development",
        "permit": True,
        "summary": "Specific Controls Overlay — bespoke planning controls apply to this site.",
        "detail": (
            "The Specific Controls Overlay (SCO) applies site-specific planning controls set out "
            "in a schedule. The controls vary widely — review the schedule to understand what "
            "is required."
        ),
        "heritage_register": False,
    },
    "BFO": {
        "severity": 5,
        "family": "development",
        "permit": True,
        "summary": "Built Form Overlay — built form and design standards apply.",
        "detail": (
            "The Built Form Overlay (BFO) sets mandatory and discretionary built form standards "
            "for an area, typically in activity centres. Height, setbacks, podium design, and "
            "active frontages are commonly regulated."
        ),
        "heritage_register": False,
    },
    # ── Infrastructure & Contributions ────────────────────────────────────
    "DCPO": {
        "severity": 3,
        "family": "infrastructure",
        "permit": False,
        "summary": "Development Contributions Plan Overlay — levies apply to subdivision and development.",
        "detail": (
            "The Development Contributions Plan Overlay (DCPO) requires developers to pay levies "
            "toward local infrastructure (roads, drainage, open space, community facilities). "
            "The levy amount is set in the schedule and is typically charged per lot or per square "
            "metre of floor area. This directly affects development feasibility."
        ),
        "heritage_register": False,
    },
    "ICO": {
        "severity": 3,
        "family": "infrastructure",
        "permit": False,
        "summary": "Infrastructure Contributions Overlay — state infrastructure levies apply.",
        "detail": (
            "The Infrastructure Contributions Overlay (ICO) applies state government infrastructure "
            "contribution requirements to development. Similar to DCPO but state-administered. "
            "Check the schedule for applicable rates."
        ),
        "heritage_register": False,
    },
    "PO": {
        "severity": 2,
        "family": "infrastructure",
        "permit": False,
        "summary": "Parking Overlay — car parking requirements are modified for this area.",
        "detail": (
            "The Parking Overlay (PO) modifies standard car parking requirements, typically "
            "reducing or removing minimum parking rates in areas well-served by public transport "
            "or in activity centres. Can benefit development feasibility for higher-density projects."
        ),
        "heritage_register": False,
    },
    # ── Environment ───────────────────────────────────────────────────────
    "ESO": {
        "severity": 6,
        "family": "environment",
        "permit": True,
        "summary": "Environmental Significance Overlay — vegetation and habitat protection applies.",
        "detail": (
            "The Environmental Significance Overlay (ESO) protects areas of environmental "
            "significance including native vegetation, habitat, waterways, and wetlands. "
            "A planning permit is required for vegetation removal and may be required for "
            "buildings and works depending on the schedule."
        ),
        "heritage_register": False,
    },
    "VPO": {
        "severity": 5,
        "family": "environment",
        "permit": True,
        "summary": "Vegetation Protection Overlay — significant trees and vegetation are protected.",
        "detail": (
            "The Vegetation Protection Overlay (VPO) protects significant trees and vegetation. "
            "A planning permit is required for vegetation removal, pruning, or any works within "
            "the root zone of protected trees."
        ),
        "heritage_register": False,
    },
    "EMO": {
        "severity": 5,
        "family": "environment",
        "permit": True,
        "summary": "Erosion Management Overlay — land is prone to erosion or landslip.",
        "detail": (
            "The Erosion Management Overlay (EMO) identifies land subject to erosion, landslip, "
            "or mass movement. A planning permit is required for buildings, works, and vegetation "
            "removal. Geotechnical assessment is typically required."
        ),
        "heritage_register": False,
    },
    "SLO": {
        "severity": 4,
        "family": "environment",
        "permit": True,
        "summary": "Significant Landscape Overlay — landscape character must be protected.",
        "detail": (
            "The Significant Landscape Overlay (SLO) protects areas of landscape significance "
            "such as ridgelines, waterways, and scenic corridors. Development must respect the "
            "landscape character objectives set out in the schedule."
        ),
        "heritage_register": False,
    },
    "SMO": {
        "severity": 4,
        "family": "environment",
        "permit": True,
        "summary": "Salinity Management Overlay — land affected by dryland salinity.",
        "detail": (
            "The Salinity Management Overlay (SMO) identifies land affected by dryland salinity "
            "or at risk of becoming saline. Development must manage vegetation and drainage to "
            "avoid exacerbating salinity."
        ),
        "heritage_register": False,
    },
    "EAO": {
        "severity": 6,
        "family": "environment",
        "permit": True,
        "summary": "Environmental Audit Overlay — a certificate of environmental audit may be required.",
        "detail": (
            "The Environmental Audit Overlay (EAO) identifies potentially contaminated land. "
            "Before a sensitive use (residential, childcare, school) can commence, an environmental "
            "audit statement or certificate is required from an EPA-appointed auditor. This adds "
            "cost and time to any residential development."
        ),
        "heritage_register": False,
    },
    # ── Bushfire ──────────────────────────────────────────────────────────
    "BMO": {
        "severity": 8,
        "family": "bushfire",
        "permit": True,
        "summary": "Bushfire Management Overlay — strict bushfire protection measures required.",
        "detail": (
            "The Bushfire Management Overlay (BMO) applies to land where the bushfire hazard "
            "requires specific management measures. A planning permit is required for most "
            "buildings and works, and development must meet Bushfire Attack Level (BAL) "
            "construction standards and defendable space requirements."
        ),
        "heritage_register": False,
    },
    "BAO": {
        "severity": 7,
        "family": "bushfire",
        "permit": True,
        "summary": "Bushfire Area Overlay — development must meet bushfire protection standards.",
        "detail": (
            "The Bushfire Area Overlay (BAO) applies in areas with a moderate to high bushfire "
            "hazard. A planning permit is required and development must demonstrate compliance "
            "with bushfire protection objectives."
        ),
        "heritage_register": False,
    },
    # ── Airport & Corridors ───────────────────────────────────────────────
    "MAEO": {
        "severity": 6,
        "family": "airport",
        "permit": True,
        "summary": "Melbourne Airport Environs Overlay — height and noise restrictions apply.",
        "detail": (
            "The Melbourne Airport Environs Overlay (MAEO) restricts building heights within "
            "flight paths and imposes noise attenuation requirements on new sensitive uses "
            "(residential, schools, hospitals). Check the schedule for the applicable noise "
            "exposure level and height restrictions."
        ),
        "heritage_register": False,
    },
    "AEO": {
        "severity": 5,
        "family": "airport",
        "permit": True,
        "summary": "Airport Environs Overlay — height and noise restrictions apply near a regional airport.",
        "detail": (
            "The Airport Environs Overlay (AEO) applies near regional airports and restricts "
            "building heights and sensitive uses within flight corridors and noise-affected areas."
        ),
        "heritage_register": False,
    },
    "CLPO": {
        "severity": 7,
        "family": "corridor",
        "permit": True,
        "summary": "CityLink Project Overlay — land is within the CityLink road corridor.",
        "detail": (
            "The CityLink Project Overlay (CLPO) identifies land within or adjacent to the "
            "CityLink freeway corridor. Development is tightly controlled and must not compromise "
            "the operation of the freeway infrastructure."
        ),
        "heritage_register": False,
    },
    "RXO": {
        "severity": 5,
        "family": "corridor",
        "permit": True,
        "summary": "Road Closure Overlay — a road closure affects this land.",
        "detail": (
            "The Road Closure Overlay (RXO) identifies land affected by a road closure. "
            "The land may be subject to specific use and development requirements."
        ),
        "heritage_register": False,
    },
    "SRO": {
        "severity": 5,
        "family": "corridor",
        "permit": True,
        "summary": "State Resource Overlay — land contains a state resource (e.g. mineral, extractive).",
        "detail": (
            "The State Resource Overlay (SRO) identifies land containing a state resource that "
            "must be protected from incompatible uses. Development that would sterilise or "
            "conflict with the resource is restricted."
        ),
        "heritage_register": False,
    },
    "RO": {
        "severity": 6,
        "family": "corridor",
        "permit": True,
        "summary": "Restructure Overlay — land identified for rural restructure.",
        "detail": (
            "The Restructure Overlay (RO) identifies rural land that has been fragmented into "
            "uneconomic lot sizes. The overlay facilitates consolidation and may restrict further "
            "subdivision or development until restructuring is completed."
        ),
        "heritage_register": False,
    },
    "PSB": {
        "severity": 4,
        "family": "corridor",
        "permit": False,
        "summary": "Protected Settlement Boundary — urban growth beyond this boundary is restricted.",
        "detail": (
            "The Protected Settlement Boundary (PSB) defines the limit of urban settlement in "
            "rural and regional areas. Development that would extend settlement beyond the boundary "
            "is strongly discouraged."
        ),
        "heritage_register": False,
    },
    # ── Specific / catch-all ──────────────────────────────────────────────
    "NCO": {
        "severity": 4,
        "family": "heritage",
        "permit": True,
        "summary": "Neighbourhood Character Overlay — demolition and new development are regulated.",
        "detail": (
            "The Neighbourhood Character Overlay (NCO) protects the established character of "
            "residential areas. A planning permit is required for demolition and new development "
            "must respond to the neighbourhood character objectives."
        ),
        "heritage_register": False,
    },
}

# Zone codes where a planning permit is NOT required for standard residential use
# (used as a baseline — overlays can re-impose permit requirements)
_PERMIT_EXEMPT_ZONES = {"GRZ", "NRZ", "TZ", "RGZ"}

# Zone codes that always require a permit for residential use
_PERMIT_REQUIRED_ZONES = {
    "CCZ", "CAZ", "MUZ", "B1Z", "B2Z", "B3Z", "B4Z", "B5Z",
    "C1Z", "C2Z", "IN1Z", "IN2Z", "IN3Z", "FZ", "RCZ", "LDRZ",
    "RLZ", "RAZ", "PPRZ", "PWAZ", "SUZ", "UGZ", "CDZ",
}


def _spatial_query_params(lat: float, lng: float, out_fields: str) -> str:
    """Build ArcGIS REST spatial query parameters for a lat/lng point."""
    return urlencode({
        "geometry":       f"{lng},{lat}",
        "geometryType":   "esriGeometryPoint",
        "inSR":           "4326",
        "spatialRel":     "esriSpatialRelIntersects",
        "outFields":      out_fields,
        "returnGeometry": "false",
        "f":              "json",
    })


def _lookup_overlay(code: str) -> dict:
    """Return knowledge-base entry for an overlay code by prefix match."""
    upper = code.upper()
    # Try longest prefix first so e.g. "LSIO" wins over "L"
    for prefix in sorted(_OVERLAY_KB.keys(), key=len, reverse=True):
        if upper.startswith(prefix):
            return _OVERLAY_KB[prefix]
    return {
        "severity": 2,
        "family": "other",
        "permit": False,
        "summary": f"Overlay {code} applies to this site.",
        "detail": (
            f"Overlay code {code} is present on this site. Consult the planning scheme "
            "for the relevant schedule and controls."
        ),
        "heritage_register": False,
    }


class VicPlanAdapter(BaseAdapter):
    """Fetches zoning, overlay, and enriched constraint data from Vicmap Planning."""

    def scrape(self, job: dict) -> dict:
        lat, lng = job["latitude"], job["longitude"]
        force_refresh = job.get("mode") == "FORCE_ALL" or job.get("force") is True
        db = None

        try:
            if not force_refresh:
                # Cache read is best-effort. Unit tests and local runs should
                # still work even when Postgres is unavailable.
                try:
                    db = get_db_connection()
                    cached = get_cached_vic_plan_data(db, lat, lng)
                    if cached:
                        logger.debug("VicPlan cache hit for lat=%s lng=%s", lat, lng)
                        return cached
                except Exception:
                    logger.warning(
                        "VicPlan cache read unavailable for lat=%s lng=%s; continuing without cache",
                        lat,
                        lng,
                    )
                    if db:
                        try:
                            db.close()
                        except Exception:
                            pass
                    db = None

            zone_data = self.fetch_json(
                f"{_ARCGIS_BASE}/{_LAYER_ZONES}/query?"
                f"{_spatial_query_params(lat, lng, _ZONE_FIELDS)}"
            )
            overlay_data = self.fetch_json(
                f"{_ARCGIS_BASE}/{_LAYER_OVERLAYS}/query?"
                f"{_spatial_query_params(lat, lng, _OVERLAY_FIELDS)}"
            )
            bushfire_data = self.fetch_json(
                f"{_ARCGIS_BASE}/{_LAYER_BUSHFIRE}/query?"
                f"{_spatial_query_params(lat, lng, _BUSHFIRE_FIELDS)}"
            )

            zone_feature      = self._first_feature(zone_data)
            overlay_features  = self._all_features(overlay_data)
            in_bushfire_prone = bool(self._all_features(bushfire_data))

            # ── Zone fields ───────────────────────────────────────────────
            zone_code         = zone_feature.get("zone_code")         if zone_feature else None
            zone_description  = zone_feature.get("zone_description")  if zone_feature else None
            zone_status       = zone_feature.get("zone_status")       if zone_feature else None
            zone_num          = zone_feature.get("zone_num")          if zone_feature else None
            scheme_code       = zone_feature.get("scheme_code")       if zone_feature else None
            lga_name          = zone_feature.get("lga")               if zone_feature else None
            lga_code          = zone_feature.get("lga_code")          if zone_feature else None
            gaz_raw           = zone_feature.get("gaz_begin_date")    if zone_feature else None
            gaz_begin_date    = (
                datetime.fromtimestamp(gaz_raw / 1000, tz=UTC).date().isoformat()
                if gaz_raw else None
            )

            # ── Overlay enrichment ────────────────────────────────────────
            overlays = []
            for f in overlay_features:
                code = f.get("zone_code", "")
                if not code:
                    continue
                kb = _lookup_overlay(code)
                gaz_o = f.get("gaz_begin_date")
                overlays.append({
                    # Raw API fields
                    "code":        code,
                    "description": f.get("zone_description"),
                    "scheme":      f.get("scheme_code"),
                    "schedule":    f.get("zone_num"),
                    "status":      f.get("zone_status"),
                    "gazetted":    (
                        datetime.fromtimestamp(gaz_o / 1000, tz=UTC).date().isoformat()
                        if gaz_o else None
                    ),
                    # Knowledge-base enrichment
                    "family":            kb["family"],
                    "severity":          kb["severity"],
                    "permit_trigger":    kb["permit"],
                    "summary":           kb["summary"],
                    "detail":            kb["detail"],
                    "heritage_register": kb["heritage_register"],
                    # Heritage register lookup hint
                    "heritage_register_url": (
                        f"https://www.heritage.vic.gov.au/heritage-register?search={code}"
                        if kb["heritage_register"] else None
                    ),
                })

            overlay_codes = [o["code"] for o in overlays]

            # ── Constraint score (0–10) ───────────────────────────────────
            constraint_score = self._constraint_score(overlays, in_bushfire_prone)

            # ── Grouped overlays ──────────────────────────────────────────
            overlay_groups = self._group_overlays(overlays)

            # ── Derived risk flags ────────────────────────────────────────
            flood_risk    = self._classify_flood(overlay_codes)
            bushfire_risk = self._classify_bushfire(overlay_codes, in_bushfire_prone)

            # ── Planning permit flag ───────────────────────────────────────
            requires_permit = self._requires_planning_permit(zone_code, overlays)

            # ── Hard flags ────────────────────────────────────────────────
            has_pao       = any(c.upper().startswith("PAO")  for c in overlay_codes)
            has_airport   = any(c.upper().startswith(("AEO", "MAEO")) for c in overlay_codes)
            has_dcpo_ico  = any(c.upper().startswith(("DCPO", "ICO")) for c in overlay_codes)
            has_dpo       = any(c.upper().startswith("DPO")  for c in overlay_codes)
            has_ipo       = any(c.upper().startswith("IPO")  for c in overlay_codes)
            has_eao       = any(c.upper().startswith("EAO")  for c in overlay_codes)

            # ── Plain-English constraint summary ──────────────────────────
            constraint_summary = self._build_constraint_summary(
                zone_code, zone_description, overlays,
                flood_risk, bushfire_risk, has_pao,
            )

            result = {
                # ── Zone ──────────────────────────────────────────────────
                "zoning_code":    zone_code,
                "zoning_label":   zone_description,
                "zoning_status":  zone_status,
                "zoning_scheme":  scheme_code,
                "zone_num":       zone_num,
                "gazetted_date":  gaz_begin_date,

                # ── LGA ───────────────────────────────────────────────────
                "lga_name": lga_name,
                "lga_code": lga_code,

                # ── Overlays ──────────────────────────────────────────────
                "overlays":       overlays,         # full enriched list
                "overlay_codes":  overlay_codes,    # flat list for quick lookups
                "overlay_groups": overlay_groups,   # grouped by family

                # ── Risk flags ────────────────────────────────────────────
                "flood_risk":             flood_risk,
                "bushfire_risk":          bushfire_risk,
                "heritage_overlay":       any(c.upper().startswith("HO")  for c in overlay_codes),
                "has_design_overlay":     any(c.upper().startswith("DDO") for c in overlay_codes),
                "has_vegetation_overlay": any(c.upper().startswith("VPO") for c in overlay_codes),
                "has_environment_overlay":any(c.upper().startswith("ESO") for c in overlay_codes),

                # ── Hard flags ────────────────────────────────────────────
                "public_acquisition":        has_pao,
                "airport_corridor":          has_airport,
                "development_contributions": has_dcpo_ico,
                "development_plan_required": has_dpo,
                "incorporated_plan_applies": has_ipo,
                "contamination_audit_required": has_eao,

                # ── Constraint score & permit ─────────────────────────────
                "constraint_score":       constraint_score,   # 0–10
                "requires_planning_permit": requires_permit,

                # ── Plain-English summary ─────────────────────────────────
                "constraint_summary": constraint_summary,

                "data_sources": [{
                    "name":       "Vicmap Planning FeatureServer (data.vic.gov.au)",
                    "url":        _ARCGIS_BASE,
                    "fetched_at": datetime.now(UTC).isoformat(),
                }],
            }

            # Cache write-through (best-effort, non-blocking)
            try:
                if db is None:
                    db = get_db_connection()
                store_vic_plan_data(
                    db,
                    lat=lat,
                    lng=lng,
                    raw_data=result,
                    ttl_hours=settings.VICPLAN_CACHE_TTL_HOURS,
                )
            except Exception:
                logger.exception("Failed to persist VicPlan cache for lat=%s lng=%s", lat, lng)

            return result

        except Exception:
            logger.exception("VicPlan adapter failed for lat=%s lng=%s", lat, lng)
            return {
                "zoning_code":   None,
                "zoning_label":  None,
                "zoning_status": None,
                "lga_name":      None,
                "overlays":      [],
                "overlay_codes": [],
                "overlay_groups":{},
                "flood_risk":    None,
                "bushfire_risk": None,
                "heritage_overlay":            None,
                "public_acquisition":          None,
                "constraint_score":            None,
                "requires_planning_permit":    None,
                "constraint_summary":          None,
            }
        finally:
            if db:
                try:
                    db.close()
                except Exception:
                    pass

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _normalise_attrs(attrs: dict) -> dict:
        """Lowercase all attribute keys for consistent access."""
        return {k.lower(): v for k, v in attrs.items()}

    def _first_feature(self, data: dict) -> dict | None:
        try:
            features = data.get("features", [])
            if features:
                return self._normalise_attrs(features[0].get("attributes", {}))
        except (AttributeError, IndexError, KeyError):
            pass
        return None

    def _all_features(self, data: dict) -> list[dict]:
        try:
            return [
                self._normalise_attrs(f.get("attributes", {}))
                for f in data.get("features", [])
            ]
        except (AttributeError, KeyError):
            return []

    @staticmethod
    def _classify_flood(overlay_codes: list[str]) -> str:
        codes_upper = {c.upper() for c in overlay_codes}
        if any(c.startswith("FO") or c.startswith("RFO") for c in codes_upper):
            return "HIGH"
        if any(c.startswith("LSIO") for c in codes_upper):
            return "MEDIUM"
        if any(c.startswith("SBO") for c in codes_upper):
            return "LOW"
        return "NONE"

    @staticmethod
    def _classify_bushfire(overlay_codes: list[str], in_prone_area: bool) -> str:
        codes_upper = {c.upper() for c in overlay_codes}
        if any(c.startswith("BMO") for c in codes_upper):
            return "HIGH"
        if any(c.startswith("BAO") for c in codes_upper):
            return "MEDIUM"
        if in_prone_area:
            return "LOW"
        return "NONE"

    @staticmethod
    def _group_overlays(overlays: list[dict]) -> dict[str, list[dict]]:
        """Group enriched overlay dicts by their family (heritage, flood, etc.)."""
        groups: dict[str, list[dict]] = {}
        for o in overlays:
            family = o.get("family", "other")
            groups.setdefault(family, []).append(o)
        return groups

    @staticmethod
    def _constraint_score(overlays: list[dict], in_bushfire_prone: bool) -> float:
        """
        Compute a 0–10 constraint severity score.

        Logic:
          - Sum severity scores from all overlays (capped per family to avoid
            double-counting e.g. multiple HO overlays on one parcel)
          - Add 2 if in bushfire prone area and no BMO/BAO already present
          - Normalise to 0–10 with a reasonable ceiling of 30 raw points = 10
        """
        # Take the max severity per family (not sum) to avoid inflation
        family_max: dict[str, int] = {}
        for o in overlays:
            family = o.get("family", "other")
            sev    = o.get("severity", 2)
            family_max[family] = max(family_max.get(family, 0), sev)

        raw = sum(family_max.values())

        # Add baseline bushfire contribution if only in prone area (no explicit overlay)
        has_bushfire_overlay = any(
            o.get("family") == "bushfire" for o in overlays
        )
        if in_bushfire_prone and not has_bushfire_overlay:
            raw += 2

        # Normalise: ceiling of 30 raw points maps to 10
        score = min(raw / 30 * 10, 10.0)
        return round(score, 1)

    @staticmethod
    def _requires_planning_permit(zone_code: str | None, overlays: list[dict]) -> bool:
        """
        Determine whether a planning permit is required.

        A permit is required if:
          - The zone itself requires a permit for standard use/development, OR
          - Any overlay triggers a permit requirement
        """
        if zone_code:
            # Strip schedule number to get base zone prefix (e.g. "GRZ1" → "GRZ")
            base_zone = "".join(c for c in zone_code if not c.isdigit()).rstrip("-")
            if base_zone in _PERMIT_REQUIRED_ZONES:
                return True
            # Even exempt zones require a permit if any overlay triggers one
        return any(o.get("permit_trigger") for o in overlays)

    @staticmethod
    def _build_constraint_summary(
        zone_code: str | None,
        zone_description: str | None,
        overlays: list[dict],
        flood_risk: str,
        bushfire_risk: str,
        has_pao: bool,
    ) -> list[str]:
        """
        Build a prioritised list of plain-English constraint sentences.

        Returns sentences ordered from most to least critical.
        """
        sentences: list[tuple[int, str]] = []  # (priority, sentence)

        # PAO is always first — it's the most critical flag
        if has_pao:
            sentences.append((0, (
                "⚠️  Public Acquisition Overlay: A government authority has reserved the right "
                "to acquire this land. Long-term development and investment value are severely affected."
            )))

        # Zone context
        if zone_code and zone_description:
            sentences.append((1, f"This site is zoned {zone_code} ({zone_description.title()})."))

        # Flood
        if flood_risk == "HIGH":
            sentences.append((2, (
                "Flood risk is HIGH — the site is within a designated floodway. "
                "Buildings and works are heavily restricted."
            )))
        elif flood_risk == "MEDIUM":
            sentences.append((3, (
                "Flood risk is MEDIUM — the site may be inundated in a 1-in-100-year event. "
                "Floor levels must be set above the applicable flood level."
            )))
        elif flood_risk == "LOW":
            sentences.append((4, (
                "A Special Building Overlay applies — overland drainage flooding may affect the site. "
                "Minimum floor levels are required."
            )))

        # Bushfire
        if bushfire_risk == "HIGH":
            sentences.append((2, (
                "Bushfire risk is HIGH — a Bushfire Management Overlay applies. "
                "BAL construction standards and defendable space are mandatory."
            )))
        elif bushfire_risk == "MEDIUM":
            sentences.append((3, "A Bushfire Area Overlay applies — bushfire protection measures are required."))
        elif bushfire_risk == "LOW":
            sentences.append((5, "The site is within a designated Bushfire Prone Area."))

        # Per-overlay summaries (sorted by severity descending, skip flood/bushfire already covered)
        skip_families = {"flood", "bushfire", "acquisition"}
        seen_families: set[str] = set()
        for o in sorted(overlays, key=lambda x: x.get("severity", 0), reverse=True):
            family = o.get("family", "other")
            if family in skip_families:
                continue
            # Only emit one sentence per family in the summary to keep it concise
            if family not in seen_families:
                sentences.append((6, o["summary"]))
                seen_families.add(family)

        # Sort by priority and return plain sentences
        sentences.sort(key=lambda x: x[0])
        return [s for _, s in sentences]