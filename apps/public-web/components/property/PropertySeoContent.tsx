import React from "react";
import type { PropertyDetail } from "@/types";
import PropertyDownloadActions from "./PropertyDownloadActions";

type PropertySeoContentProps = {
  property: PropertyDetail;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function asList(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => !!item && typeof item === "object");
}

export default function PropertySeoContent({ property }: PropertySeoContentProps) {
  const education = asRecord(property.education);
  const connectivity = asRecord(property.connectivity);
  const riskFactors = asRecord(property.risk_factors);
  const zoning = asRecord(property.zoning_and_planning);
  const demographics = asRecord(property.demographic_snapshot);

  const hasReport =
    property.report_status === "READY" &&
    (education || connectivity || riskFactors || zoning || demographics);

  if (!hasReport) {
    return (
      <article className="p-6 flex flex-col gap-6 text-zinc-800 dark:text-zinc-200 bg-white dark:bg-zinc-900 min-h-full" aria-label={`Property details for ${property.address}`}>
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 text-xs font-semibold px-2 py-0.5 rounded-full uppercase">
              Property
            </span>
            <span className="bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 text-xs font-semibold px-2 py-0.5 rounded-full uppercase">
              {property.state?.toUpperCase()}
            </span>
          </div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-white tracking-tight">
            {property.address}
          </h1>
        </div>
        <div className="bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl p-4 text-sm text-zinc-600 dark:text-zinc-400 italic">
          Report not yet available
        </div>
      </article>
    );
  }

  const primarySchools = asList(education?.primary_schools).slice(0, 5);
  const secondarySchools = asList(education?.secondary_schools).slice(0, 5);
  const overlays = asList(zoning?.overlays).slice(0, 6);

  const nbnTech = String(connectivity?.nbn_tech_type ?? connectivity?.nbn_technology ?? "N/A");
  const nbnStatus = String(connectivity?.nbn_service_status ?? connectivity?.nbn_status ?? "N/A");

  const floodRisk = String(asRecord(riskFactors?.flood)?.risk ?? riskFactors?.flood_risk ?? "Unknown");
  const bushfireRisk = String(asRecord(riskFactors?.bushfire)?.risk ?? riskFactors?.bushfire_risk ?? "Unknown");

  const zoningCode = String(zoning?.zoning_code ?? "N/A");
  const zoningLabel = String(zoning?.zoning_label ?? "N/A");
  const lgaName = zoning?.lga_name ? String(zoning.lga_name) : null;
  const heritageArea = zoning?.heritage_area === true;

  const population = demographics?.total_population ? String(demographics.total_population) : "N/A";
  const medianAge = demographics?.median_age ? `${demographics.median_age} yrs` : "N/A";
  const popGrowth = demographics?.population_growth_pct_yoy !== undefined ? `${demographics.population_growth_pct_yoy}%` : "N/A";
  const houseGrowth = demographics?.house_price_growth_pct_yoy !== undefined ? `${demographics.house_price_growth_pct_yoy}%` : "N/A";

  return (
    <article className="p-6 flex flex-col gap-6 text-zinc-800 dark:text-zinc-200 bg-white dark:bg-zinc-900 min-h-full" aria-label={`Property details for ${property.address}`}>
      {/* Property Header */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 text-xs font-semibold px-2 py-0.5 rounded-full uppercase">
            Property Report
          </span>
          <span className="bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 text-xs font-semibold px-2 py-0.5 rounded-full uppercase">
            {property.state?.toUpperCase()}
          </span>
        </div>
        <h1 className="text-2xl font-bold text-zinc-900 dark:text-white tracking-tight">
          {property.address}
        </h1>
      </div>

      {/* Zoning and Planning Section */}
      {zoning && (
        <section className="flex flex-col gap-2 border-t border-zinc-200 dark:border-zinc-800 pt-4">
          <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
            Zoning and Planning
          </h2>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-zinc-400 text-xs">Zoning Code</dt>
              <dd className="font-semibold text-zinc-900 dark:text-white mt-0.5">{zoningCode}</dd>
            </div>
            <div>
              <dt className="text-zinc-400 text-xs">Zone Label</dt>
              <dd className="font-semibold text-zinc-900 dark:text-white mt-0.5">{zoningLabel}</dd>
            </div>
            {lgaName && (
              <div>
                <dt className="text-zinc-400 text-xs">LGA Name</dt>
                <dd className="font-semibold text-zinc-900 dark:text-white mt-0.5">{lgaName}</dd>
              </div>
            )}
            <div>
              <dt className="text-zinc-400 text-xs">Heritage Overlay</dt>
              <dd className="font-semibold text-zinc-900 dark:text-white mt-0.5">
                {heritageArea ? "Applies" : "Does not apply"}
              </dd>
            </div>
          </dl>
          {overlays.length > 0 && (
            <div className="mt-2">
              <span className="text-xs text-zinc-400 font-medium">Planning Overlays</span>
              <ul className="mt-1 space-y-1.5">
                {overlays.map((overlay, idx) => (
                  <li key={`overlay-${idx}`} className="text-xs text-zinc-600 dark:text-zinc-400 bg-zinc-50 dark:bg-zinc-800/50 p-2 rounded border border-zinc-100 dark:border-zinc-800">
                    <span className="font-semibold">{String(overlay.code ?? "-")}</span>: {String(overlay.summary ?? "Overlay applies")}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {/* Risk Factors Section */}
      {riskFactors && (
        <section className="flex flex-col gap-2 border-t border-zinc-200 dark:border-zinc-800 pt-4">
          <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
            Risk Factors
          </h2>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-zinc-400 text-xs">Flood Risk</dt>
              <dd className="font-semibold text-zinc-900 dark:text-white mt-0.5">{floodRisk}</dd>
            </div>
            <div>
              <dt className="text-zinc-400 text-xs">Bushfire Risk</dt>
              <dd className="font-semibold text-zinc-900 dark:text-white mt-0.5">{bushfireRisk}</dd>
            </div>
          </dl>
        </section>
      )}

      {/* Connectivity Section */}
      {connectivity && (
        <section className="flex flex-col gap-2 border-t border-zinc-200 dark:border-zinc-800 pt-4">
          <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
            Connectivity
          </h2>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-zinc-400 text-xs">NBN Technology</dt>
              <dd className="font-semibold text-zinc-900 dark:text-white mt-0.5">{nbnTech}</dd>
            </div>
            <div>
              <dt className="text-zinc-400 text-xs">Service Status</dt>
              <dd className="font-semibold text-zinc-900 dark:text-white mt-0.5">{nbnStatus}</dd>
            </div>
          </dl>
        </section>
      )}

      {/* Demographic Snapshot Section */}
      {demographics && (
        <section className="flex flex-col gap-2 border-t border-zinc-200 dark:border-zinc-800 pt-4">
          <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
            Demographic Snapshot
          </h2>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-zinc-400 text-xs">Total Population</dt>
              <dd className="font-semibold text-zinc-900 dark:text-white mt-0.5">{population}</dd>
            </div>
            <div>
              <dt className="text-zinc-400 text-xs">Median Age</dt>
              <dd className="font-semibold text-zinc-900 dark:text-white mt-0.5">{medianAge}</dd>
            </div>
            <div>
              <dt className="text-zinc-400 text-xs">Population Growth YoY</dt>
              <dd className="font-semibold text-zinc-900 dark:text-white mt-0.5">{popGrowth}</dd>
            </div>
            <div>
              <dt className="text-zinc-400 text-xs">House Price Growth YoY</dt>
              <dd className="font-semibold text-zinc-900 dark:text-white mt-0.5">{houseGrowth}</dd>
            </div>
          </dl>
        </section>
      )}

      {/* Nearby Schools Section */}
      {education && (
        <section className="flex flex-col gap-2 border-t border-zinc-200 dark:border-zinc-800 pt-4">
          <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
            Education
          </h2>
          {typeof education.nearby_schools_summary === "string" && (
            <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-1">{education.nearby_schools_summary}</p>
          )}
          <div className="flex flex-col gap-3">
            {primarySchools.length > 0 && (
              <div>
                <span className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Primary Schools</span>
                <ul className="mt-1 space-y-1">
                  {primarySchools.map((school, idx) => (
                    <li key={`primary-${idx}`} className="text-xs text-zinc-700 dark:text-zinc-300">
                      {String(school.name ?? "Unknown")} ({Number(school.distance_km ?? 0).toFixed(2)} km)
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {secondarySchools.length > 0 && (
              <div>
                <span className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Secondary Schools</span>
                <ul className="mt-1 space-y-1">
                  {secondarySchools.map((school, idx) => (
                    <li key={`secondary-${idx}`} className="text-xs text-zinc-700 dark:text-zinc-300">
                      {String(school.name ?? "Unknown")} ({Number(school.distance_km ?? 0).toFixed(2)} km)
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}

      <PropertyDownloadActions propertyId={String(property.id)} reportStatus={property.report_status ?? null} />
    </article>
  );
}
