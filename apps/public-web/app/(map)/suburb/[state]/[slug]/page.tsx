import { Metadata } from "next";
import { auth } from "@clerk/nextjs/server";
import { notFound } from "next/navigation";
import { serverApiRequest } from "@/lib/api-server";
import SharedMapView from "@/components/map/SharedMapView";
import ZonePageLayout from "@/components/zones/ZonePageLayout";
import SuburbDetailPanel from "@/components/zones/SuburbDetailPanel";

type Props = {
  params: Promise<{ state: string; slug: string }>;
};

async function getZoneData(slug: string) {
  try {
    const { getToken } = await auth();
    return await serverApiRequest<any>(
      `/api/search/zones/slug/${slug}`,
      getToken,
    );
  } catch (err: any) {
    if (err?.status === 404) return null;
    throw err;
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { state, slug } = await params;
  const zone = await getZoneData(slug);
  
  if (!zone) {
    return { title: "Suburb Not Found" };
  }
  
  const zoneName = zone.properties?.name || "Suburb";
  const stateUpper = state.toUpperCase();
  
  // Keep metadata generation lightweight — do NOT call the summary endpoint
  // here because it may trigger a slow ABS API fetch on first visit.
  // The SuburbDetailPanel handles dynamic stats rendering.
  const description = `View property market data, demographics, and nearby schools for ${zoneName}, ${stateUpper}. OZ Property Report.`;
  
  return {
    title: `${zoneName}, ${stateUpper} — Suburb Overview | OZ Property Report`,
    description,
  };
}

export default async function SuburbSlugPage({ params }: Props) {
  const { state, slug } = await params;
  const zone = await getZoneData(slug);
  
  if (!zone) {
    notFound();
  }
  
  const bbox = zone.properties?.bbox;
  const zoneId = zone.properties?.id;
  const zoneName = zone.properties?.name || "Suburb";
  const stateUpper = state.toUpperCase();
  
  const zoneOverlay = {
    id: zoneName || slug,
    geojson: {
      type: "FeatureCollection" as const,
      features: [zone],
    },
    color: "#6366f1", // Suburb zone color
  };
  
  // JSON-LD structured data — rendered in the page body as a <script> tag
  let lat = 0;
  let lng = 0;
  if (bbox && bbox.length === 4) {
    lng = (bbox[0] + bbox[2]) / 2;
    lat = (bbox[1] + bbox[3]) / 2;
  }
  
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Place",
    "name": `${zoneName}, ${stateUpper}`,
    "address": {
      "@type": "PostalAddress",
      "addressRegion": stateUpper,
      "addressCountry": "AU",
    },
    ...(lat && lng
      ? {
          "geo": {
            "@type": "GeoCoordinates",
            "latitude": lat,
            "longitude": lng,
          },
        }
      : {}),
  };
  
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <ZonePageLayout
        mapSlot={
          <SharedMapView initialBbox={bbox} zoneOverlay={zoneOverlay} zoneId={zoneId} />
        }
        detailSlot={
          <SuburbDetailPanel zoneId={zoneId} zoneName={zoneName} state={state} />
        }
      />
    </>
  );
}
