"""ABS Census Service — Fetch-on-demand census statistics from ABS API."""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

ABS_BASE = "https://data.api.abs.gov.au/rest/data"
DATAFLOWS = {
    "medians": "C21_G02_SAL",
    "population": "C21_G01_SAL",
    "age": "C21_G04_SAL",
    "birthplace": "C21_G09_SAL",
    "income": "C21_G17_SAL",
    "labour": "C21_G46_SAL",
}

URL_TEMPLATES = {
    "medians": "{dataflow}/.{sal}..?format=jsondata",
    "population": "{dataflow}/..{sal}..?format=jsondata",
    "age": "{dataflow}/..{sal}..?format=jsondata",
    "birthplace": "{dataflow}/...{sal}..?format=jsondata",
    "income": "{dataflow}/...{sal}..?format=jsondata",
    "labour": "{dataflow}/...{sal}..?format=jsondata",
}


def _series_records(data: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Return one parsed record per SDMX series entry."""
    if not data or "data" not in data:
        return []

    payload = data["data"]
    if "structure" in payload:
        structure = payload["structure"]
    elif "structures" in payload and isinstance(payload["structures"], list) and payload["structures"]:
        structure = payload["structures"][0]
    else:
        return []

    dims = structure["dimensions"]["series"]
    datasets = payload.get("dataSets", [])
    if not datasets:
        return []

    series = datasets[0].get("series", {})
    records: list[Dict[str, Any]] = []
    for series_key, series_value in series.items():
        try:
            indices = [int(part) for part in series_key.split(":")]
        except ValueError:
            continue

        ids: Dict[str, str] = {}
        labels: Dict[str, str] = {}
        for dim, index in zip(dims, indices):
            values = dim.get("values", [])
            if index < 0 or index >= len(values):
                continue

            value = values[index]
            dim_id = dim.get("id")
            if not dim_id:
                continue

            ids[dim_id] = str(value.get("id", ""))
            labels[dim_id] = value.get("name", str(value.get("id", "")))

        obs = series_value.get("observations", {}).get("0")
        if obs and len(obs) > 0:
            records.append({"ids": ids, "labels": labels, "value": obs[0]})

    return records


def _find_record_value(
    records: list[Dict[str, Any]],
    required_ids: Dict[str, str],
) -> Any:
    for record in records:
        ids = record.get("ids", {})
        if all(ids.get(key) == value for key, value in required_ids.items()):
            return record.get("value")
    return None


def _aggregate_by_dimension(
    records: list[Dict[str, Any]],
    target_dim: str,
    required_ids: Dict[str, str],
    limit: int = 5,
) -> list[Dict[str, Any]]:
    buckets: Dict[str, float] = {}
    for record in records:
        ids = record.get("ids", {})
        if any(ids.get(key) != value for key, value in required_ids.items()):
            continue

        label = record.get("labels", {}).get(target_dim)
        if not label:
            continue

        try:
            numeric_value = float(record.get("value", 0) or 0)
        except (TypeError, ValueError):
            continue

        buckets[label] = buckets.get(label, 0.0) + numeric_value

    return [
        {
            "label": label,
            "count": int(value) if float(value).is_integer() else round(value, 2),
        }
        for label, value in sorted(buckets.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def _extract_display_stats(raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract human-readable census stats from raw multi-dataflow response."""
    if not raw_data or ("g02" not in raw_data and "g01" not in raw_data):
        return None

    g01 = _series_records(raw_data.get("g01", {}))
    g02 = _series_records(raw_data.get("g02", {}))
    g04 = _series_records(raw_data.get("g04", {}))
    g09 = _series_records(raw_data.get("g09", {}))
    g17 = _series_records(raw_data.get("g17", {}))
    g46 = _series_records(raw_data.get("g46", {}))

    if not g01 and not g02:
        return None

    population_val = _find_record_value(g01, {"SEXP": "3", "PCHAR": "P_1"})
    male_count_val = _find_record_value(g01, {"SEXP": "1", "PCHAR": "P_1"})
    female_count_val = _find_record_value(g01, {"SEXP": "2", "PCHAR": "P_1"})

    population = int(population_val) if population_val is not None else None
    male_count = int(male_count_val) if male_count_val is not None else None
    female_count = int(female_count_val) if female_count_val is not None else None

    born_overseas_count_val = _find_record_value(g01, {"SEXP": "3", "PCHAR": "B_O"})
    born_in_australia_count_val = _find_record_value(g01, {"SEXP": "3", "PCHAR": "B_11"})
    indigenous_count_val = _find_record_value(g01, {"SEXP": "3", "PCHAR": "A_T"})
    language_english_only_count_val = _find_record_value(g01, {"SEXP": "3", "PCHAR": "L_1201"})

    born_overseas_pct = None
    born_in_australia_pct = None
    indigenous_pct = None
    language_english_only_pct = None
    if population and population > 0:
        if born_overseas_count_val is not None:
            born_overseas_pct = round((float(born_overseas_count_val) / population) * 100, 2)
        if born_in_australia_count_val is not None:
            born_in_australia_pct = round((float(born_in_australia_count_val) / population) * 100, 2)
        if indigenous_count_val is not None:
            indigenous_pct = round((float(indigenous_count_val) / population) * 100, 2)
        if language_english_only_count_val is not None:
            language_english_only_pct = round((float(language_english_only_count_val) / population) * 100, 2)

    median_age = None
    median_weekly_household_income = None
    median_total_family_income = None
    median_total_personal_income = None
    median_weekly_rent = None
    median_monthly_mortgage = None
    average_household_size = None
    average_persons_per_bedroom = None

    for record in g02:
        label = str(record.get("labels", {}).get("MEDAVG", "")).lower()
        value = record.get("value")
        if value is None:
            continue

        if "median age" in label:
            median_age = int(float(value))
        elif "median total household income" in label:
            median_weekly_household_income = int(float(value))
        elif "median total family income" in label:
            median_total_family_income = int(float(value))
        elif "median total personal income" in label:
            median_total_personal_income = int(float(value))
        elif "median rent" in label:
            median_weekly_rent = int(float(value))
        elif "median mortgage" in label:
            median_monthly_mortgage = int(float(value))
        elif "average household size" in label:
            average_household_size = float(value)
        elif "average number of persons per bedroom" in label:
            average_persons_per_bedroom = float(value)

    age_distribution = _aggregate_by_dimension(g04, "AGEINGP", {"SEXP": "3"}, limit=8)
    top_birth_countries = _aggregate_by_dimension(g09, "BPLP", {"SEXP": "3"}, limit=6)
    income_distribution = _aggregate_by_dimension(g17, "INCP", {"SEXP": "3"}, limit=6)
    labour_force_distribution = _aggregate_by_dimension(g46, "LFSP", {"SEXP": "3"}, limit=6)

    return {
        "population": population,
        "male_count": male_count,
        "female_count": female_count,
        "median_age": median_age,
        "median_weekly_household_income": median_weekly_household_income,
        "median_total_family_income": median_total_family_income,
        "median_total_personal_income": median_total_personal_income,
        "median_weekly_rent": median_weekly_rent,
        "median_monthly_mortgage": median_monthly_mortgage,
        "average_household_size": average_household_size,
        "average_persons_per_bedroom": average_persons_per_bedroom,
        "born_overseas_pct": born_overseas_pct,
        "born_in_australia_pct": born_in_australia_pct,
        "indigenous_pct": indigenous_pct,
        "language_english_only_pct": language_english_only_pct,
        "renting_pct": None,
        "age_distribution": age_distribution,
        "top_birth_countries": top_birth_countries,
        "income_distribution": income_distribution,
        "labour_force_distribution": labour_force_distribution,
    }


async def _fetch_from_abs(sal_code: str) -> Dict[str, Any]:
    """Fetch all working ABS Census SAL dataflows concurrently from ABS API."""
    urls = {
        key: f"{ABS_BASE}/{URL_TEMPLATES[key].format(dataflow=dataflow, sal=sal_code)}"
        for key, dataflow in DATAFLOWS.items()
    }

    results: Dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=20.0) as client:
        keys = list(urls.keys())
        responses = await asyncio.gather(
            *(client.get(urls[key]) for key in keys),
            return_exceptions=True,
        )

        for key, resp in zip(keys, responses):
            if isinstance(resp, Exception):
                logger.error("Error fetching %s from ABS: %s", key, resp)
                results[key] = {}
            elif resp.status_code == 200:
                try:
                    results[key] = resp.json()
                except Exception as exc:
                    logger.error("Error parsing JSON for %s from ABS: %s", key, exc)
                    results[key] = {}
            else:
                logger.warning("ABS API returned status %s for %s", resp.status_code, key)
                results[key] = {}

    return {
        "g01": results.get("population", {}),
        "g02": results.get("medians", {}),
        "g04": results.get("age", {}),
        "g09": results.get("birthplace", {}),
        "g17": results.get("income", {}),
        "g46": results.get("labour", {}),
    }


