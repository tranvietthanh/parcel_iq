## Context

The property slug page at `apps/public-web/app/(map)/property/[slug]/page.tsx` is a Next.js App Router page inside the `(map)` route group. It currently:

1. **Server-side:** `generateMetadata` fetches property data from `/api/properties/slug/{slug}/detail` for `<title>` and `<meta description>`
2. **Client-side:** Renders `<SharedMapView>` which includes `MapContainer`, `SearchOmnibox`, `PropertyDetail` panel, and `UserAvatar`

The `PropertyDetail` client component (`components/property/PropertyDetail.tsx`) fetches data via `useProperty(propertyId, "detail")` (SWR hook) and renders:
- Address + state
- Education section (primary/secondary schools with distances)
- Connectivity section (NBN tech type, service status)
- Risk factors (flood, bushfire)
- Zoning & planning (zoning code, label, overlays)
- Demographic snapshot (population, median age, growth rates)
- Download actions (lite PDF, full PDF)

The API endpoint `/api/properties/slug/{slug}/detail` returns a `PropertyDetail` payload with all these sections. It has **no auth dependency** — the data is publicly accessible.

**Current problem:** The existing `getPropertyData` function calls `auth()` from `@clerk/nextjs/server` and passes the token to `serverApiRequest`, which uses `cache: "no-store"`. This means:
- Every SSR request calls `auth()` even though the endpoint doesn't require it, opting the page out of static generation/ISR
- `generateMetadata` and the page body both call `getPropertyData`, resulting in **2 uncached API calls** per request (Next.js Request Memoization doesn't work with `no-store`)

## Goals / Non-Goals

**Goals**
- Property pages with completed reports render key data as server-side HTML
- HTML is crawlable by Googlebot and contains meaningful text for indexing
- JSON-LD `Place` structured data with `PropertyValue` entries for accurate search engine understanding
- Canonical URL and Open Graph tags for proper deduplication and social sharing
- Existing interactive map + panel experience is not affected
- Server-rendered content is visible to both users and crawlers
- Single deduplicated API fetch per render (via Next.js Request Memoization) with ISR caching

**Non-Goals**
- Replacing the `PropertyDetail` client component (it stays for the interactive experience)
- Adding new API endpoints (existing endpoint provides all needed data)
- Rendering download buttons or interactive elements in the server component (those stay client-only)
- Properties without reports (they have no data to render — page shows map + "request data" CTA as before)
- Adding `noindex` to no-report pages (out of scope — could be a follow-up thin-content improvement)

## Decisions

### Decision 1: Auth-free public fetch with ISR caching

Replace the existing `getPropertyData` (which calls `auth()` + uses `no-store`) with a new `getPropertyDataPublic` function that:
1. Does **not** call `auth()` — the endpoint has no auth dependency
2. Uses cacheable `fetch()` with `next: { revalidate: 300 }` (5-minute ISR)
3. Enables Next.js Request Memoization — `generateMetadata` and the page body share the same fetch automatically

```tsx
const SERVER_API_URL = process.env.INTERNAL_API_URL ?? "http://localhost:8080";

async function getPropertyDataPublic(slug: string): Promise<PropertyDetail | null> {
  const res = await fetch(
    `${SERVER_API_URL}/api/properties/slug/${slug}/detail`,
    { next: { revalidate: 300 } }
  );
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}
```

This is a net performance improvement over the current implementation.

### Decision 2: Server-rendered detail section alongside the map

For properties with report data (`report_status === 'READY'`), render a visible detail section as HTML alongside the map. For properties without reports, render only the map with a brief meta description.

Layout approach: same split layout as suburb/school pages using `ZonePageLayout`.

```
Properties WITH report:
┌──────────────────────────┬─────────────────────┐
│                          │  Server-rendered:    │
│        Map Canvas        │  - Address (h1)      │
│      (flex: 1)           │  - Zoning code/label │
│                          │  - Risk factors      │
│                          │  - NBN connectivity  │
│                          │  - Demographics      │
│                          │  - Schools nearby    │
└──────────────────────────┴─────────────────────┘
         (client)                (server only)

Properties WITHOUT report:
┌──────────────────────────────────────────────────┐
│                                                  │
│              Full-screen Map                     │
│              (existing behavior)                 │
│                                                  │
└──────────────────────────────────────────────────┘
```

The server-rendered section includes **only static text content**. No download buttons, no scrape request buttons, no disclaimer modal. All interactive elements remain exclusively in the `PropertyDetail` client component.

### Decision 3: Avoid double data display — suppress auto-open panel

The server-rendered section and the `PropertyDetail` client panel would show overlapping data in two places. To handle this:

- The server section renders a **summary view** — key stats at a glance (zoning code, risk levels, NBN type, demographics headline)
- The client `PropertyDetail` panel renders the **full detail** — expanded sections with all fields and interactive features
- When the split layout is active (property has report data), the `PropertyDetail` panel is **NOT auto-opened** on direct navigation. The server summary already provides context. Users can still open the full panel by clicking the property pin on the map.
- When no split layout (no report), existing auto-open behavior is preserved.

This avoids the current `PropertyDetail` panel (which is `fixed right-0 top-0 z-40 h-full w-full max-w-md`) overlapping the server-rendered content in the right column of the split layout.

### Decision 4: PropertySeoContent server component

Create a server component that takes property data (fetched at the page level) and renders semantic HTML:

```tsx
// Server component — no "use client"
export default function PropertySeoContent({ property }: { property: PropertyDetail }) {
  return (
    <article aria-label={`Property details for ${property.address}`}>
      <h1>{property.address}</h1>
      <dl>
        <dt>Zoning</dt>
        <dd>{property.zoning_and_planning?.zoning_code} — {property.zoning_and_planning?.zoning_label}</dd>
        <dt>Flood Risk</dt>
        <dd>{property.risk_factors?.flood?.risk}</dd>
        ...
      </dl>
      <script type="application/ld+json">{JSON.stringify(jsonLd)}</script>
    </article>
  );
}
```

### Decision 5: JSON-LD structured data — `Place` schema

Use `Place` as the primary schema type (not `RealEstateListing`). OZ Property Report is a property intelligence platform, not a real estate marketplace — `RealEstateListing` expects fields like `offers`, `price`, `datePosted` which don't apply. Using it would be misleading to crawlers.

`Place` is consistent with what the suburb page already uses and accurately represents a geographic location with property attributes.

```json
{
  "@context": "https://schema.org",
  "@type": "Place",
  "name": "8 St Lawrence Close, Werribee VIC 3030",
  "url": "https://ozpropertyreport.com/property/8-st-lawrence-close-werribee-vic-3030",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "8 St Lawrence Close",
    "addressLocality": "Werribee",
    "addressRegion": "VIC",
    "postalCode": "3030",
    "addressCountry": "AU"
  },
  "geo": {
    "@type": "GeoCoordinates",
    "latitude": -37.89,
    "longitude": 144.66
  },
  "additionalProperty": [
    { "@type": "PropertyValue", "name": "Zoning Code", "value": "GRZ1" },
    { "@type": "PropertyValue", "name": "Flood Risk", "value": "LOW" },
    { "@type": "PropertyValue", "name": "NBN Technology", "value": "FTTP" }
  ]
}
```

### Decision 6: Enhanced generateMetadata with canonical + OG tags

When report data is available, enrich the meta tags with canonical URL and Open Graph tags:

```tsx
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const property = await getPropertyDataPublic(slug);

  if (!property) return { title: "Property Not Found" };

  const zoning = property.zoning_and_planning?.zoning_code;
  const floodRisk = property.risk_factors?.flood?.risk;
  const canonicalUrl = `https://ozpropertyreport.com/property/${slug}`;

  const description = zoning
    ? `${property.address}. Zoned ${zoning}. Flood risk: ${floodRisk ?? "Unknown"}. View full property intelligence report.`
    : `View property details, risks, and insights for ${property.address}.`;

  return {
    title: `${property.address} — OZ Property Report`,
    description,
    alternates: {
      canonical: canonicalUrl,
    },
    openGraph: {
      title: `${property.address} — OZ Property Report`,
      description,
      url: canonicalUrl,
      siteName: "OZ Property Report",
      type: "website",
    },
  };
}
```

## File Layout

```
apps/public-web/
├── app/(map)/property/[slug]/page.tsx          # MODIFIED: auth-free fetch, split layout, JSON-LD
├── components/property/PropertySeoContent.tsx  # NEW: server component for crawlable property data
├── lib/jsonld.ts                               # NEW: JSON-LD builder for Place schema
└── types/index.ts                              # No changes (PropertyDetail type already exists)
```

## Data Flow

### Property page load (with report)
```
Browser → /property/8-st-lawrence-close-werribee-vic-3030
  → Next.js SSR (ISR, revalidate: 300s):
    1. getPropertyDataPublic(slug) → /api/properties/slug/.../detail → PropertyDetail payload
       (deduplicated: generateMetadata + page body share the same fetch via Request Memoization)
    2. generateMetadata: enhanced <title>, <meta description>, canonical, OG tags
    3. ZonePageLayout split:
       - mapSlot: SharedMapView (client, initialPropertyId but NO auto-open panel)
       - detailSlot: PropertySeoContent (server) → <article> with address, zoning, risk, demographics
    4. JSON-LD <script> with Place schema
  → Googlebot sees: <title>, <meta>, <link rel="canonical">, <h1> address, <dl> with stats, JSON-LD
  → User sees: map + summary panel. Can click property pin to open full detail panel.
