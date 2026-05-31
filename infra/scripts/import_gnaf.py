"""import_gnaf.py – Bulk import G-NAF address data into the gnaf_addresses table.

Uses PostgreSQL COPY for performance (~15M rows across all Australian states).
The G-NAF dataset is published by Geoscape Australia under an open data licence.

File can be downloaded from:

Official source: https://data.gov.au/data/dataset/geocoded-national-address-file-g-naf

Usage:
    python import_gnaf.py --state ALL --source /data/gnaf_feb2026.zip
    python import_gnaf.py --state VIC --source /data/gnaf_feb2026.zip

G-NAF relational model (relevant tables):
    ADDRESS_DETAIL → has STREET_LOCALITY_PID, LOCALITY_PID, POSTCODE
    ADDRESS_DEFAULT_GEOCODE → has ADDRESS_DETAIL_PID, LATITUDE, LONGITUDE
    STREET_LOCALITY → has STREET_NAME, STREET_TYPE_CODE, LOCALITY_PID
    LOCALITY → has LOCALITY_NAME, STATE_PID
    STATE → has STATE_NAME, STATE_ABBREVIATION

The script loads the lookup tables into memory and joins them in Python
to build the full address string before COPY into PostgreSQL.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time
import zipfile
from pathlib import Path

import psycopg2

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://parceliq:devpassword@localhost:5432/parceliq"
)

VALID_STATES = ("VIC", "NSW", "QLD", "SA", "WA", "TAS", "ACT", "NT")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import G-NAF addresses into PostgreSQL")
    parser.add_argument(
        "--state",
        default="ALL",
        help="State to import (VIC, NSW, etc.) or ALL for every state",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the G-NAF zip file",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100_000,
        help="Rows per COPY batch (default: 100,000)",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="TRUNCATE gnaf_addresses before importing",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Zip file helpers — locate PSV files inside the G-NAF zip
# ---------------------------------------------------------------------------

def _find_psv(names: list[str], pattern: str) -> str | None:
    """Find first zip entry matching pattern."""
    matches = [n for n in names if pattern in n and n.endswith(".psv")]
    return matches[0] if matches else None


def _read_psv(zf: zipfile.ZipFile, path: str) -> csv.DictReader:
    """Open a PSV file inside the zip and return a DictReader."""
    return csv.DictReader(
        io.TextIOWrapper(zf.open(path), encoding="utf-8"), delimiter="|"
    )


# ---------------------------------------------------------------------------
# Lookup table loaders
# ---------------------------------------------------------------------------

def load_states(zf: zipfile.ZipFile, names: list[str]) -> dict[str, str]:
    """Load all STATE files → {STATE_PID: STATE_ABBREVIATION}."""
    states: dict[str, str] = {}
    for abbr in VALID_STATES:
        path = _find_psv(names, f"{abbr}_STATE_psv")
        if not path:
            continue
        for row in _read_psv(zf, path):
            pid = row.get("STATE_PID", "").strip()
            abbreviation = row.get("STATE_ABBREVIATION", "").strip()
            if pid and abbreviation:
                states[pid] = abbreviation
    return states


def load_localities(
    zf: zipfile.ZipFile, names: list[str], state_prefix: str, state_map: dict[str, str]
) -> dict[str, tuple[str, str, str | None]]:
    """Load LOCALITY file → {LOCALITY_PID: (LOCALITY_NAME, STATE_ABBREVIATION, PRIMARY_POSTCODE)}."""
    localities: dict[str, tuple[str, str, str | None]] = {}
    path = _find_psv(names, f"{state_prefix}_LOCALITY_psv")
    if not path:
        return localities
    for row in _read_psv(zf, path):
        pid = row.get("LOCALITY_PID", "").strip()
        name = row.get("LOCALITY_NAME", "").strip()
        state_pid = row.get("STATE_PID", "").strip()
        postcode = row.get("PRIMARY_POSTCODE", "").strip() or None
        state_abbr = state_map.get(state_pid, "")
        if pid and name:
            localities[pid] = (name, state_abbr, postcode)
    return localities


def load_street_localities(
    zf: zipfile.ZipFile, names: list[str], state_prefix: str
) -> dict[str, tuple[str, str]]:
    """Load STREET_LOCALITY file → {STREET_LOCALITY_PID: (STREET_NAME, STREET_TYPE_CODE)}."""
    streets: dict[str, tuple[str, str]] = {}
    path = _find_psv(names, f"{state_prefix}_STREET_LOCALITY_psv")
    if not path:
        return streets
    for row in _read_psv(zf, path):
        pid = row.get("STREET_LOCALITY_PID", "").strip()
        street_name = row.get("STREET_NAME", "").strip()
        street_type = row.get("STREET_TYPE_CODE", "").strip()
        if pid and street_name:
            streets[pid] = (street_name, street_type)
    return streets


def load_geocodes(zf: zipfile.ZipFile, geocode_path: str) -> dict[str, tuple[float, float]]:
    """Load geocode file → {ADDRESS_DETAIL_PID: (lat, lng)}."""
    geocodes: dict[str, tuple[float, float]] = {}
    for row in _read_psv(zf, geocode_path):
        pid = row.get("ADDRESS_DETAIL_PID", "").strip()
        lat = row.get("LATITUDE", "").strip()
        lng = row.get("LONGITUDE", "").strip()
        if pid and lat and lng:
            try:
                geocodes[pid] = (float(lat), float(lng))
            except ValueError:
                continue
    return geocodes


# ---------------------------------------------------------------------------
# Address string builder
# ---------------------------------------------------------------------------

def build_address_string(
    row: dict,
    streets: dict[str, tuple[str, str]],
    localities: dict[str, tuple[str, str, str | None]],
) -> tuple[str, str | None, str | None]:
    """Build a human-readable address from G-NAF detail + lookups.

    Returns (address_string, suburb, state_abbreviation).
    """
    parts = []

    # Flat/unit number
    flat_number = row.get("FLAT_NUMBER", "").strip()
    if flat_number:
        flat_type = row.get("FLAT_TYPE_CODE", "").strip()
        parts.append(f"{flat_type} {flat_number}".strip())

    # Street number
    number_first = row.get("NUMBER_FIRST", "").strip()
    if number_first:
        number_last = row.get("NUMBER_LAST", "").strip()
        if number_last:
            parts.append(f"{number_first}-{number_last}")
        else:
            parts.append(number_first)

    # Street name (from STREET_LOCALITY lookup)
    street_locality_pid = row.get("STREET_LOCALITY_PID", "").strip()
    if street_locality_pid and street_locality_pid in streets:
        street_name, street_type = streets[street_locality_pid]
        if street_type:
            parts.append(f"{street_name} {street_type}")
        else:
            parts.append(street_name)

    # Locality / suburb (from LOCALITY lookup)
    locality_pid = row.get("LOCALITY_PID", "").strip()
    suburb = None
    state_abbr = None
    postcode = row.get("POSTCODE", "").strip() or None

    if locality_pid and locality_pid in localities:
        locality_name, state_abbr, locality_postcode = localities[locality_pid]
        suburb = locality_name
        parts.append(locality_name)

        # Use postcode from detail row first, fall back to locality's primary postcode
        if not postcode:
            postcode = locality_postcode

    # State + postcode
    if state_abbr:
        if postcode:
            parts.append(f"{state_abbr} {postcode}")
        else:
            parts.append(state_abbr)

    address = ", ".join(parts) if parts else "Unknown address"
    return address, suburb, state_abbr


# ---------------------------------------------------------------------------
# Import logic
# ---------------------------------------------------------------------------

def import_state(
    conn,
    zf: zipfile.ZipFile,
    names: list[str],
    state: str,
    state_map: dict[str, str],
    batch_size: int,
) -> int:
    """Import a single state's G-NAF data. Returns row count."""
    # Find required files
    detail_path = _find_psv(names, f"{state}_ADDRESS_DETAIL_psv")
    geocode_path = _find_psv(names, f"{state}_ADDRESS_DEFAULT_GEOCODE_psv")
    if not detail_path or not geocode_path:
        print(f"  WARNING: Missing PSV files for {state}, skipping")
        return 0

    # Load lookup tables
    print(f"  Loading lookup tables for {state}...")
    geocodes = load_geocodes(zf, geocode_path)
    print(f"    Geocodes: {len(geocodes):,}")

    localities = load_localities(zf, names, state, state_map)
    print(f"    Localities: {len(localities):,}")

    streets = load_street_localities(zf, names, state)
    print(f"    Streets: {len(streets):,}")

    # Process address details
    print(f"  Processing address details for {state}...")
    row_count = 0
    skipped = 0
    batch_buf = io.StringIO()

    for row in _read_psv(zf, detail_path):
        pid = row.get("ADDRESS_DETAIL_PID", "").strip()
        if not pid or pid not in geocodes:
            skipped += 1
            continue

        # Skip alias/secondary addresses — only import principal addresses
        alias_flag = row.get("ALIAS_PRINCIPAL", "").strip()
        if alias_flag and alias_flag != "P":
            skipped += 1
            continue

        lat, lng = geocodes[pid]
        address_string, suburb, row_state = build_address_string(row, streets, localities)

        if not row_state or row_state not in VALID_STATES:
            skipped += 1
            continue

        postcode = row.get("POSTCODE", "").strip() or None

        # Tab-separated line for COPY
        line = "\t".join([
            pid,
            address_string.replace("\t", " ").replace("\n", " "),
            str(lat),
            str(lng),
            postcode or "\\N",
            (suburb or "\\N").replace("\t", " "),
            row_state,
        ])
        batch_buf.write(line + "\n")
        row_count += 1

        if row_count % batch_size == 0:
            _copy_batch(conn, batch_buf)
            batch_buf = io.StringIO()
            print(f"    {row_count:,} rows imported...")

    # Final partial batch
    if batch_buf.tell() > 0:
        _copy_batch(conn, batch_buf)

    print(f"  {state}: {row_count:,} rows imported ({skipped:,} skipped)")
    return row_count


