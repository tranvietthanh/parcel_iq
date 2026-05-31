import { Metadata } from "next";
import { notFound } from "next/navigation";
import type { PropertyDetail } from "@/types";
import SharedMapView from "@/components/map/SharedMapView";
import ZonePageLayout from "@/components/zones/ZonePageLayout";
import PropertySeoContent from "@/components/property/PropertySeoContent";
import { getPropertyJsonLd } from "@/lib/jsonld";

type Props = {
  params: Promise<{ slug: string }>;
};

const SERVER_API_URL = process.env.INTERNAL_API_URL ?? "http://localhost:8080";
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://ozpropertyreport.com";

// ── Data fetching ────────────────────────────────────────────────────────────

async function getPropertyDataPublic(slug: string): Promise<PropertyDetail | null> {
  const res = await fetch(
    `${SERVER_API_URL}/api/properties/slug/${slug}/detail`,
    { next: { revalidate: 300 } }
  );
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function hasReportData(property: PropertyDetail): boolean {
  const has = (v: unknown) => !!v && typeof v === "object";
  return (
    property.report_status === "READY" &&
    (has(property.education) || has(property.connectivity) ||
     has(property.risk_factors) || has(property.zoning_and_planning) ||
     has(property.demographic_snapshot))
  );
}

// ── Metadata ─────────────────────────────────────────────────────────────────

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const property = await getPropertyDataPublic(slug);

  if (!property) {
    return { title: "Property Not Found" };
  }

  const canonicalUrl = `${SITE_URL}/property/${slug}`;
  const hasReport = hasReportData(property);

  let description = `View property details, risks, and insights for ${property.address}.`;

  if (hasReport) {
    const zoning = property.zoning_and_planning as Record<string, any> | null;
    const riskFactors = property.risk_factors as Record<string, any> | null;
    const zoningCode = zoning?.zoning_code;
    const flood = riskFactors?.flood && typeof riskFactors.flood === "object" ? riskFactors.flood : {};
    const floodRisk = flood.risk || riskFactors?.flood_risk;

    description = zoningCode
      ? `${property.address}. Zoned ${zoningCode}. Flood risk: ${floodRisk ?? "Unknown"}. View full property intelligence report.`
      : `${property.address}. Flood risk: ${floodRisk ?? "Unknown"}. View full property intelligence report.`;
  }

  const title = `${property.address} — OZ Property Report`;

  return {
    title,
    description,
    alternates: {
      canonical: canonicalUrl,
    },
    openGraph: {
      title,
      description,
      url: canonicalUrl,
      siteName: "OZ Property Report",
      type: "website",
    },
  };
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default async function PropertySlugPage({ params }: Props) {
  const { slug } = await params;
  const property = await getPropertyDataPublic(slug);

  if (!property) {
    notFound();
  }

  const initialCoordinates: [number, number] | null =
    property.longitude !== null && property.latitude !== null
      ? [property.longitude, property.latitude]
      : null;

  if (hasReportData(property)) {
    const jsonLd = getPropertyJsonLd(property, slug, SITE_URL);
    return (
      <>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
        <ZonePageLayout
          mapSlot={
            <SharedMapView
              initialCoordinates={initialCoordinates}
            />
          }
          detailSlot={
            <PropertySeoContent property={property} />
          }
        />
      </>
    );
  }

  return (
    <>
      <h1 className="sr-only">{property.address}</h1>
      <SharedMapView
        initialPropertyId={property.id}
        initialCoordinates={initialCoordinates}
      />
    </>
  );
}
