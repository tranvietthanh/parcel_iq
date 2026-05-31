## 1. Public API — Sitemap URL Endpoint

- [x] 1.1 Create `services/public-api/app/routers/sitemap.py`:
  - `router = APIRouter(tags=["sitemap"])`
  - Pydantic response models: `SitemapZone(slug, zone_type, state, updated_at)`, `SitemapProperty(slug, updated_at)`, `SitemapUrlsResponse(zones, properties)`
  - `GET /urls` endpoint:
    - Query 1 (zones): `SELECT slug, zone_type, LOWER(state) AS state, COALESCE(updated_at, created_at, NOW()) AS updated_at FROM spatial_zones WHERE zone_type IN ('SUBURB', 'SCHOOL_CATCHMENT') AND slug IS NOT NULL AND slug != '' ORDER BY zone_type, state, slug`
    - Query 2 (properties — deduplicated via GROUP BY to handle multiple READY reports per property): `SELECT p.slug, COALESCE(GREATEST(p.updated_at, pr.updated_at), p.created_at, NOW()) AS updated_at FROM properties p INNER JOIN (SELECT property_id, MAX(updated_at) AS updated_at FROM property_reports WHERE status = 'READY' GROUP BY property_id) pr ON pr.property_id = p.id WHERE p.slug IS NOT NULL AND p.slug != '' ORDER BY p.slug`
    - Return `SitemapUrlsResponse` with both lists
    - Rate limit: `60/hour` (generous enough for ISR revalidation across pods + local dev)
    - No auth required

- [x] 1.2 Modify `services/public-api/app/main.py`:
  - Import sitemap router: `from app.routers import sitemap`
  - Include router: `app.include_router(sitemap.router, prefix="/api/sitemap")`

## 2. Next.js — robots.txt

- [x] 2.1 Create `apps/public-web/app/robots.ts`:
  - Export default function returning `MetadataRoute.Robots`
  - Use camelCase keys per Next.js typing (`userAgent`, `allow`, `disallow`)
  - Rules:
    - `userAgent: '*'`
    - `allow: '/'`
    - `disallow: ['/api/', '/profile', '/my-properties', '/sign-in', '/sign-up', '/credits']`
  - `sitemap: '${BASE_URL}/sitemap.xml'`
  - `BASE_URL` from `process.env.NEXT_PUBLIC_SITE_URL || 'https://ozpropertyreport.com'`

## 3. Next.js — sitemap.xml

- [x] 3.1 Create `apps/public-web/app/sitemap.ts`:
  - Export `const revalidate = 86400` at route level (24-hour ISR — prevents live DB round-trip on every crawler request, since Next.js 15+ defaults fetch to `no-store`)
  - Export default async function returning `MetadataRoute.Sitemap`
  - Fetch `/api/sitemap/urls` from `INTERNAL_API_URL` with `{ next: { revalidate: 86400 } }` (server-side, no auth needed)
  - Build sitemap entries:
    - Static pages: `/`, `/pricing`, `/terms-of-service`, `/privacy-policy` — priority 1.0/0.5, changeFrequency daily/monthly
    - Suburb zones: `/suburb/${state}/${slug}` — priority 0.8, changeFrequency weekly
    - School zones: `/school/${state}/${slug}` — priority 0.8, changeFrequency weekly
    - Reported properties: `/property/${slug}` — priority 0.6, changeFrequency monthly
  - All URLs use `BASE_URL` prefix for absolute URLs
  - `lastModified` from the API response `updated_at` field
  - Handle API fetch errors gracefully (return at least static pages with `console.error` logging)

## 4. Configuration

- [x] 4.1 Add `NEXT_PUBLIC_SITE_URL` to:
  - `apps/public-web/.env.example` with value `http://localhost:3000`
  - Document in deployment guide: set to `https://ozpropertyreport.com` in production

## 5. Verification

- [x] 5.1 `GET /api/sitemap/urls` — returns 200 with JSON containing `zones` array (suburb + school_catchment entries) and `properties` array
- [x] 5.2 Verify zone entries have `slug`, `zone_type`, `state`, `updated_at` fields
- [x] 5.3 Verify property entries only include those with `READY` reports — no duplicate slugs even if a property has multiple READY reports
- [x] 5.4 Browse `/robots.txt` in dev server — returns valid robots.txt with Disallow rules and Sitemap directive
- [x] 5.5 Browse `/sitemap.xml` in dev server — returns valid XML sitemap with `<urlset>` containing `<url>` entries
- [x] 5.6 Verify sitemap contains static page URLs (`/`, `/pricing`, `/terms-of-service`, `/privacy-policy`)
- [x] 5.7 Verify sitemap contains suburb URLs in format `http://localhost:3000/suburb/vic/werribee-vic`
- [x] 5.8 Verify sitemap contains school URLs in format `http://localhost:3000/school/vic/suzanne-cory-high-school-vic`
- [x] 5.9 Verify sitemap contains property URLs only for properties with completed reports
- [x] 5.10 Validate sitemap XML with an online sitemap validator (e.g., xml-sitemaps.com/validate)
- [x] 5.11 Test with no reported properties — sitemap should still include static pages + zones without errors
- [x] 5.12 Test API error handling — if `/api/sitemap/urls` fails, sitemap.ts should return at least the static pages