```

### Property page load (without report)
```
Browser → /property/some-new-property
  → Next.js SSR:
    1. getPropertyDataPublic(slug) → PropertyDetail with null sections
    2. generateMetadata: basic title + description + canonical
    3. Full-screen map: SharedMapView with initialPropertyId (auto-open panel preserved)
    4. PropertyDetail panel opens with "Request Property Information" CTA
  → Googlebot sees: <title>, <h1>, brief placeholder text
  → User sees: map + CTA to request data (existing behavior)
```

## Risks / Mitigations

| Risk | Mitigation |
|---|---|
| Server and client components show duplicate data | Server renders a summary; client renders full detail. Panel does not auto-open when split layout is active. |
| Property data changes after server render (report completes) | Client component refetches via SWR — panel shows latest data. ISR revalidates server content every 5 minutes. |
| JSON-LD schema validation errors | Use `Place` schema (conservative, widely supported). Test with Google Rich Results Test and Schema.org Validator. |
| Layout change (split view) affects mobile UX | Use responsive breakpoints via `ZonePageLayout`; mobile: stack map above detail. Test on viewport <640px. |
| generateMetadata double-fetches | Eliminated: `getPropertyDataPublic` uses cacheable fetch (no `no-store`), so Next.js Request Memoization deduplicates automatically. |
| PropertyDetail panel overlaps server content on desktop | Panel is not auto-opened when split layout is active. Users open it explicitly via property pin. |
| Thin content penalty for no-report pages | Out of scope. Could add `noindex` as a follow-up. Renders `<h1>` + brief message, which is minimal but not penalised. |
