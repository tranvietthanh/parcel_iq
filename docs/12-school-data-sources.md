# School Data Sources for Australia

This document lists official data sources for school locations and catchment zones by state.

---

## Victoria (VIC)

### School Locations (Point Data)
**Source:** Victorian Registration and Qualifications Authority (VRQA)  
**URL:** https://www.education.vic.gov.au/about/research/pages/datavic.aspx

**Direct Download:**
```bash
# All Victorian schools list (CSV with lat/lng)
curl -O https://www.findmyschool.vic.gov.au/data/schools.csv

# Or search DataVic for "school locations"
# https://discover.data.vic.gov.au/dataset/school-locations-2024
```

**Expected Fields:**
- `school_id`, `name`, `address`, `suburb`, `postcode`, `lat`, `lng`
- `school_type` (Primary, Secondary, Combined, Special)
- `gender` (Mixed, Boys, Girls)
- `sector` (Government, Catholic, Independent)
- `enrolments` (may be in separate dataset)

**Import Command:**
```bash
cd /home/thanhtran/Projects/parcel_iq
uv run --project infra/scripts python infra/scripts/import_schools.py \
  --source ~/Downloads/vic_schools_2024.csv \
  --state VIC \
  --link-catchments  # Links to catchment polygons if they exist
```

---

### School Catchment Zones (Polygon Data)
**Source:** Department of Education Victoria  
**URL:** https://www.findmyschool.vic.gov.au/

**Download Options:**

1. **Via DataVic (Recommended)**
   ```bash
   # Search "school zones" or "designated neighbourhood areas"
   # https://discover.data.vic.gov.au/
   # Download GeoJSON or Shapefile
   ```

2. **Via Manual Export from Find My School**
   - Visit https://www.findmyschool.vic.gov.au/
   - Export catchment boundaries (if available)
   - Save as GeoJSON

**Import Command:**
```bash
cd /home/thanhtran/Projects/parcel_iq
uv run --project infra/scripts python infra/scripts/import_spatial_zones.py \
  --type SCHOOL_CATCHMENT \
  --source ~/Downloads/vic_school_zones_2024.geojson \
  --state VIC
```

---

## New South Wales (NSW)

### School Locations (Point Data)
**Source:** NSW Department of Education  
**URL:** https://data.cese.nsw.gov.au/

**Direct Link:**
```bash
# Master Dataset of NSW Government Schools
curl -O https://data.cese.nsw.gov.au/data/dataset/nsw-public-schools-master-dataset/resource/master-dataset.csv

# Or visit: https://data.nsw.gov.au/
# Search: "school locations"
```

**Import Command:**
```bash
uv run --project infra/scripts python infra/scripts/import_schools.py \
  --source ~/Downloads/nsw_schools_2024.csv \
  --state NSW
```

---

### School Catchment Zones (Polygon Data)
**Source:** NSW Department of Education  
**URL:** https://education.nsw.gov.au/school-finder

**Download:**
- Catchment data is less publicly available in NSW
- May need to request from: schoolenrolments@det.nsw.edu.au
- Or scrape from school finder tool (check licensing)

**Alternative:** Use FindMySchool API (if available)

---

## Queensland (QLD)

### School Locations
**Source:** Queensland Government Open Data Portal  
**URL:** https://www.qld.gov.au/education/schools/find

**Download:**
```bash
# QLD Schools Directory
# https://data.qld.gov.au/dataset/schools-directory
curl -O https://data.qld.gov.au/dataset/.../schools.csv
```

### Catchment Zones
**Note:** QLD uses "enrolment management plans" instead of strict catchments.  
Check: https://qldschools.eq.edu.au/

---

## South Australia (SA)

**Source:** SA Department for Education  
**URL:** https://data.sa.gov.au/

Search for "school locations" in the open data portal.

---

## Western Australia (WA)

**Source:** WA Department of Education  
**URL:** https://data.wa.gov.au/

Search for "school" in the catalogue.

**School Finder:** https://www.education.wa.edu.au/find-a-school

---

## Tasmania (TAS)

**Source:** Tasmanian Department of Education  
**URL:** https://www.education.tas.gov.au/

School data is less centralized — may need to:
1. Email: schoolops@decyp.tas.gov.au
2. Or scrape from school finder

---

## Australian Capital Territory (ACT)

**Source:** ACT Education Directorate  
**URL:** https://www.data.act.gov.au/

Search for "school locations".

---

## Northern Territory (NT)

**Source:** NT Department of Education  
**URL:** https://nt.gov.au/learning/primary-and-secondary-students/find-a-government-school

Data may require direct request.

---

## National Alternative: ACARA My School Database

**Source:** Australian Curriculum, Assessment and Reporting Authority  
**URL:** https://www.myschool.edu.au/

- Contains **all Australian schools** (government + non-government)
- Has lat/lng, enrolments, ICSEA scores, etc.
- **No official API or bulk download** — would need to scrape (check legal)

**Manual Export:**
1. Search for a school
2. Export school list (limited to 100 at a time)
3. Combine exports into CSV

---

## Recommended Workflow

1. **Start with VIC + NSW** (largest states, best data availability)
   ```bash
   # Download VIC school locations
   curl -O https://www.findmyschool.vic.gov.au/data/schools.csv
   
   # Import to database
   make db-migrate  # Run migration 019 first
   uv run --project infra/scripts python infra/scripts/import_schools.py \
     --source ~/Downloads/vic_schools_2024.csv --state VIC
   ```

2. **Import catchment zones separately**
   ```bash
   # If you have catchment polygon data:
   uv run --project infra/scripts python infra/scripts/import_spatial_zones.py \
     --type SCHOOL_CATCHMENT --source ~/Downloads/vic_zones.geojson --state VIC
   
   # Then link schools to catchments:
   uv run --project infra/scripts python infra/scripts/import_schools.py \
     --source ~/Downloads/vic_schools_2024.csv --state VIC --link-catchments
   ```

3. **Verify import**
   ```bash
   psql $DATABASE_URL -c "SELECT state, school_type, COUNT(*) FROM schools GROUP BY state, school_type;"
   ```

---

## Data Quality Notes

- **Enrolments:** Often published annually (Feb/March)
- **Catchments:** Can change yearly — check for updates
- **Coordinates:** Most datasets use WGS84 (EPSG:4326) — script handles this
- **Missing data:** Not all schools have catchment zones (e.g., private schools)

---

## Legal Compliance

✅ **Public sector data:** Most state education departments publish school lists under open licenses (CC BY 4.0)  
⚠️ **ACARA data:** Check terms of use before scraping My School database  
✅ **Attribution:** Credit data sources in your UI (e.g., "School data © Victorian Department of Education")

