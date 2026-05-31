import { Metadata } from "next";
import { auth } from "@clerk/nextjs/server";
import { notFound } from "next/navigation";
import { serverApiRequest } from "@/lib/api-server";
import SharedMapView from "@/components/map/SharedMapView";
import ZonePageLayout from "@/components/zones/ZonePageLayout";
import SchoolDetailPanel from "@/components/zones/SchoolDetailPanel";

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
    return { title: "School Catchment Not Found" };
  }
  
  const zoneName = zone.properties?.name || "School";
  const stateUpper = state.toUpperCase();
  
  // Keep metadata generation lightweight — do NOT call the school/summary
  // endpoints here since SchoolDetailPanel fetches them already.
  const description = `View the school catchment area and property data for ${zoneName}, ${stateUpper}. OZ Property Report.`;
  
  return {
    title: `${zoneName} Catchment — OZ Property Report`,
    description,
  };
}

export default async function SchoolSlugPage({ params }: Props) {
  const { state, slug } = await params;
  const zone = await getZoneData(slug);
  
  if (!zone) {
    notFound();
  }
  
  const bbox = zone.properties?.bbox;
  const zoneId = zone.properties?.id;
  const zoneName = zone.properties?.name || "School";
  const stateUpper = state.toUpperCase();
  
  const zoneOverlay = {
    id: zoneName || slug,
    geojson: {
      type: "FeatureCollection" as const,
      features: [zone],
    },
    color: "#f59e0b", // Amber color for school catchments
  };
  
  // JSON-LD structured data — rendered in the page body as a <script> tag
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "EducationalOrganization",
    "name": zoneName,
    "address": `${zoneName}, ${stateUpper}`,
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
          <SchoolDetailPanel zoneId={zoneId} zoneName={zoneName} state={state} />
        }
      />
    </>
  );
}
