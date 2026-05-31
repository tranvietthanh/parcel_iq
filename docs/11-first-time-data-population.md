# OZ Property Report – First-Time Data Population Guide

When deploying OZ Property Report for the first time, you need to populate the database with property data and geospatial boundaries. This guide walks through the complete pipeline.

---

## Overview

The data population pipeline has **3 stages**:

```
Stage 1: Import Spatial Boundaries
└─ Spatial Zones (LGA, suburbs, school catchments)
   └─ Source: Australian Bureau of Statistics (ABS) shapefiles
   └─ Output: spatial_zones table (~2,200 LGAs)

Stage 2: Import Address Data
└─ G-NAF Addresses (Australian National Address File)
   └─ Source: Geoscape Australia (open data)
   └─ Output: gnaf_addresses table (~15M addresses)

Stage 3: Create Properties
└─ Match GNAF addresses to LGAs using spatial join
   └─ Source: gnaf_addresses + spatial_zones
   └─ Output: properties table (~15M properties)
```

After these 3 stages, the admin console can trigger scrape jobs.

---

## Prerequisites

Ensure you have:
- ✅ PostgreSQL 14+ with PostGIS extension installed
- ✅ Database migrations run (`make db-migrate`)
- ✅ `uv` package manager installed
- ✅ Docker (for Redis) running (`make infra-up`)

Verify:
```bash
psql postgresql://parceliq:devpassword@localhost:5432/parceliq -c "\dt"
# Should show: spatial_zones, gnaf_addresses, properties, etc.
```

---

## Stage 1: Import Spatial Boundaries

### 1a. Download LGA Shapefiles

Get the latest LGA boundaries from ABS:

```bash
# Option 1: Download from browser
# https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/latest-release

# Save to: ~/Downloads/LGA_2025_AUST_GDA2020.zip
# Extract: unzip ~/Downloads/LGA_2025_AUST_GDA2020.zip

# Option 2: Command line (if you have wget)
cd ~/Downloads
wget https://www.abs.gov.au/ausstats/subscriber.nsf/log?openagent&lga_2025_aust_gda2020.zip

unzip LGA_2025_AUST_GDA2020.zip
# Creates: LGA_2025_AUST_GDA2020/ directory with .shp files
```

### 1b. Import into Database

```bash
cd ~/Projects/parcel_iq
make import-spatial-zones type=LGA source=~/Downloads/LGA_2025_AUST_GDA2020/LGA_2025_AUST_GDA2020.shp
```

**Expected output:**
```
Loading shapefile: .../LGA_2025_AUST_GDA2020.shp
Processing feature 1/546...
Processing feature 100/546...
...
✅ Successfully imported 546 LGAs
   Unique constraint: (zone_type, name, state) ✓
```

### 1c. Verify

```bash
psql postgresql://parceliq:devpassword@localhost:5432/parceliq -c \
  "SELECT COUNT(*), zone_type FROM spatial_zones GROUP BY zone_type;"
```

Expected output:
```
 count | zone_type
-------+-----------
   546 | LGA
```

---

## Stage 2: Import G-NAF Address Data

**⚠️ Warning: This step takes 5-10 minutes and creates 15M+ records. Plan accordingly.**

### 2a. Download G-NAF Dataset

Get the latest G-NAF file from the official source:

```bash
# Visit: https://data.gov.au/data/dataset/geocoded-national-address-file-g-naf
# Look for the CSV format download (latest release)

# Save to: ~/Downloads/gnaf_feb2026.zip (or latest month/year)
# File size: ~500MB compressed, ~2GB uncompressed

# You can also download via curl if a direct link is available:
cd ~/Downloads
# curl -O https://data.gov.au/.../gnaf_feb2026.zip  (URL varies by release)
```

### 2b. Import into Database

```bash
cd ~/Projects/parcel_iq
make import-gnaf source=~/Downloads/gnaf_feb2026.zip
```

**Expected output (watch the progress):**
```
Loading G-NAF data from: .../gnaf_feb2026.zip
Extracting and processing...
  Processing STATE_DETAIL.csv...        [████████░░] 50%
  Processing ADDRESS_DETAIL.csv...      [██████████] 100%
  Processing ADDRESS_DEFAULT_GEOCODE... [██████████] 100%
  Joining and inserting...               [██████████] 100%

✅ Successfully imported 15,349,872 addresses into gnaf_addresses table
   Time: 487 seconds (8.1 minutes)
   Rate: ~31,500 rows/sec
```

### 2c. Verify

```bash
psql postgresql://parceliq:devpassword@localhost:5432/parceliq -c \
  "SELECT COUNT(*) as total, COUNT(DISTINCT state) as states FROM gnaf_addresses;"
```

Expected output (approximately):
```
     total     | states
---------------+--------
 15,349,872    |      8
```

---

## Stage 3: Create Properties from GNAF (Thin Import)

This stage does a **thin insert** — it copies GNAF addresses into `properties` without a spatial join. `lga_id` is left NULL and resolved lazily the first time a user requests a scrape for that property.

This approach reduces Stage 3 from 3–4 hours to ~20 minutes.

### 3a. Test Run (Small Batch - Recommended First)

Test with 10,000 addresses to ensure everything works:

```bash
make create-properties limit=10000
```

**Expected output:**
```
📊 G-NAF Addresses: 15,349,872
📊 Existing Properties: 0

🚀 Creating properties from G-NAF addresses (thin insert, no spatial join)...
   Processing up to 10,000 addresses in batches of 5000

  Inserted 5,000 rows — committing...
  Inserted 10,000 rows — committing...

✅ Done!
   Total properties created: 10,000 (0 skipped)
   Time elapsed: 5.2s
```

