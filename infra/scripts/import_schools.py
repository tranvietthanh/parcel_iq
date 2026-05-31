"""import_schools.py – Load school point locations with metadata into schools table.

Imports school data from state education department CSV/GeoJSON files.

Usage:
    python import_schools.py --source ~/Downloads/vic_schools_2024.csv --state VIC
    python import_schools.py --source ~/Downloads/nsw_schools.geojson --state NSW

Expected CSV format (VIC example):
    school_id,name,address,suburb,postcode,lat,lng,school_type,gender,sector,enrolments,year_range
    1234,Westgrove Primary School,37a Thames Boulevard,Werribee,3030,-37.8785,144.65953,Primary,Mixed,Government,,Prep-6

Expected GeoJSON format:
    {
      "type": "FeatureCollection",
      "features": [
        {
          "type": "Feature",
          "geometry": {"type": "Point", "coordinates": [144.65953, -37.8785]},
          "properties": {
            "school_id": "1234",
            "name": "Westgrove Primary School",
            "address": "37a Thames Boulevard",
            "suburb": "Werribee",
            "postcode": "3030",
            "school_type": "Primary",
            "gender": "Mixed",
            "sector": "Government",
            "enrolments": null,
            "year_range": "Prep-6"
          }
        }
      ]
    }
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://parceliq:devpassword@localhost:5432/parceliq"
)

VALID_STATES = ("VIC", "NSW", "QLD", "SA", "WA", "TAS", "ACT", "NT")
VALID_SCHOOL_TYPES = ("Primary", "Secondary", "Combined", "Special")
VALID_GENDERS = ("Mixed", "Boys", "Girls")
VALID_SECTORS = ("Government", "Catholic", "Independent")

# State-specific CSV field mappings for different data sources
STATE_CSV_FIELD_MAPS = {
    "VIC": {
        # Victoria Department of Education CSV (dv402-SchoolLocations*.csv)
        "school_id": "School_No",
        "name": "School_Name",
        "address": "Address_Line_1",
        "suburb": "Address_Town",
        "postcode": "Address_Postcode",
        "lat": "Y",
        "lng": "X",
        "school_type": "School_Type",
        "gender": "Gender",  # Not always present, may be derived from school type
        "sector": "Education_Sector",
        "enrolments": "Enrolments",
        "year_range": "Year_Levels",
        "phone": "Full_Phone_No",
        "website": "Website",
    },
    "NSW": {
        # NSW data source field mapping (adjust as needed)
        "school_id": "school_code",
        "name": "school_name",
        "address": "address",
        "suburb": "suburb",
        "postcode": "postcode",
        "lat": "latitude",
        "lng": "longitude",
        "school_type": "school_type",
        "gender": "gender",
        "sector": "sector",
        "enrolments": "enrolments",
        "year_range": "year_range",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import school locations into PostgreSQL")
    parser.add_argument(
        "--source",
        required=True,
        help="Path to CSV or GeoJSON file with school data",
    )
    parser.add_argument(
        "--state",
        required=True,
        choices=VALID_STATES,
        help="State abbreviation (VIC, NSW, etc.)",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Delete existing schools for this state before importing",
    )
    parser.add_argument(
        "--link-catchments",
        action="store_true",
        help="After import, link schools to their catchment zones (spatial join)",
    )
    return parser.parse_args()


def load_csv(filepath: Path, state: str) -> list[dict]:
    """Load schools from CSV using state-specific field mappings."""
    schools = []
    
    # Get field mapping for this state
    field_map = STATE_CSV_FIELD_MAPS.get(state, {})
    
    if not field_map:
        print(f"⚠️  No field mapping for state {state}. Using generic field names.", file=sys.stderr)
        field_map = {
            "school_id": "school_id",
            "name": "name",
            "address": "address",
            "suburb": "suburb",
            "postcode": "postcode",
            "lat": "lat",
            "lng": "lng",
            "school_type": "school_type",
            "gender": "gender",
            "sector": "sector",
            "enrolments": "enrolments",
            "year_range": "year_range",
            "phone": "phone",
            "website": "website",
        }
    
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Map CSV fields to internal schema using state-specific mapping
                def get_field(key: str):
                    if key == "enrolments":
                        if "Enrolments" in row: return row["Enrolments"]
                        if '"Grand Total"' in row: return row['"Grand Total"']
                        if 'Grand Total' in row: return row['Grand Total']
                    
                    csv_field = field_map.get(key)
                    if not csv_field:
                        return None
                    return row.get(csv_field)
                
                enrolments_raw = get_field("enrolments")
                enrolments_val = None
                if enrolments_raw and str(enrolments_raw).strip():
                    try:
                        enrolments_val = int(float(str(enrolments_raw).strip().replace(",", "")))
                    except ValueError:
                        pass
                
                lat_raw = get_field("lat")
                lng_raw = get_field("lng")
                
                school = {
                    "school_id": get_field("school_id"),
                    "name": get_field("name"),
                    "address": get_field("address"),
                    "suburb": get_field("suburb"),
                    "postcode": get_field("postcode"),
                    "state": state,
                    "lat": float(lat_raw) if lat_raw and str(lat_raw).strip() not in ("NA", "None", "") else None,
                    "lng": float(lng_raw) if lng_raw and str(lng_raw).strip() not in ("NA", "None", "") else None,
                    "school_type": normalize_school_type(get_field("school_type")),
                    "gender": normalize_gender(get_field("gender")),
                    "sector": normalize_sector(get_field("sector")),
                    "enrolments": enrolments_val,
                    "year_range": get_field("year_range"),
                    "website": get_field("website"),
                    "phone": get_field("phone"),
                }
                
                # We only need school_id for merging; full validation happens later
                if not school["school_id"]:
                    continue
                
                schools.append(school)
            except (KeyError, ValueError) as e:
                school_no = row.get("School_No", "Unknown")
                print(f"⚠️  Skipping row {school_no} in {filepath.name} due to error: {e}", file=sys.stderr)
    
    return schools


def load_geojson(filepath: Path, state: str) -> list[dict]:
    """Load schools from GeoJSON."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    schools = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        coords = geom.get("coordinates", [])
        
        if len(coords) != 2:
            print(f"⚠️  Skipping feature with invalid coordinates: {coords}", file=sys.stderr)
            continue
        
        try:
            school = {
                "school_id": props.get("school_id") or props.get("id"),
                "name": props["name"],
                "address": props.get("address"),
                "suburb": props.get("suburb"),
                "postcode": props.get("postcode"),
                "state": state,
                "lng": float(coords[0]),  # GeoJSON is [lng, lat]
                "lat": float(coords[1]),
                "school_type": normalize_school_type(props.get("school_type")),
                "gender": normalize_gender(props.get("gender")),
                "sector": normalize_sector(props.get("sector")),
                "enrolments": props.get("enrolments"),
                "year_range": props.get("year_range"),
                "website": props.get("website"),
                "phone": props.get("phone"),
            }
            schools.append(school)
        except (KeyError, ValueError) as e:
            print(f"⚠️  Skipping feature due to error: {e} | Props: {props}", file=sys.stderr)
    
    return schools


