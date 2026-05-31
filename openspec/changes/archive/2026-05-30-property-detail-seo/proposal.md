## Why

Property detail pages at `/property/[slug]` currently render exclusively inside a `SharedMapView` client component — a full-screen Mapbox canvas with a `PropertyDetail` panel that slides in from the right. The `PropertyDetail` component is marked `"use client"` and fetches data via a client-side SWR hook (`useProperty`). This means:

1. **Googlebot sees almost nothing.** The initial HTML contains no property data — just an empty `<canvas>` element and React hydration scripts. While Google can execute JavaScript, a map canvas yields zero textual content for indexing.

2. **The rich data exists but is invisible to crawlers.** Properties with completed reports (`status = 'READY'`) have detailed sections: education (nearby schools), connectivity (NBN), risk factors (flood/bushfire), zoning & planning (overlays), and demographics. All of this is fetched client-side and rendered inside the sliding panel.

3. **The page is publicly accessible.** The `/slug/{slug}/detail` API endpoint has no auth dependency. The Clerk middleware only protects `/profile(.*)`. Unauthenticated visitors (including Googlebot) can access the full PropertyDetail payload.

The fix: render a **server-side HTML summary** of property data alongside the map, so Googlebot indexes the textual content while users still get the full interactive map experience.

## What Changes

- **Modified:** Property slug page — renders a server-side `PropertySeoContent` component that outputs crawlable HTML with property address, key report data, and JSON-LD structured data. Uses a new auth-free public fetch function with ISR caching to avoid double-fetching and enable static caching.
- **New:** `PropertySeoContent` server component — receives property detail data and renders a visible summary panel with semantic HTML (text-only, no interactive elements)
- **Modified:** `generateMetadata` on property page — enhanced with report-specific descriptions, canonical URL, Open Graph tags, and JSON-LD `Place` structured data
- **No changes** to the existing `PropertyDetail` client component or `SharedMapView` — the interactive experience remains identical

## Capabilities

### New Capabilities

- `seo-property-content`: Property pages with completed reports render server-side HTML with address, zoning, risk factors, connectivity, demographics, and education data
- `structured-data-property`: JSON-LD `Place` schema with `PropertyValue` entries on property pages for accurate search engine understanding
- `enhanced-property-metadata`: `<title>`, `<meta description>`, canonical URL, and Open Graph tags include property-specific details (address, zoning code, risk level) when report data is available

### Modified Capabilities

- `seo-friendly-property-urls`: Property slug pages now render crawlable text content alongside the map, not just the map view

## Impact

**Database:** No changes.

**API:** No changes. The existing `/api/properties/slug/{slug}/detail` endpoint already returns all needed data without authentication.

**Frontend:** The property slug page gains a server-rendered content block using the visible detail panel approach — same split layout as suburb/school pages (`ZonePageLayout`). Users see a text summary next to the map. Properties without reports keep the existing full-screen map behavior.

Key design decisions:
- Server section renders a **summary view** only (no download buttons, no interactive elements). All interactive features (downloads, scrape requests, disclaimer modal) remain exclusively in the `PropertyDetail` client panel.
- The `PropertyDetail` client panel is **not auto-opened** on direct navigation when the split layout is active, since the server summary already provides context. Users can still open it via the property pin on the map.
- The existing `getPropertyData` function (which calls `auth()`) is replaced with a new `getPropertyDataPublic` function that skips auth and uses cacheable `fetch()` with ISR revalidation. This enables Next.js Request Memoization (automatic dedup between `generateMetadata` and page body) and static caching.

**Performance:** One server-side fetch per page load (deduplicated via Request Memoization), cached with 5-minute ISR revalidation. This is an internal network call within the cluster. Compared to the current implementation (which makes 2 uncached calls via `no-store`), this is a net improvement.

## Rollout Strategy

Deploy frontend changes only — no API or database changes needed. The server component uses the same API endpoint the client component already calls.
