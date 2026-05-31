"""Parallel adapter execution engine.

Runs national + state + (optional) council adapters concurrently using a
thread pool.  Failed adapters are logged but never block the scrape — the
LLM parser will work with whatever data is available.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.adapters.base import BaseAdapter
from app.adapters.registry import (
    COUNCIL_ADAPTER_MAP,
    NATIONAL_ADAPTERS,
    STATE_ADAPTER_MAP,
    GenericStateAdapter,
)

logger = logging.getLogger(__name__)


def run_adapters_parallel(
    job: dict,
    council_config: dict | None,
    state: str,
) -> list[dict]:
    """Run all applicable adapters concurrently and return partial results.

    Parameters
    ----------
    job:
        Dict with property_id, gnaf_pid, address_string, latitude,
        longitude, lga_name, state.
    council_config:
        Row from ``data_source_configs`` (adapter_name, base_url, config)
        or ``None`` if no council adapter is configured for this LGA.
    state:
        Two- or three-letter Australian state code.
    """
    tasks: list[tuple[str, type[BaseAdapter], dict]] = []

    # National adapters (always run)
    for adapter_cls in NATIONAL_ADAPTERS:
        tasks.append(("national", adapter_cls, {}))

    # State adapter
    state_adapter = STATE_ADAPTER_MAP.get(state, GenericStateAdapter)
    tasks.append(("state", state_adapter, {}))

    # Council adapter (only if configured for this LGA)
    if council_config:
        council_adapter = COUNCIL_ADAPTER_MAP.get(council_config.get("adapter_name", ""))
        if council_adapter:
            tasks.append(("council", council_adapter, council_config))

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(len(tasks), 1)) as executor:
        futures = {
            executor.submit(
                adapter_cls(
                    base_url=cfg.get("base_url", ""),
                    config=cfg.get("config", cfg),
                ).scrape,
                job,
            ): name
            for name, adapter_cls, cfg in tasks
        }
        for future in as_completed(futures):
            adapter_name = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                logger.warning("Adapter %s failed: %s.  Continuing.", adapter_name, exc)
                results.append({})  # empty partial — won't block LLM

    return results


def merge_adapter_results(partials: list[dict]) -> dict:
    """Merge partial dicts from multiple adapters into one.

    Later non-None values overwrite earlier ones.  ``data_sources`` and
        ``overlays``/``overlay_codes`` are *accumulated* (not replaced).

        Overlay contract (strict):
            - ``overlays`` must be a list[dict] where each dict has a string ``code``.
            - ``overlay_codes`` must be a list[str].

        Any legacy/non-conforming overlay entries are ignored.
    """
    merged: dict = {
        "zoning_code": None,
        "zoning_label": None,
        "overlays": [],
                "overlay_codes": [],
        "flood_risk": None,
        "bushfire_risk": None,
        "nbn_type": None,
        "demographics": None,
        "council_planning_applications_text": None,
        "council_meeting_minutes_text": None,
        "data_sources": [],
    }

    for partial in partials:
        for key, value in partial.items():
            if key == "data_sources" and isinstance(value, list):
                merged["data_sources"].extend(value)
            elif key == "overlays" and isinstance(value, list):
                for overlay in value:
                    if not isinstance(overlay, dict):
                        continue
                    code = overlay.get("code")
                    if isinstance(code, str) and code:
                        merged["overlays"].append(overlay)
            elif key == "overlay_codes" and isinstance(value, list):
                merged["overlay_codes"].extend(
                    code for code in value if isinstance(code, str) and code
                )
            elif key.startswith("_"):
                # Internal fields like _adapter_error — skip
                continue
            elif value is not None:
                merged[key] = value

    # De-duplicate overlays by code (keep first occurrence)
    unique_overlays: dict[str, dict] = {}
    for overlay in merged["overlays"]:
        code = overlay["code"]
        if code not in unique_overlays:
            unique_overlays[code] = overlay
    merged["overlays"] = list(unique_overlays.values())

    # Canonical overlay codes = explicit codes + codes from overlay objects
    all_codes = merged["overlay_codes"] + [overlay["code"] for overlay in merged["overlays"]]
    merged["overlay_codes"] = list(dict.fromkeys(all_codes))

    return merged