def _copy_batch(conn, buf: io.StringIO) -> None:
    """Execute a COPY FROM for a batch of rows."""
    buf.seek(0)
    with conn.cursor() as cur:
        cur.copy_from(
            buf,
            "gnaf_addresses",
            columns=("gnaf_pid", "address_string", "latitude", "longitude", "postcode", "suburb", "state"),
            null="\\N",
        )
    conn.commit()


def main() -> None:
    args = parse_args()
    source = Path(args.source)

    if not source.exists():
        print(f"ERROR: Source file not found: {source}", file=sys.stderr)
        sys.exit(1)

    states = list(VALID_STATES) if args.state.upper() == "ALL" else [args.state.upper()]
    for s in states:
        if s not in VALID_STATES:
            print(f"ERROR: Invalid state '{s}'. Must be one of: {', '.join(VALID_STATES)}", file=sys.stderr)
            sys.exit(1)

    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)

    if args.truncate:
        print("Truncating gnaf_addresses table...")
        with conn.cursor() as cur:
            cur.execute("TRUNCATE gnaf_addresses;")
        conn.commit()

    print(f"Opening G-NAF zip: {source}")
    with zipfile.ZipFile(source) as zf:
        all_names = zf.namelist()

        # Load state PID → abbreviation mapping (shared across all states)
        print("Loading state reference data...")
        state_map = load_states(zf, all_names)
        print(f"  State PIDs: {state_map}")

        total = 0
        start = time.time()

        for state in states:
            count = import_state(conn, zf, all_names, state, state_map, args.batch_size)
            total += count

        elapsed = time.time() - start
        print(f"\nDone. {total:,} total rows imported in {elapsed:.1f}s")

    # Refresh spatial index + analyze
    print("Running ANALYZE on gnaf_addresses...")
    with conn.cursor() as cur:
        cur.execute("ANALYZE gnaf_addresses;")
    conn.commit()
    conn.close()
    print("Import complete.")


if __name__ == "__main__":
    main()
