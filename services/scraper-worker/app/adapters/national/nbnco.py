"""NBN Co adapter — checks NBN connectivity type for an address.

Uses the NBN Co places API to resolve a lat/lng to an NBN Location ID
and retrieve the technology type (FTTP, HFC, FTTN, FTTB, FTTC, Fixed Wireless, Satellite).

Resolution strategy (in priority order):
  1. nbn_loc_id in job dict — skip all resolution, go straight to details
  2. lat/lng → GET /places/v1/nearby → locId (reliable, no reCAPTCHA)
  3. address_string → POST /places/v2/suggest → locId (fragile fallback)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.adapters.base import BaseAdapter
from app.services.db import get_db_connection, update_property_nbn_loc_id

logger = logging.getLogger(__name__)

_NBN_HEADERS = {
    "Referer": "https://www.nbnco.com.au/",
    "Accept": "application/json, text/plain, */*",
    "X-NBN-Sender-Id": "nbn-website",
}


class NbnCoAdapter(BaseAdapter):
    """Checks NBN connectivity type via NBN Co's unofficial places API.

    Job dict should contain:
      - latitude (float) + longitude (float) — primary resolution method
      - address_string (str)                 — fallback if coords fail
      - nbn_loc_id (str)                     — optional, skips resolution entirely
      - property_id (str)                    — optional, used to persist resolved locId
    """

    NBN_V1 = "https://places.nbnco.net.au/places/v1"
    NBN_V2 = "https://places.nbnco.net.au/places/v2"

    def scrape(self, job: dict) -> dict:
        # Strategy 1: locId already known — skip resolution entirely
        loc_id = job.get("nbn_loc_id")

        # Strategy 2: resolve via lat/lng (reliable — no reCAPTCHA)
        if not loc_id:
            lat, lng = job.get("latitude"), job.get("longitude")
            if lat is not None and lng is not None:
                loc_id = self._resolve_from_coords(lat, lng)

        # Strategy 3: fall back to address string suggest (fragile)
        if not loc_id:
            address = job.get("address_string")
            if address:
                loc_id = self._resolve_from_address(address)

        if not loc_id:
            logger.warning(
                "Could not determine NBN locId for property at lat=%s lng=%s",
                job.get("latitude"),
                job.get("longitude"),
            )
            return {"nbn": None}

        # Persist resolved loc_id back to the property row so future runs reuse it
        property_id = job.get("property_id")
        if property_id:
            try:
                db = get_db_connection()
                update_property_nbn_loc_id(db, property_id, loc_id)
            except Exception:
                logger.exception("Failed to persist nbn_loc_id=%s for property=%s", loc_id, property_id)
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        return self._fetch_details(loc_id)

    # ── Resolution helpers ───────────────────────────────────────────────────

    def _resolve_from_coords(self, lat: float, lng: float) -> str | None:
        """Resolve lat/lng to NBN locId via the v1/nearby endpoint.

        Returns the nearest location ID, which for a precise property
        lat/lng will be the property itself.
        """
        try:
            data = self.fetch_json(
                f"{self.NBN_V1}/nearby?lat={lat}&lng={lng}",
                headers=_NBN_HEADERS,
            )
            locations = data.get("locations", []) if isinstance(data, dict) else []
            if not locations:
                logger.debug("NBN nearby returned no locations for lat=%s lng=%s", lat, lng)
                return None

            loc_id = locations[0].get("id")
            logger.debug("Resolved lat=%s lng=%s → locId=%s via nearby", lat, lng, loc_id)
            return loc_id

        except Exception as exc:
            logger.debug("NBN nearby failed for lat=%s lng=%s: %s", lat, lng, exc)
            return None

    def _resolve_from_address(self, address: str) -> str | None:
        """Resolve address string to NBN locId via the v2/suggest endpoint.

        Known issues: returns 404 when reCAPTCHA protection is active.
        Used only as a last resort when coordinates are unavailable.
        """
        try:
            data = self.fetch_json(
                f"{self.NBN_V2}/suggest",
                method="POST",
                json_body={"query": address},
                headers=_NBN_HEADERS,
            )
            suggestions = data.get("suggestions", []) if isinstance(data, dict) else []
            if not suggestions:
                logger.debug("NBN suggest returned no results for address=%r", address)
                return None

            loc_id = suggestions[0].get("id")
            logger.debug("Resolved address=%r → locId=%s via suggest", address, loc_id)
            return loc_id

        except Exception as exc:
            logger.debug("NBN suggest failed for address=%r: %s", address, exc)
            return None

    # ── Details fetch ────────────────────────────────────────────────────────

    def _fetch_details(self, loc_id: str) -> dict:
        """Fetch NBN service details for a resolved NBN Location ID."""
        try:
            data = self.fetch_json(
                f"{self.NBN_V2}/details/{loc_id}",
                headers=_NBN_HEADERS,
            )

            if not isinstance(data, dict):
                logger.warning("Unexpected NBN details response for locId=%s", loc_id)
                return {"nbn": None}

            # addressDetail is premise-level (precise); servingArea is area-level fallback
            addr = data.get("addressDetail") or {}
            area = data.get("servingArea") or {}

            tech_type = addr.get("techType") or area.get("techType")
            # prefer API-provided timestamp (ms since epoch) if present
            fetched_ts = data.get("timestamp")
            if fetched_ts:
                try:
                    # timestamp is milliseconds since epoch
                    fetched_at = datetime.fromtimestamp(int(fetched_ts) / 1000, UTC).isoformat()
                except Exception:
                    fetched_at = datetime.now(UTC).isoformat()
            else:
                fetched_at = datetime.now(UTC).isoformat()

            return {
                "nbn": {
                    "loc_id": loc_id,
                    "tech_type": tech_type,
                    "service_type": addr.get("serviceType") or area.get("serviceType"),
                    "service_status": addr.get("serviceStatus") or area.get("serviceStatus"),
                    "tech_change_status": addr.get("techChangeStatus"),
                    "target_eligibility_quarter": addr.get("targetEligibilityQuarter"),
                    "formatted_address": addr.get("formattedAddress"),
                    "latitude": addr.get("latitude") or area.get("latitude"),
                    "longitude": addr.get("longitude") or area.get("longitude"),
                    "postcode": addr.get("postcode") or area.get("postcode"),
                },
                "nbn_type": tech_type,
                "data_sources": [
                    {
                        "name": "NBN Co Places API (unofficial)",
                        "url": "https://places.nbnco.net.au/places/",
                        "fetched_at": fetched_at,
                    }
                ],
            }

        except Exception:
            logger.exception("NBN details fetch failed for locId=%s", loc_id)
            return {"nbn": None}
