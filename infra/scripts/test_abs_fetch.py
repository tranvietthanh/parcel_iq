import argparse
import asyncio
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ABS_BASE = "https://data.api.abs.gov.au/rest/data"
ABS_SAL_DATAFLOWS = {
    "g01": "C21_G01_SAL",
    "g02": "C21_G02_SAL",
    "g04": "C21_G04_SAL",
    "g09": "C21_G09_SAL",
    "g17": "C21_G17_SAL",
    "g46": "C21_G46_SAL",
}

ABS_SAL_URL_TEMPLATES = {
    "g01": "C21_G01_SAL/..{sal}..?format=jsondata",
    "g02": "C21_G02_SAL/.{sal}..?format=jsondata",
    "g04": "C21_G04_SAL/..{sal}..?format=jsondata",
    "g09": "C21_G09_SAL/...{sal}..?format=jsondata",
    "g17": "C21_G17_SAL/...{sal}..?format=jsondata",
    "g46": "C21_G46_SAL/...{sal}..?format=jsondata",
}

def _build_abs_url(dataflow_id: str, sal_code: str) -> str:
    for label, flow_id in ABS_SAL_DATAFLOWS.items():
        if flow_id == dataflow_id:
            template = ABS_SAL_URL_TEMPLATES[label]
            return f"{ABS_BASE}/{template.format(sal=sal_code)}"

    raise KeyError(f"Unknown ABS dataflow: {dataflow_id}")


def _parse_sdmx_series(data: dict[str, Any]) -> dict[str, Any]:
    if not data or "data" not in data:
        return {}

    payload = data["data"]
    try:
        if "structure" in payload:
            structure = payload["structure"]
        elif "structures" in payload and isinstance(payload["structures"], list) and payload["structures"]:
            structure = payload["structures"][0]
        else:
            return {}

        dims = structure["dimensions"]["series"]
        series = payload["dataSets"][0].get("series", {})

        parsed: dict[str, Any] = {}
        for series_key, series_value in series.items():
            dim_index = int(series_key.split(":")[0])
            if dim_index >= len(dims[0]["values"]):
                continue

            metric_name = dims[0]["values"][dim_index]["name"]
            observation = series_value.get("observations", {}).get("0")
            if observation and len(observation) > 0:
                parsed[metric_name] = observation[0]

        return parsed
    except Exception:
        return {}


def _http_get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _resolve_suburb(suburb_query: str) -> tuple[str, str, dict[str, Any]]:
    payload = _http_get_json(
        "https://data.api.abs.gov.au/rest/codelist/ABS/CL_SAL_2021",
        {"Accept": "application/vnd.sdmx.structure+json"},
    )
    codes = payload["data"]["codelists"][0]["codes"]

    if suburb_query.isdigit():
        for code in codes:
            if code["id"] == suburb_query:
                return code["name"], suburb_query, {"SAL_CODE21": suburb_query}
        raise ValueError(f"No suburb found with SAL code {suburb_query}")

    matches = [
        code
        for code in codes
        if suburb_query.lower() in code["name"].lower()
    ]
    if not matches:
        raise ValueError(f"No suburb found matching {suburb_query!r}")

    exact = [code for code in matches if code["name"].lower() == suburb_query.lower()]
    selected = exact[0] if exact else matches[0]
    return selected["name"], selected["id"], {"SAL_CODE21": selected["id"]}


def _fetch_all_abs_data(sal_code: str) -> dict[str, dict[str, Any]]:
    headers = {"Accept": "application/vnd.sdmx.data+json;version=1.0.0"}
    results: dict[str, dict[str, Any]] = {}

    for label, dataflow_id in ABS_SAL_DATAFLOWS.items():
        url = _build_abs_url(dataflow_id, sal_code)
        try:
            results[label] = _http_get_json(url, headers)
        except urllib.error.HTTPError as exc:
            print(f"{label}: HTTP {exc.code} from {url}")
            results[label] = {}
        except Exception as exc:
            print(f"{label}: failed to fetch {url}: {exc}")
            results[label] = {}

    return results