def normalize_school_type(value: str | None) -> str | None:
    """Normalize school type to enum values."""
    if not value:
        return None
    value = value.strip().title()
    if value in VALID_SCHOOL_TYPES:
        return value
    # Common variations
    if value in ("Primary School", "Ps"):
        return "Primary"
    if value in ("Secondary School", "Ss", "High School", "Secondary College"):
        return "Secondary"
    if value in ("P-12", "K-12", "P-12 College"):
        return "Combined"
    return None


def normalize_gender(value: str | None) -> str | None:
    """Normalize gender to enum values."""
    if not value:
        return None
    value = value.strip().title()
    if value in VALID_GENDERS:
        return value
    if value in ("Co-Ed", "Coed", "Co-Educational"):
        return "Mixed"
    return None


def normalize_sector(value: str | None) -> str | None:
    """Normalize sector to enum values."""
    if not value:
        return None
    value = value.strip().title()
    if value in VALID_SECTORS:
        return value
    if value in ("Govt", "State", "Public"):
        return "Government"
    if value in ("Private"):
        return "Independent"
    return None


def insert_schools(conn, schools: list[dict]) -> int:
    """Bulk insert schools into database."""
    values = [
        (
            s["school_id"],
            s["name"],
            s["address"],
            s["suburb"],
            s["postcode"],
            s["state"],
            s["lng"],
            s["lat"],
            s["school_type"],
            s["gender"],
            s["sector"],
            s["enrolments"],
            s["year_range"],
            s["website"],
            s["phone"],
        )
        for s in schools
    ]
    
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO schools (
                school_id, name, address, suburb, postcode, state, geom,
                school_type, gender, sector, enrolments, year_range, website, phone
            ) VALUES %s
            ON CONFLICT (school_id, state) DO UPDATE SET
                name = EXCLUDED.name,
                address = EXCLUDED.address,
                suburb = EXCLUDED.suburb,
                postcode = EXCLUDED.postcode,
                geom = EXCLUDED.geom,
                school_type = EXCLUDED.school_type,
                gender = EXCLUDED.gender,
                sector = EXCLUDED.sector,
                enrolments = EXCLUDED.enrolments,
                year_range = EXCLUDED.year_range,
                website = EXCLUDED.website,
                phone = EXCLUDED.phone,
                updated_at = NOW()
            """,
            values,
            template="(%s, %s, %s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s, %s, %s, %s)",
        )
    
    return len(values)


def link_catchments(conn, state: str):
    """Spatial join: link each school to its catchment zone if it exists."""
    with conn.cursor() as cur:
        # First try exact name match + spatial containment (stricter)
        cur.execute(
            """
            UPDATE schools s
            SET catchment_zone_id = (
                SELECT sz.id
                FROM spatial_zones sz
                WHERE sz.zone_type = 'SCHOOL_CATCHMENT'
                  AND sz.state = s.state
                  AND sz.name = s.name  -- Exact name match
                  AND ST_Contains(sz.geom, s.geom)
                LIMIT 1
            )
            WHERE s.state = %s
              AND s.catchment_zone_id IS NULL
            """,
            (state,),
        )
        named_count = cur.rowcount
        
        # Then link by spatial containment alone for remaining unlinked schools
        # (in case zone names don't match school names exactly)
        cur.execute(
            """
            UPDATE schools s
            SET catchment_zone_id = (
                SELECT sz.id
                FROM spatial_zones sz
                WHERE sz.zone_type = 'SCHOOL_CATCHMENT'
                  AND sz.state = s.state
                  AND ST_Contains(sz.geom, s.geom)  -- Spatial containment only
                LIMIT 1
            )
            WHERE s.state = %s
              AND s.catchment_zone_id IS NULL
            """,
            (state,),
        )
        spatial_count = cur.rowcount
        
        total_linked = named_count + spatial_count
        print(f"   Linked {named_count} schools by name + spatial, {spatial_count} by spatial containment only")
        print(f"   Total linked: {total_linked}")


def main():
    args = parse_args()
    source = Path(args.source)
    
    if not source.exists():
        print(f"ERROR: File not found: {source}", file=sys.stderr)
        sys.exit(1)
    
    # Find target files
    target_files = []
    if source.is_dir():
        for child in source.iterdir():
            if child.is_file() and child.suffix.lower() in (".csv", ".geojson", ".json"):
                target_files.append(child)
        if not target_files:
            print(f"ERROR: No .csv or .geojson files found in directory: {source}", file=sys.stderr)
            sys.exit(1)
    else:
        target_files = [source]
        
    # Load schools from file(s)
    schools_by_id = {}
    for f in target_files:
        print(f"Loading schools from: {f}")
        file_schools = []
        if f.suffix.lower() == ".csv":
            file_schools = load_csv(f, args.state)
        elif f.suffix.lower() in (".geojson", ".json"):
            file_schools = load_geojson(f, args.state)
        else:
            print(f"ERROR: Unsupported file type: {f.suffix}", file=sys.stderr)
            sys.exit(1)
            
        for s in file_schools:
            sid = str(s.get("school_id")).strip()
            if not sid or sid == "None":
                continue
            if sid not in schools_by_id:
                schools_by_id[sid] = s
            else:
                for k, v in s.items():
                    if v is not None and str(v).strip() != "":
                        schools_by_id[sid][k] = v

    schools = []
    for s in schools_by_id.values():
        if not s.get("name") or s.get("lat") is None or s.get("lng") is None:
            continue
        schools.append(s)
    
    if not schools:
        print("ERROR: No schools loaded from file", file=sys.stderr)
        sys.exit(1)
    
    print(f"   Loaded {len(schools)} schools")
    
    # Connect to database
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    
    try:
        # Truncate if requested
        if args.truncate:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM schools WHERE state = %s", (args.state,))
                print(f"   Deleted {cur.rowcount} existing schools for {args.state}")
        
        # Insert schools
        print(f"Inserting {len(schools)} schools into database...")
        count = insert_schools(conn, schools)
        conn.commit()
        print(f"✅ Successfully imported {count} schools for {args.state}")
        
        # Link to catchment zones if requested
        if args.link_catchments:
            print("Linking schools to catchment zones...")
            link_catchments(conn, args.state)
            conn.commit()
        
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