def _has_complete_raw_data(raw_data: Dict[str, Any]) -> bool:
    required = ("g01", "g02", "g04", "g09", "g17", "g46")
    return all(raw_data.get(key) for key in required)


async def get_or_fetch_suburb_census_stats(sal_code: str, db) -> Optional[Dict[str, Any]]:
    """Return cached or freshly-fetched ABS Census 2021 stats for a suburb."""
    try:
        row = await db.fetchrow(
            "SELECT raw_data FROM abs_census_data WHERE region_code=$1 AND region_type='SAL2021'",
            sal_code,
        )
        if row and row["raw_data"]:
            raw_data = row["raw_data"]
            if isinstance(raw_data, str):
                raw_data = json.loads(raw_data)

            if _has_complete_raw_data(raw_data):
                return _extract_display_stats(raw_data)

            logger.info("ABS cache for SAL %s is incomplete; refreshing from API", sal_code)

        raw = await _fetch_from_abs(sal_code)
        if not raw.get("g02") and not raw.get("g01"):
            return None

        if _has_complete_raw_data(raw):
            await db.execute(
                """
                INSERT INTO abs_census_data (region_code, region_type, census_year, raw_data, fetched_at)
                VALUES ($1, 'SAL2021', 2021, $2::jsonb, now())
                ON CONFLICT (region_code, region_type)
                DO UPDATE SET raw_data=EXCLUDED.raw_data, fetched_at=now(), updated_at=now()
                """,
                sal_code,
                json.dumps(raw),
            )

        return _extract_display_stats(raw)
    except Exception as e:
        logger.error(f"Error in get_or_fetch_suburb_census_stats: {e}", exc_info=True)
        return None
