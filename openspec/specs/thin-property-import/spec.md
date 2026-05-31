## ADDED Requirements

### Requirement: Properties are populated via thin import from gnaf_addresses
The system SHALL populate the `properties` table from `gnaf_addresses` using a simple INSERT without PostGIS spatial join. Only basic fields SHALL be copied: `gnaf_pid`, `address_string`, `geom`, `state`, and a generated `address_tokens` TSVECTOR. All other columns (`lga_id`, `suburb_id`, `beds`, `baths`, `cars`, `land_size_sqm`, `estimated_value`, `estimated_rent`) SHALL be NULL.

#### Scenario: Thin import completes within 30 minutes
- **WHEN** the thin import script runs against a fully populated `gnaf_addresses` table (~15M rows)
- **THEN** it SHALL insert all rows into `properties` within ~20 minutes
- **THEN** text search (`address_tokens`) and map bbox queries (`geom`) SHALL be immediately functional

#### Scenario: Fresh deployment with thin import
- **WHEN** the system is deployed and thin import completes
- **THEN** the map SHALL display address pins for all 15M Australian addresses
- **THEN** text search SHALL return autocomplete results for any address
- **THEN** `lga_id` SHALL be NULL on all properties (resolved lazily)

### Requirement: lga_id is resolved lazily at report request time
The system SHALL resolve `lga_id` for a property via a PostGIS `ST_Contains` query against `spatial_zones` when a report is requested and `lga_id` is NULL.

#### Scenario: Report requested for property with NULL lga_id
- **WHEN** a report request is made for a property where `lga_id IS NULL`
- **THEN** the system SHALL query `spatial_zones` for the LGA polygon containing the property's point
- **THEN** the system SHALL update the property's `lga_id` with the resolved value
- **THEN** the scrape task SHALL proceed with the resolved `lga_id`

#### Scenario: lga_id cannot be resolved
- **WHEN** the PostGIS spatial query finds no matching LGA polygon
- **THEN** the property's `lga_id` SHALL remain NULL
- **THEN** the scrape task SHALL still proceed using the property's `state` as fallback for adapter dispatch

#### Scenario: lga_id already resolved
- **WHEN** a report request is made for a property where `lga_id IS NOT NULL`
- **THEN** the system SHALL skip the spatial query and proceed directly to scraping

### Requirement: The full spatial-join properties import is removed
The 3–4 hour bulk import script that performs a PostGIS spatial join of all `gnaf_addresses` × `spatial_zones` to resolve `lga_id` upfront SHALL be replaced with the thin import. The old import script or make target SHALL be updated to use the thin import approach.

#### Scenario: Deployment uses thin import
- **WHEN** an operator runs the properties import
- **THEN** it SHALL use the thin import (no spatial join)
- **THEN** it SHALL complete in ~20 minutes for 15M rows
