## Context

OZ Property Report is a Next.js 15 (App Router) + FastAPI monorepo. The public website at `apps/public-web` has the following indexable route patterns:

- `/` — homepage (map view)
- `/pricing` — credit pricing page
- `/terms-of-service` — legal page
- `/privacy-policy` — legal page
- `/suburb/[state]/[slug]` — suburb detail pages (~15K from `spatial_zones WHERE zone_type = 'SUBURB'`)
- `/school/[state]/[slug]` — school catchment pages (~10K from `spatial_zones WHERE zone_type = 'SCHOOL_CATCHMENT'`)
- `/property/[slug]` — property detail pages (only those with `property_reports.status = 'READY'`)

Auth-gated routes that should NOT be indexed: `/profile`, `/my-properties`, `/sign-in`, `/sign-up`, `/credits`.

API routes at `/api/*` should not be indexed.

The production domain is `ozpropertyreport.com`. Next.js 15 supports `app/sitemap.ts` and `app/robots.ts` as native Route Handlers for sitemap and robots.txt generation.

## Goals / Non-Goals

**Goals**
- Dynamic `sitemap.xml` listing all indexable pages with `lastmod` timestamps
- `robots.txt` with crawl directives and sitemap reference
- Sitemap includes suburbs, school catchments, reported properties, and static pages
- Sitemap updates automatically as new properties get reports
- Lightweight API endpoint to feed slug data to the sitemap generator

**Non-Goals**
- Sitemapping all 15.3M properties (only those with completed reports)
- Sitemap index with multiple files (total count is well under 50K, one file suffices initially)
- Pre-generating or caching sitemaps (dynamic generation is fast enough for ~25K URLs)
- Image sitemaps or video sitemaps
- Submitting to Bing/Yandex (manual step, not automated)

## Decisions

### Decision 1: Next.js native `sitemap.ts` + `robots.ts`

Next.js App Router supports `app/sitemap.ts` which exports a default function returning `MetadataRoute.Sitemap`. This generates `/sitemap.xml` automatically. Similarly, `app/robots.ts` generates `/robots.txt`.

No third-party packages needed (no `next-sitemap`). The built-in approach is simpler and integrates with the App Router.

### Decision 2: Single API endpoint for all sitemap URLs

Rather than having the Next.js sitemap function query the database directly (which would require a database connection in the Next.js server), create a lightweight API endpoint:

```
GET /api/sitemap/urls
```

Response (JSON):
```json
{
  "zones": [
    { "slug": "werribee-vic", "zone_type": "SUBURB", "state": "vic", "updated_at": "2026-05-29T00:00:00Z" },
    { "slug": "suzanne-cory-high-school-vic", "zone_type": "SCHOOL_CATCHMENT", "state": "vic", "updated_at": "2026-05-29T00:00:00Z" }
  ],
  "properties": [
    { "slug": "8-st-lawrence-close-werribee-vic-3030", "updated_at": "2026-05-29T12:00:00Z" }
  ]
}
```

SQL:
```sql
-- Zones (suburbs + school catchments)
SELECT slug, zone_type, LOWER(state) AS state, updated_at
FROM spatial_zones
WHERE zone_type IN ('SUBURB', 'SCHOOL_CATCHMENT')
  AND slug IS NOT NULL AND slug != ''
ORDER BY zone_type, state, slug

-- Properties with reports
SELECT p.slug, p.updated_at
FROM properties p
INNER JOIN property_reports pr ON pr.property_id = p.id
WHERE pr.status = 'READY'
  AND p.slug IS NOT NULL AND p.slug != ''
ORDER BY p.updated_at DESC
```

### Decision 3: No auth, but rate-limited and internal-only

The sitemap API endpoint is public (no Clerk token needed) since it only returns slugs — no sensitive data. Rate-limited to 10/hour to prevent abuse. In practice, only the Next.js server calls this endpoint.

### Decision 4: Sitemap entry structure