def _extract_display_stats(raw_data: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    g02 = _parse_sdmx_series(raw_data.get("g02", {}))
    g01 = _parse_sdmx_series(raw_data.get("g01", {}))

    if not g02 and not g01:
        return None

    median_age = None
    median_weekly_household_income = None
    median_weekly_rent = None
    median_monthly_mortgage = None

    for key, value in g02.items():
        key_lower = key.lower()
        if "median age" in key_lower:
            try:
                median_age = int(value)
            except (ValueError, TypeError):
                pass
        elif "median weekly household income" in key_lower or "median total household income" in key_lower:
            try:
                median_weekly_household_income = int(value)
            except (ValueError, TypeError):
                pass
        elif "median weekly rent" in key_lower:
            try:
                median_weekly_rent = int(value)
            except (ValueError, TypeError):
                pass
        elif "median monthly mortgage repayments" in key_lower or "median monthly mortgage" in key_lower:
            try:
                median_monthly_mortgage = int(value)
            except (ValueError, TypeError):
                pass

    population = None
    born_overseas_pct = None
    indigenous_pct = None
    born_overseas_count = None
    indigenous_count = None
    born_in_australia_count = None

    for key, value in g01.items():
        key_lower = key.lower()
        if "total persons" in key_lower or key_lower == "persons" or key_lower == "total":
            try:
                population = int(value)
            except (ValueError, TypeError):
                pass
        elif "born overseas" in key_lower:
            try:
                born_overseas_count = int(value)
            except (ValueError, TypeError):
                pass
        elif "born in australia" in key_lower:
            try:
                born_in_australia_count = int(value)
            except (ValueError, TypeError):
                pass
        elif "aboriginal" in key_lower or "torres strait" in key_lower:
            try:
                indigenous_count = int(value)
            except (ValueError, TypeError):
                pass

    if population and population > 0:
        if born_overseas_count is not None:
            born_overseas_pct = round((born_overseas_count / population) * 100, 2)
        elif born_in_australia_count is not None:
            born_overseas_pct = round(((population - born_in_australia_count) / population) * 100, 2)

        if indigenous_count is not None:
            indigenous_pct = round((indigenous_count / population) * 100, 2)

    return {
        "population": population,
        "median_age": median_age,
        "median_weekly_household_income": median_weekly_household_income,
        "median_weekly_rent": median_weekly_rent,
        "median_monthly_mortgage": median_monthly_mortgage,
        "born_overseas_pct": born_overseas_pct,
        "indigenous_pct": indigenous_pct,
        "renting_pct": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch all available ABS Census 2021 suburb dataflows for a SAL code or suburb name."
    )
    parser.add_argument(
        "suburb",
        nargs="?",
        default="Werribee",
        help="Suburb name or SAL code to fetch (default: Werribee)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the merged raw ABS payload as JSON.",
    )
    args = parser.parse_args()

    suburb_name, sal_code, metadata = _resolve_suburb(args.suburb)
    print(f"Suburb: {suburb_name}")
    print(f"SAL_CODE21: {sal_code}")
    print(f"Metadata keys: {sorted(metadata.keys())}")

    print("\nFetching all ABS SAL dataflows...")
    raw_data = _fetch_all_abs_data(sal_code)

    print("\nFetch results:")
    for label, dataflow_id in ABS_SAL_DATAFLOWS.items():
        payload = raw_data.get(label, {})
        parsed = _parse_sdmx_series(payload)
        print(f"- {label} ({dataflow_id}): {len(parsed)} series values")
        if parsed:
            sample_keys = list(parsed.keys())[:5]
            print(f"  sample keys: {sample_keys}")

    stats = _extract_display_stats(raw_data)
    print("\nDisplay stats:")
    print(json.dumps(stats, indent=2, sort_keys=True))

    merged_payload = {
        "suburb": suburb_name,
        "sal_code": sal_code,
        "metadata": metadata,
        "raw_data": raw_data,
        "display_stats": stats,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(merged_payload, indent=2, sort_keys=True))
        print(f"\nWrote merged payload to {args.output}")
    else:
        print("\nTip: pass --output tmp/abs_suburb.json to save the merged payload.")


if __name__ == "__main__":
    main()
