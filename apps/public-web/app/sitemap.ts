import type { MetadataRoute } from "next";

/**
 * ISR revalidation — cache the sitemap for 24 hours.
 *
 * Next.js 15+ defaults fetch to `no-store`.  Without this, every crawler
 * request to `/sitemap.xml` would trigger a live DB round-trip.  The route-
 * level `revalidate` ensures the generated XML is served from cache and
 * regenerated in the background at most once per day.
 */
export const revalidate = 86400;

const BASE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://ozpropertyreport.com";
const API_URL = process.env.INTERNAL_API_URL || "http://localhost:8080";

// ── Types for the /api/sitemap/urls response ─────────────────────────────────

type SitemapZone = {
  slug: string;
  zone_type: "SUBURB" | "SCHOOL_CATCHMENT";
  state: string;
  updated_at: string;
};

type SitemapProperty = {
  slug: string;
  updated_at: string;
};

type SitemapUrlsResponse = {
  zones: SitemapZone[];
  properties: SitemapProperty[];
};

// ── Static pages (always included) ───────────────────────────────────────────

const STATIC_PAGES: MetadataRoute.Sitemap = [
  {
    url: BASE_URL,
    lastModified: new Date(),
    changeFrequency: "daily",
    priority: 1.0,
  },
  {
    url: `${BASE_URL}/pricing`,
    lastModified: new Date(),
    changeFrequency: "monthly",
    priority: 0.5,
  },
  {
    url: `${BASE_URL}/terms-of-service`,
    lastModified: new Date(),
    changeFrequency: "monthly",
    priority: 0.5,
  },
  {
    url: `${BASE_URL}/privacy-policy`,
    lastModified: new Date(),
    changeFrequency: "monthly",
    priority: 0.5,
  },
];

// ── Sitemap generator ────────────────────────────────────────────────────────

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  try {
    const res = await fetch(`${API_URL}/api/sitemap/urls`, {
      next: { revalidate: 86400 },
    });

    if (!res.ok) {
      console.error(`Sitemap API returned status ${res.status}`);
      return STATIC_PAGES;
    }

    const data: SitemapUrlsResponse = await res.json();

    const zoneEntries: MetadataRoute.Sitemap = data.zones.map((zone) => ({
      url: `${BASE_URL}/${zone.zone_type === "SUBURB" ? "suburb" : "school"}/${zone.state}/${zone.slug}`,
      lastModified: new Date(zone.updated_at),
      changeFrequency: "weekly" as const,
      priority: 0.8,
    }));

    const propertyEntries: MetadataRoute.Sitemap = data.properties.map(
      (prop) => ({
        url: `${BASE_URL}/property/${prop.slug}`,
        lastModified: new Date(prop.updated_at),
        changeFrequency: "monthly" as const,
        priority: 0.6,
      }),
    );

    return [...STATIC_PAGES, ...zoneEntries, ...propertyEntries];
  } catch (error) {
    console.error("Failed to generate dynamic sitemap entries:", error);
    return STATIC_PAGES;
  }
}
