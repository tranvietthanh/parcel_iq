import type { PropertyDetail } from "@/types";

export function getPropertyJsonLd(property: PropertyDetail, slug: string, siteUrl: string) {
  const addressString = property.address || "";
  let streetAddress = addressString;
  let locality = "";
  let region = property.state ? property.state.toUpperCase() : "AU";
  let postalCode = "";

  const commaIndex = addressString.lastIndexOf(",");
  if (commaIndex !== -1) {
    streetAddress = addressString.substring(0, commaIndex).trim();
    const rest = addressString.substring(commaIndex + 1).trim();
    const parts = rest.split(/\s+/);
    if (parts.length >= 2) {
      const maybePostcode = parts[parts.length - 1];
      if (/^\d{4}$/.test(maybePostcode)) {
        postalCode = maybePostcode;
        region = parts[parts.length - 2].toUpperCase();
        locality = parts.slice(0, parts.length - 2).join(" ");
      } else {
        locality = parts.join(" ");
      }
    } else {
      locality = rest;
    }
  }

  const additionalProperty: any[] = [];
  if (property.zoning_and_planning) {
    const zoning = property.zoning_and_planning as Record<string, any>;
    if (zoning.zoning_code) {
      additionalProperty.push({
        "@type": "PropertyValue",
        "name": "Zoning Code",
        "value": zoning.zoning_code,
      });
    }
  }

  if (property.risk_factors) {
    const risks = property.risk_factors as Record<string, any>;
    if (risks.flood) {
      const flood = typeof risks.flood === "object" ? risks.flood : {};
      const floodRisk = flood.risk || risks.flood_risk;
      if (floodRisk) {
        additionalProperty.push({
          "@type": "PropertyValue",
          "name": "Flood Risk",
          "value": floodRisk,
        });
      }
    }
    if (risks.bushfire) {
      const bushfire = typeof risks.bushfire === "object" ? risks.bushfire : {};
      const bushfireRisk = bushfire.risk || risks.bushfire_risk;
      if (bushfireRisk) {
        additionalProperty.push({
          "@type": "PropertyValue",
          "name": "Bushfire Risk",
          "value": bushfireRisk,
        });
      }
    }
  }

  if (property.connectivity) {
    const conn = property.connectivity as Record<string, any>;
    const nbnTech = conn.nbn_tech_type || conn.nbn_technology;
    if (nbnTech) {
      additionalProperty.push({
        "@type": "PropertyValue",
        "name": "NBN Technology",
        "value": nbnTech,
      });
    }
  }

  const jsonLd: Record<string, any> = {
    "@context": "https://schema.org",
    "@type": "Place",
    "name": addressString,
    "url": `${siteUrl}/property/${slug}`,
    "address": {
      "@type": "PostalAddress",
      ...(streetAddress ? { "streetAddress": streetAddress } : {}),
      ...(locality ? { "addressLocality": locality } : {}),
      "addressRegion": region,
      ...(postalCode ? { "postalCode": postalCode } : {}),
      "addressCountry": "AU",
    },
  };

  if (property.latitude !== null && property.longitude !== null) {
    jsonLd.geo = {
      "@type": "GeoCoordinates",
      "latitude": property.latitude,
      "longitude": property.longitude,
    };
  }

  if (additionalProperty.length > 0) {
    jsonLd.additionalProperty = additionalProperty;
  }

  return jsonLd;
}
