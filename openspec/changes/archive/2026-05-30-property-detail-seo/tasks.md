## 1. Auth-Free Public Fetch

- [x] 1.1 Create `getPropertyDataPublic(slug)` function in `apps/public-web/app/(map)/property/[slug]/page.tsx`:
  - Does NOT call `auth()` — the slug/detail endpoint has no auth dependency
  - Uses `fetch()` with `{ next: { revalidate: 300 } }` for 5-minute ISR caching
  - Enables Next.js Request Memoization (automatic dedup between `generateMetadata` and page body)
  - Returns `PropertyDetail | null` (returns null on 404)
  - Remove the old `getPropertyData` function that called `auth()` + `serverApiRequest`

## 2. Server Component — PropertySeoContent

- [x] 2.1 Create `apps/public-web/components/property/PropertySeoContent.tsx` (server component, no `"use client"`):
  - Props: `property: PropertyDetail`
  - If property has no report data (all sections null): render only `<h1>` with address + "Report not yet available" text
  - If property has report data: render semantic HTML `<article>` with `aria-label` for accessibility:
    - `<h1>` — full address
    - `<dl>` Zoning section: zoning code, zoning label, LGA name, heritage overlay status
    - `<dl>` Risk Factors: flood risk level, bushfire risk level
    - `<dl>` Connectivity: NBN tech type, service status
    - `<dl>` Demographics: population, median age, population growth YoY, house price growth YoY
    - `<ul>` Education: list of nearby primary + secondary schools with distances
    - Planning overlays list (up to 6)
  - **No interactive elements** — no download buttons, no scrape request buttons, no disclaimer modal. All interactive features stay exclusively in the `PropertyDetail` client component.

- [x] 2.2 Create JSON-LD builder function in `apps/public-web/lib/jsonld.ts`:
  - Input: `PropertyDetail`
  - Output: JSON-LD object with `@type: "Place"` (NOT `RealEstateListing`)
  - Include: `PostalAddress`, `GeoCoordinates`, and `additionalProperty` entries for zoning code, risk levels, NBN type
  - Consistent with the suburb page's `Place` schema pattern

## 3. Property Slug Page — Server-Rendered Content

- [x] 3.1 Modify `apps/public-web/app/(map)/property/[slug]/page.tsx`:
  - Replace `getPropertyData` with `getPropertyDataPublic` (no auth, cacheable fetch)
  - Fetch property data once at the page level (shared between `generateMetadata` and page body via Request Memoization)
  - If property has report data (`report_status === 'READY'` and at least one section is non-null):
    - Render `ZonePageLayout` split layout (reuse from suburb/school pages)
    - `mapSlot`: `SharedMapView` with `initialPropertyId` and `initialCoordinates`
    - `detailSlot`: `PropertySeoContent` server component
    - Render JSON-LD `<script>` tag alongside layout (same pattern as suburb page)
  - If property has no report data:
    - Render full-screen `SharedMapView` as before (existing behavior unchanged)
  - Keep `SharedMapView` with `initialPropertyId` for the map portion

- [x] 3.2 Suppress auto-open of `PropertyDetail` client panel when split layout is active:
  - When property has report data + split layout: do NOT set `initialPropertyId` on `SharedMapView` (or add a prop to suppress auto-open), so the panel doesn't overlay the server-rendered summary
  - When property has no report data: preserve existing auto-open behavior (pass `initialPropertyId` as before)

- [x] 3.3 Enhance `generateMetadata` in property slug page:
  - Use `getPropertyDataPublic` (not the old `getPropertyData`)
  - When report data is available: include zoning code and risk level in `description`
  - Add canonical URL: `alternates: { canonical: "https://ozpropertyreport.com/property/${slug}" }`
  - Add Open Graph tags: `og:title`, `og:description`, `og:url`, `og:siteName`, `og:type`
  - Example description: "8 St Lawrence Close, Werribee VIC 3030. Zoned GRZ1. Flood risk: LOW. View full property intelligence report."
  - When no report data: keep generic description, still include canonical + OG tags

## 4. Responsive Layout

- [x] 4.1 Ensure property split layout is responsive (via `ZonePageLayout`):
  - Desktop (≥1024px): side-by-side (map flex-1 + detail panel w-96)
  - Mobile (<1024px): stacked (map h-[50vh] + detail panel scrollable below)
  - Detail panel should be scrollable independently
  - `ZonePageLayout` already handles this — verify it works correctly with `PropertySeoContent`

## 5. Verification

- [x] 5.1 Browse `/property/{slug-with-ready-report}` — page shows map + server-rendered detail section with address, zoning, risk, connectivity, demographics, schools
- [x] 5.2 `curl` the property page URL — confirm property data appears in raw HTML response (not injected by JavaScript). Do NOT rely on "View Source" in Chrome alone.
- [x] 5.3 View page source — confirm `<script type="application/ld+json">` tag with `Place` schema data is present (not `RealEstateListing`)
- [x] 5.4 Browse `/property/{slug-without-report}` — page shows full-screen map with "Request Property Information" CTA (existing behavior, no split layout)
- [x] 5.5 Test `<title>` tag: property with report shows enhanced title with address; property without report shows generic title
- [x] 5.6 Test canonical URL: `<link rel="canonical">` is present on both report and no-report pages
- [x] 5.7 Test Open Graph tags: `og:title`, `og:description`, `og:url` are present in page source
- [x] 5.8 Test mobile viewport (<1024px) — map and detail section stack vertically
- [x] 5.9 Verify `PropertyDetail` client panel does NOT auto-open when split layout is active (user must click property pin to open it)
- [x] 5.10 Verify `PropertyDetail` client panel still auto-opens when no split layout (no-report property, existing behavior)
- [x] 5.11 Verify no visual duplication — server summary and client panel show different levels of detail; panel doesn't overlay the summary on desktop
- [x] 5.12 Validate JSON-LD with Google's Rich Results Test (https://search.google.com/test/rich-results) or Schema.org Validator (https://validator.schema.org/)
- [x] 5.13 Verify ISR caching works: second page load within 5 minutes should be faster (check Next.js cache headers or server logs)