Each URL entry in the sitemap includes:
- `url` — full URL (e.g., `https://ozpropertyreport.com/suburb/vic/werribee-vic`)
- `lastModified` — from the `updated_at` column
- `changeFrequency` — `weekly` for zones, `monthly` for properties, `daily` for static pages
- `priority` — `1.0` for homepage, `0.8` for suburbs/schools, `0.6` for properties, `0.5` for static pages

### Decision 5: robots.txt directives

```
User-agent: *
Allow: /
Disallow: /api/
Disallow: /profile
Disallow: /my-properties
Disallow: /sign-in
Disallow: /sign-up
Disallow: /credits

Sitemap: https://ozpropertyreport.com/sitemap.xml
```

### Decision 6: BASE_URL from environment

The sitemap needs the production domain for absolute URLs. Use `NEXT_PUBLIC_SITE_URL` (or `VERCEL_URL` as fallback):

```typescript
const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://ozpropertyreport.com';
```

This keeps the sitemap working in development (`http://localhost:3000`) and production.

## File Layout

```
services/public-api/app/
├── routers/sitemap.py                          # NEW: GET /api/sitemap/urls endpoint
└── main.py                                     # MODIFIED: register sitemap router

apps/public-web/
├── app/sitemap.ts                              # NEW: dynamic sitemap.xml
└── app/robots.ts                               # NEW: dynamic robots.txt
```

## Data Flow

```
Google requests /sitemap.xml
  → Next.js App Router → app/sitemap.ts default function
  → fetch(INTERNAL_API_URL + "/api/sitemap/urls")
  → API queries spatial_zones + properties/property_reports
  → Returns JSON: { zones: [...], properties: [...] }
  → sitemap.ts maps to MetadataRoute.Sitemap array
  → Next.js serializes to XML
  → Google receives valid sitemap XML

Google requests /robots.txt
  → Next.js App Router → app/robots.ts default function
  → Returns MetadataRoute.Robots object
  → Next.js serializes to robots.txt format
```

## API Changes

### New router: `sitemap.py`

```python
router = APIRouter(prefix="/api/sitemap", tags=["sitemap"])

@router.get("/urls")
@limiter.limit("10/hour")
async def sitemap_urls(request: Request, db = Depends(get_db)) -> dict:
    """Return all slugs for sitemap generation."""
    zones = await db.fetch("""
        SELECT slug, zone_type, LOWER(state) AS state, updated_at
        FROM spatial_zones
        WHERE zone_type IN ('SUBURB', 'SCHOOL_CATCHMENT')
          AND slug IS NOT NULL AND slug != ''
        ORDER BY zone_type, state, slug
    """)
    properties = await db.fetch("""
        SELECT p.slug, GREATEST(p.updated_at, pr.updated_at) AS updated_at
        FROM properties p
        INNER JOIN property_reports pr ON pr.property_id = p.id
        WHERE pr.status = 'READY'
          AND p.slug IS NOT NULL AND p.slug != ''
        ORDER BY p.updated_at DESC
    """)
    return {
        "zones": [dict(z) for z in zones],
        "properties": [dict(p) for p in properties],
    }
```

## Risks / Mitigations

| Risk | Mitigation |
|---|---|
| Sitemap query slow as property reports grow to thousands | Queries use indexed joins; start with no caching, add `Cache-Control: max-age=3600` if needed |
| Rate limit blocks Google's repeated crawls of sitemap.xml | 10/hour is more than enough — Google typically fetches sitemaps every few hours |
| `NEXT_PUBLIC_SITE_URL` not set in production → wrong absolute URLs | Default fallback to `https://ozpropertyreport.com`; document in deployment guide |
| Sitemap includes property URLs but property pages have no content | Depends on `property-detail-seo` change landing first; if not, property pages still have valid `<title>` + `<meta>` from `generateMetadata` |
| `updated_at` is NULL for some rows | Use `COALESCE(updated_at, created_at, NOW())` in query |
