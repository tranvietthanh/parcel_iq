## Why

OZ Property Report has no `sitemap.xml` or `robots.txt`. Search engines cannot efficiently discover the thousands of crawlable pages on the site. Without a sitemap:

1. **Google relies on link discovery only.** There's no internal linking from the homepage to the 15K suburb pages or 10K school pages — they're only reachable via search-and-select on the map. Google has no path to discover them.

2. **No crawl budget guidance.** Without a sitemap telling Google which pages exist and when they were updated, Google may waste crawl budget on low-value pages or miss high-value ones entirely.

3. **No robots.txt.** Google doesn't know where the sitemap lives, and there are no crawl directives for auth-gated or API routes.

The sitemap should include:
- **Static pages:** `/`, `/pricing`, `/terms-of-service`, `/privacy-policy` (~5 URLs)
- **Suburb pages:** `/suburb/[state]/[slug]` for all SUBURB zones (~15K URLs)
- **School catchment pages:** `/school/[state]/[slug]` for all SCHOOL_CATCHMENT zones (~10K URLs)
- **Property pages with reports:** `/property/[slug]` only for properties with `report_status = 'READY'` (varies, starts small and grows)

Total: ~25K+ URLs — well within a single sitemap file (max 50K URLs per file).

## What Changes

- **New:** `apps/public-web/app/robots.ts` — Next.js dynamic `robots.txt` generation pointing to the sitemap
- **New:** `apps/public-web/app/sitemap.ts` — Next.js dynamic sitemap generation with ISR caching (24-hour revalidation)
- **New:** Public API endpoint `GET /api/sitemap/urls` — returns all slugs needed for the sitemap (zones + reported properties) in a lightweight format
- **Modified:** `services/public-api/app/main.py` — register new sitemap router

## Capabilities

### New Capabilities

- `xml-sitemap`: Dynamic XML sitemap at `/sitemap.xml` listing all indexable pages with `lastmod` timestamps
- `robots-txt`: `robots.txt` at `/robots.txt` with crawl directives and sitemap reference
- `sitemap-api`: Internal API endpoint providing all slugs for sitemap generation

## Impact

**Database:** No schema changes. New read-only queries against `spatial_zones` and `properties` + `property_reports`.

**API:** One new endpoint. Lightweight — returns only slug + state + updated_at per row. No auth required. Rate-limited at 60/hour (generous enough for ISR revalidation across multiple pods and local dev, while preventing abuse).

**Frontend:** Two new files in the app directory root. Next.js handles sitemap XML serialization and robots.txt generation natively. The sitemap route uses `export const revalidate = 86400` (24-hour ISR) so that `/sitemap.xml` is served from cache and regenerated in the background at most once per day — avoiding a live DB round-trip on every crawler request.

**Performance:** The sitemap API query is lightweight (<100ms for ~25K rows). With 24-hour ISR caching on the Next.js side, the query runs at most once per day per pod. The property query uses `GROUP BY property_id` to deduplicate rows (a property can have multiple `READY` reports from retries), preventing duplicate `<url>` entries in the sitemap.

## Future Considerations

**Sitemap splitting:** A single XML sitemap supports up to 50,000 URLs. With ~25K zones today, there's headroom but it's finite. As reported properties grow, the sitemap will eventually need splitting. Next.js supports `generateSitemaps()` for partitioning by type (e.g., `/sitemap/0.xml`, `/sitemap/1.xml`). No action needed now — revisit when total URL count approaches 40K.

## Rollout Strategy

Deploy API endpoint first, then frontend sitemap/robots files. Submit sitemap to Google Search Console after deployment. Monitor Search Console for indexing progress and any crawl errors.
