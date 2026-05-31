"""import_spatial_zones.py – Load LGA/suburb/school-catchment boundaries into spatial_zones.

Imports GeoJSON or Shapefile boundary data from the Australian Bureau of Statistics
(ABS) and state education departments.

Usage:
    python import_spatial_zones.py --type LGA --source /data/LGA_2024_AUST_GDA2020.shp
    python import_spatial_zones.py --type SUBURB --source /data/SAL_2021_AUST_GDA2020.shp
    python import_spatial_zones.py --type SCHOOL_CATCHMENT --source /data/vic_school_zones.geojson --state VIC

Requires: GDAL (ogr2ogr) or fiona for shapefile reading.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path

import psycopg2

sys.path.append(str(Path(__file__).parent))
from slug_utils import ensure_unique_slug, make_zone_slug

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://parceliq:devpassword@localhost:5432/parceliq"
)

VALID_STATES = ("VIC", "NSW", "QLD", "SA", "WA", "TAS", "ACT", "NT")
VALID_ZONE_TYPES = ("LGA", "SUBURB", "SCHOOL_CATCHMENT")
SUPPORTED_SOURCE_SUFFIXES = (".geojson", ".json", ".shp")

# ABS shapefile field mappings
FIELD_MAPS = {
    "LGA": {
        "name_fields": ["LGA_NAME25", "LGA_NAME_2024", "LGA_NAME_2023", "LGA_NAME_2021", "LGA_NAME", "NAME"],
        "state_fields": ["STE_NAME21", "STE_NAME_2021", "STE_NAME", "STATE_NAME"],
    },
    "SUBURB": {
        "name_fields": ["SAL_NAME21", "SAL_NAME_2021", "SAL_NAME", "NAME", "SUBURB_NAME"],
        "state_fields": ["STE_NAME21", "STE_NAME_2021", "STE_NAME", "STATE_NAME"],
    },
    "SCHOOL_CATCHMENT": {
        "name_fields": ["School_Name", "Campus_Name", "SCHOOL_NAME", "NAME", "SCHOOL"],
        "state_fields": [],  # State is passed as argument for school catchments
    },
}

STATE_NAME_MAP = {
    "Victoria": "VIC",
    "New South Wales": "NSW",
    "Queensland": "QLD",
    "South Australia": "SA",
    "Western Australia": "WA",
    "Tasmania": "TAS",
    "Australian Capital Territory": "ACT",
    "Northern Territory": "NT",
}

# ABS state code to abbreviation (from shapefiles with STE_CODE21)
STATE_CODE_MAP = {
    "1": "NSW",
    "2": "VIC",
    "3": "QLD",
    "4": "SA",
    "5": "WA",
    "6": "TAS",
    "7": "ACT",
    "8": "NT",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import spatial zone boundaries into PostgreSQL")
    parser.add_argument(
        "--type",
        required=True,
        choices=VALID_ZONE_TYPES,
        help="Zone type to import",
    )
    parser.add_argument(
        "--source",
        required=True,
        help=(
            "Path to GeoJSON/Shapefile, directory, or glob pattern "
            "(e.g. /path/file.geojson, /path/school_zones, /path/*.geojson)"
        ),
    )
    parser.add_argument(
        "--state",
        default=None,
        help="Override state for all features (required for SCHOOL_CATCHMENT)",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Delete existing zones of this type before importing",
    )
    return parser.parse_args()


def expand_glob_and_load_features(source_pattern: str) -> list[dict]:
    """
    Expand source input and load features from all matching files.
    Supports single files, directories, and glob patterns like /path/*.geojson.
    Directory input imports all supported files in that directory.
    
    Returns aggregated list of features from all files.
    """
    # Expand source path/glob. glob() also returns a direct directory path if provided.
    matches = [Path(p) for p in glob.glob(source_pattern, recursive=True)]

    if not matches:
        print(f"ERROR: No files match pattern: {source_pattern}", file=sys.stderr)
        sys.exit(1)

    matching_files: list[Path] = []
    for match in matches:
        if match.is_dir():
            for child in sorted(match.iterdir()):
                if child.is_file() and child.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES:
                    matching_files.append(child)
            continue

        if match.is_file():
            matching_files.append(match)
    
    if not matching_files:
        print(
            (
                f"ERROR: No supported files found for source: {source_pattern}. "
                "Supported extensions: .geojson, .json, .shp"
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    # Sort for consistent import order
    matching_files.sort()
    
    all_features = []
    
    for path in matching_files:

        if not path.exists():
            print(f"⚠️  File not found: {path}", file=sys.stderr)
            continue
        
        if not path.is_file():
            print(f"⚠️  Not a file: {path}", file=sys.stderr)
            continue
        
        print(f"Loading: {path}")
        features = load_features(path)
        print(f"  ✓ Loaded {len(features):,} features from {path.name}")
        all_features.extend(features)
    
    return all_features


def load_features(source: Path) -> list[dict]:
    """Load features from GeoJSON or Shapefile."""
    suffix = source.suffix.lower()

    if suffix == ".geojson" or suffix == ".json":
        with open(source) as f:
            data = json.load(f)
        return data.get("features", [])

    elif suffix == ".shp":
        # A Shapefile must include sidecar files. We can recreate .shx in some cases,
        # but .dbf is required for zone metadata like names/state.
        dbf_path = source.with_suffix(".dbf")
        shx_path = source.with_suffix(".shx")
        if not dbf_path.exists():
            print(
                (
                    "ERROR: Incomplete Shapefile. Missing sidecar file "
                    f"'{dbf_path.name}'. Provide the full Shapefile set (.shp/.dbf/.shx/.prj) "
                    "or use a GeoJSON source instead."
                ),
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            import fiona
        except ImportError:
            print(
                "ERROR: fiona is required for Shapefile reading. Install in infra/scripts with: uv add fiona",
                file=sys.stderr,
            )
            sys.exit(1)

        features = []
        try:
            # Some Fiona/GDAL builds fail to open valid shapefiles when
            # SHAPE_RESTORE_SHX is forced. Only enable it when .shx is missing.
            if shx_path.exists():
                with fiona.open(source) as src:
                    for feat in src:
                        # Convert fiona feature to GeoJSON-like dict
                        geom = feat.get("geometry")
                        if not geom:
                            # Skip features with null/invalid geometries
                            continue
                        geom = dict(geom)
                        props = dict(feat.get("properties", {}))
                        features.append({"geometry": geom, "properties": props})
            else:
                with fiona.Env(SHAPE_RESTORE_SHX="YES"):
                    with fiona.open(source) as src:
                        for feat in src:
                            # Convert fiona feature to GeoJSON-like dict
                            geom = feat.get("geometry")
                            if not geom:
                                # Skip features with null/invalid geometries
                                continue
                            geom = dict(geom)
                            props = dict(feat.get("properties", {}))
                            features.append({"geometry": geom, "properties": props})
        except Exception as e:
            print(f"ERROR: Failed to read shapefile '{source.name}': {e}", file=sys.stderr)
            print(
                "Hint: ensure .shp/.dbf/.shx/.prj files are present together in the same directory.",
                file=sys.stderr,
            )
            sys.exit(1)
        return features

    else:
        print(f"ERROR: Unsupported file format: {suffix}. Use .geojson, .json, or .shp", file=sys.stderr)
        sys.exit(1)


def resolve_field(properties: dict, field_candidates: list[str]) -> str | None:
    """Try multiple field names and return the first match."""
    for field in field_candidates:
        val = properties.get(field)
        if val:
            return str(val).strip()
    return None


def resolve_state(properties: dict, field_candidates: list[str], override: str | None) -> str | None:
    """Resolve state abbreviation from properties or override."""
    if override:
        return override.upper()

    # First try state code fields (STE_CODE21, STE_CODE, etc.)
    for code_field in ["STE_CODE21", "STE_CODE", "STATE_CODE"]:
        code = properties.get(code_field, "").strip()
        if code and code in STATE_CODE_MAP:
            return STATE_CODE_MAP[code]

    # Then try state name fields
    raw = resolve_field(properties, field_candidates)
    if not raw:
        return None

    # Try direct abbreviation
    if raw.upper() in VALID_STATES:
        return raw.upper()

    # Try full name mapping
    return STATE_NAME_MAP.get(raw)


def ensure_multipolygon(geojson_geom: dict) -> str | None:
    """Convert GeoJSON geometry to MultiPolygon WKT-compatible GeoJSON string.
    Ensures the geometry is always MultiPolygon for consistent storage."""
    geom_type = geojson_geom.get("type", "")

    if geom_type == "MultiPolygon":
        return json.dumps(geojson_geom)
    elif geom_type == "Polygon":
        # Wrap Polygon in MultiPolygon
        multi = {
            "type": "MultiPolygon",
            "coordinates": [geojson_geom["coordinates"]],
        }
        return json.dumps(multi)
    else:
        return None  # Skip non-polygon geometries


def import_zones(conn, features: list[dict], zone_type: str, state_override: str | None) -> int:
    """Insert features into spatial_zones. Returns row count."""
    field_map = FIELD_MAPS[zone_type]
    inserted = 0
    seen_slugs: set[str] = set()
    with conn.cursor() as cur:
        cur.execute("SELECT slug FROM spatial_zones")
        for row in cur.fetchall():
            seen_slugs.add(row[0])

    with conn.cursor() as cur:
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})

            name = resolve_field(props, field_map["name_fields"])
            state = resolve_state(props, field_map["state_fields"], state_override)

            if not name or not state or state not in VALID_STATES:
                continue

            geojson_str = ensure_multipolygon(geom)
            if not geojson_str:
                continue

            base_slug = make_zone_slug(name, state, zone_type)
            slug = ensure_unique_slug(base_slug, seen_slugs)

            metadata = json.dumps({
                k: v for k, v in props.items()
                if k not in (field_map["name_fields"] + field_map["state_fields"])
            })

            cur.execute(
                """
                INSERT INTO spatial_zones (zone_type, name, state, slug, geom, metadata)
                VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s::jsonb)
                ON CONFLICT (zone_type, name, state) DO UPDATE SET
                    slug = EXCLUDED.slug,
                    geom = ST_Union(spatial_zones.geom, EXCLUDED.geom),
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                """,
                (zone_type, name, state, slug, geojson_str, metadata),
            )
            inserted += 1

            if inserted % 500 == 0:
                conn.commit()
                print(f"  {inserted:,} zones imported...")

    conn.commit()
    return inserted


def main() -> None:
    args = parse_args()
    source_pattern = args.source

    if args.type == "SCHOOL_CATCHMENT" and not args.state:
        print("ERROR: --state is required for SCHOOL_CATCHMENT zone type", file=sys.stderr)
        sys.exit(1)

    if args.state and args.state.upper() not in VALID_STATES:
        print(f"ERROR: Invalid state '{args.state}'", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)

    if args.truncate:
        print(f"Deleting existing {args.type} zones...")
        with conn.cursor() as cur:
            cur.execute("DELETE FROM spatial_zones WHERE zone_type = %s", (args.type,))
        conn.commit()

    print(f"Loading features from: {source_pattern}")
    features = expand_glob_and_load_features(source_pattern)
    print(f"\n✓ Total: {len(features):,} features from all files")

    if not features:
        print("ERROR: No features loaded from any files", file=sys.stderr)
        conn.close()
        sys.exit(1)

    start = time.time()
    count = import_zones(conn, features, args.type, args.state)
    elapsed = time.time() - start

    print(f"\n✓ Imported {count:,} {args.type} zones in {elapsed:.1f}s")

    # Analyze for query planner
    print("Running ANALYZE on spatial_zones...")
    with conn.cursor() as cur:
        cur.execute("ANALYZE spatial_zones;")
    conn.commit()
    conn.close()
    print("✓ Import complete.")


if __name__ == "__main__":
    main()
