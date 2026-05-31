"""create_properties_from_gnaf.py – Populate properties table from gnaf_addresses using thin import.

This script performs a thin import of properties from gnaf_addresses.
It copies basic fields and generates address_tokens (TSVECTOR) without performing a PostGIS spatial join.
lga_id is left as NULL and resolved lazily at report request time.

Usage:
    python create_properties_from_gnaf.py
    python create_properties_from_gnaf.py --state VIC
    python create_properties_from_gnaf.py --state VIC --limit 10000
    python create_properties_from_gnaf.py --state VIC --batch-size 1000
"""

import argparse
import os
import signal
import sys
import time

import psycopg2

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://parceliq:devpassword@localhost:5432/parceliq"
)
VALID_STATES = ("VIC", "NSW", "QLD", "SA", "WA", "TAS", "ACT", "NT")
ACTIVE_CONN: psycopg2.extensions.connection | None = None


def handle_sigint(signum, frame):
    """Try to cancel the in-flight PostgreSQL query on Ctrl+C."""
    del signum, frame
    if ACTIVE_CONN is not None:
        try:
            print("\n⚠️  Interrupt received. Cancelling active PostgreSQL query...")
            ACTIVE_CONN.cancel()
            return
        except Exception:
            pass
    raise KeyboardInterrupt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create properties from gnaf_addresses with optional state filter"
    )
    parser.add_argument(
        "--state",
        choices=VALID_STATES,
        help="Only import properties for a specific state (e.g. VIC)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of rows to import (useful for testing)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Number of properties to insert per batch (default: 1000)",
    )
    return parser.parse_args()


def connect():
    """Connect to PostgreSQL."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    except psycopg2.Error as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    global ACTIVE_CONN
    args = parse_args()

    if args.limit is not None and args.limit <= 0:
        print("❌ --limit must be a positive integer")
        sys.exit(1)
    if args.batch_size <= 0:
        print("❌ --batch-size must be a positive integer")
        sys.exit(1)

    conn = connect()
    ACTIVE_CONN = conn
    signal.signal(signal.SIGINT, handle_sigint)
    
    scope = f"state={args.state}" if args.state else "all states"
    print(f"🚀 Running thin properties import from gnaf_addresses ({scope})...")
    start_time = time.time()
    rows_inserted = 0
    total_properties = 0

    try:
        cursor = conn.cursor()

        # Quick estimate so users know the query is running expected scope.
        if args.state:
            cursor.execute("SELECT COUNT(*) FROM gnaf_addresses WHERE state = %s", (args.state,))
            source_count = cursor.fetchone()[0]
            print(f"   Source rows in gnaf_addresses for {args.state}: {source_count:,}")
        else:
            cursor.execute("SELECT COUNT(*) FROM gnaf_addresses")
            source_count = cursor.fetchone()[0]
            print(f"   Source rows in gnaf_addresses: {source_count:,}")

        print(f"Executing batched inserts with batch_size={args.batch_size:,}...")
        if args.limit:
            print(f"   Run limit: {args.limit:,} rows")

        batch_num = 0
        while True:
            if args.limit is not None:
                remaining = args.limit - rows_inserted
                if remaining <= 0:
                    break
                batch_limit = min(args.batch_size, remaining)
            else:
                batch_limit = args.batch_size

            query = r"""
            WITH next_batch AS (
                SELECT
                    ga.gnaf_pid,
                    ga.address_string,
                    ga.geom,
                    ga.state
                FROM gnaf_addresses ga
                WHERE
                    (%s IS NULL OR ga.state = %s)
                    AND NOT EXISTS (
                        SELECT 1
                        FROM properties p
                        WHERE p.gnaf_pid = ga.gnaf_pid
                    )
                ORDER BY ga.gnaf_pid
                LIMIT %s
            )
            INSERT INTO properties (
                id,
                gnaf_pid,
                address_string,
                slug,
                geom,
                state,
                address_tokens,
                created_at,
                updated_at
            )
            SELECT
                gen_random_uuid(),
                gnaf_pid,
                address_string,
                trim(both '-' from regexp_replace(
                    regexp_replace(lower(address_string), '[^a-z0-9\s-]', '', 'g'),
                    '[\s-]+', '-', 'g'
                )) || '-' || substring(md5(gnaf_pid) from 1 for 8),
                geom,
                state,
                to_tsvector('simple', address_string),
                NOW(),
                NOW()
            FROM next_batch
            ON CONFLICT (gnaf_pid) DO NOTHING;
            """

            cursor.execute(query, (args.state, args.state, batch_limit))
            inserted = cursor.rowcount

            if inserted == 0:
                conn.commit()
                break

            conn.commit()
            rows_inserted += inserted
            batch_num += 1
            print(f"   Batch {batch_num}: inserted {inserted:,} (total {rows_inserted:,})")

        if args.state:
            cursor.execute("SELECT COUNT(*) FROM properties WHERE state = %s", (args.state,))
        else:
            cursor.execute("SELECT COUNT(*) FROM properties")
        total_properties = cursor.fetchone()[0]

        cursor.close()

    except KeyboardInterrupt:
        print("\n⚠️  Import interrupted by user. Rolling back transaction...")
        conn.rollback()
        conn.close()
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        conn.rollback()
        conn.close()
        sys.exit(1)
    finally:
        ACTIVE_CONN = None

    conn.close()

    elapsed = time.time() - start_time
    print(f"\n✅ Done!")
    print(f"   Rows inserted: {rows_inserted:,}")
    if args.state:
        print(f"   Total properties in table for {args.state}: {total_properties:,}")
    else:
        print(f"   Total properties in table: {total_properties:,}")
    print(f"   Time elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