### 3b. Full Production Run

Once verified, create all properties:

```bash
make create-properties
# No limit = process all 15M GNAF addresses
```

**Expected behavior:**
- Progress updates every batch
- Takes ~20 minutes on a modern machine
- Creates ~15.3M property records with `lga_id = NULL`
- `lga_id` is populated via PostGIS `ST_Contains` the first time each property is scraped

**Expected final output:**
```
✅ Done!
   Total properties created: 15,301,245 (0 skipped)
   Time elapsed: 1,234.5s (~20 minutes)
```

### 3c. Verify

```bash
psql postgresql://parceliq:devpassword@localhost:5432/parceliq -c \
  "SELECT COUNT(*) as total, COUNT(DISTINCT state) as states, \
          COUNT(CASE WHEN lga_id IS NOT NULL THEN 1 END) as with_lga \
   FROM properties;"
```

Expected output — `with_lga` will be 0 initially (populated on first scrape per property):
```
    total     | states | with_lga
---------------+--------+----------
 15,301,245   |      8 |        0
```

---

## Stage 4: Verify End-to-End

Once data is loaded, verify the complete system:

### 4a. Check Specific LGA

```bash
psql postgresql://parceliq:devpassword@localhost:5432/parceliq -c \
  "SELECT COUNT(*) FROM properties p \
   JOIN spatial_zones sz ON p.lga_id = sz.id \
   WHERE sz.name = 'Wyndham' AND sz.state = 'VIC';"
```

Expected output: `150000` or similar (varies by LGA size)

### 4b. Start Services

```bash
# Terminal 1: Infra
make infra-up

# Terminal 2: Admin API
make api-admin

# Terminal 3: Scraper Worker
make worker-scraper

# Terminal 4: Admin Web
cd apps/admin-web && pnpm dev
```

### 4c. Test Scrape Trigger

1. Open http://localhost:3001 (admin console)
2. Navigate to **Properties** page
3. Find any property and click **Re-scrape** to trigger an on-demand scrape
4. Or trigger via the admin API directly:
   ```bash
   # Get a property ID first
   psql postgresql://parceliq:devpassword@localhost:5432/parceliq \
     -c "SELECT id, address_string FROM properties LIMIT 1;"

   # Trigger scrape via admin API (bypasses auth)
   curl -X POST http://localhost:8082/properties/<PROPERTY_ID>/force-scrape \
     -H "Content-Type: application/json" \
     -H "X-Service-Token: dev-service-token-change-in-prod" \
     -H "X-Admin-User-Id: dev-admin" \
     -d '{"mode": "FORCE_ALL", "priority": "HIGH"}'
   ```
5. Watch Flower at http://localhost:5555 for task progress

---

## Troubleshooting

### "No properties found" when triggering scrape

**Cause:** Properties table is empty
**Fix:** Ensure Stage 3 completed successfully and check row count:
```bash
SELECT COUNT(*) FROM properties;
```

### Import script hangs or is very slow

**Cause:** Indexes are rebuilding or queries are slow
**Fix:** Check PostgreSQL logs:
```bash
docker logs postgres  # if running in Docker
# Look for VACUUM or CREATE INDEX messages
```

### "Disk space full" during GNAF import

**Cause:** 2GB uncompressed GNAF data + PostgreSQL indexes
**Fix:** Free up space and retry. You need ~50GB free for the full pipeline.

### Wrong number of properties created

**Possible causes:**
- Some GNAF addresses have NULL geometry (excluded by import script)
- Duplicate gnaf_pid values (import script uses `ON CONFLICT DO NOTHING`)

**Verify:**
```bash
SELECT COUNT(*) FROM gnaf_addresses;
SELECT COUNT(*) FROM properties;
SELECT COUNT(*) FROM gnaf_addresses WHERE geom IS NULL;
```

Note: `lga_id` will be NULL for all properties after the initial import. This is expected — it is resolved lazily via a PostGIS `ST_Contains` query the first time each property is scraped.

---

## Timeline Estimate

| Stage | Action | Time | Notes |
|-------|--------|------|-------|
| 1 | Download LGA shapefiles | 5-10 min | ~100MB download |
| 1 | Import LGAs | 1-2 min | 546 records |
| 2 | Download G-NAF | 10-30 min | ~500MB download |
| 2 | Import G-NAF | 5-10 min | 15M records, uses COPY |
| 3 | Create properties (test) | ~5 sec | 10k sample test |
| 3 | Create properties (full) | ~20 min | 15M records, thin insert (no spatial join) |
| **Total** | | **~45-60 min wall-clock** | Can run in background |

---

## What's Next?

Once data is loaded:

- **Develop scrapers**: Add council adapters to `services/scraper-worker/app/adapters/`
- **Monitor imports**: Use admin console **Scrape** and **Tasks** pages
- **Public API**: Ready to query properties via `/api/properties` endpoint
- **LLM enrichment**: Configure LLM parser for property report parsing

---

## Maintenance

### Monthly Updates

G-NAF is updated monthly. To re-import:

```bash
# Download latest gnaf_YYYY_MM.zip
make import-gnaf source=~/Downloads/gnaf_2026_03.zip

# Re-create properties (will skip existing gnaf_pids)
make create-properties limit=100000  # Test first
make create-properties              # Full run
```

### Backup After Population

```bash
# Backup the populated database
docker exec postgres pg_dump -U parceliq parceliq | gzip > parceliq_backup_2026_02_27.sql.gz
```

---

## Questions?

Refer to:
- [Database Schema Doc](../docs/04-database.md)
- [System Architecture](../docs/01-system-architecture.md)
- [Local Dev Setup](../docs/09-local-dev.md)
