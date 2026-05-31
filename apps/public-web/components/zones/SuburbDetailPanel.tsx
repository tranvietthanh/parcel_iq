import React from "react";
import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { serverApiRequest } from "@/lib/api-server";
import { formatCurrency, formatNumber } from "@/lib/format";
import { ZoneSummary } from "@/types";

type SuburbDetailPanelProps = {
  zoneId: string;
  zoneName: string;
  state: string;
};

export default async function SuburbDetailPanel({
  zoneId,
  zoneName,
  state,
}: SuburbDetailPanelProps) {
  let summary: ZoneSummary | null = null;
  let error: string | null = null;

  try {
    const { getToken } = await auth();
    summary = await serverApiRequest<ZoneSummary>(
      `/api/zones/${zoneId}/summary`,
      getToken,
    );
  } catch (err: any) {
    console.error("Error fetching zone summary:", err);
    error = "Unable to load suburb statistics at this time.";
  }

  if (error || !summary) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold text-slate-900 mb-2">
          {zoneName}, {state.toUpperCase()}
        </h1>
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 text-rose-800 text-sm">
          {error || "Data is currently unavailable."}
        </div>
      </div>
    );
  }

  const { census_stats, nearby_schools } = summary;

  const renderMiniBars = (
    title: string,
    items: Array<{ label: string; count: number }>,
  ) => {
    if (items.length === 0) {
      return null;
    }

    const maxCount = Math.max(...items.map((item) => item.count), 1);

    return (
      <div className="border-t border-zinc-800 pt-3 mt-1 flex flex-col gap-2">
        <h3 className="text-xs text-zinc-400 uppercase tracking-wider">{title}</h3>
        <ul className="flex flex-col gap-1.5">
          {items.slice(0, 6).map((item) => (
            <li key={item.label} className="text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="text-zinc-200 truncate">{item.label}</span>
                <span className="text-zinc-400 shrink-0">{formatNumber(item.count)}</span>
              </div>
              <div className="h-1.5 bg-zinc-800 rounded mt-1 overflow-hidden">
                <div
                  className="h-full bg-blue-400/70"
                  style={{ width: `${Math.max((item.count / maxCount) * 100, 4)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      </div>
    );
  };

  return (
    <div className="p-6 flex flex-col gap-6 text-zinc-800 dark:text-zinc-200 bg-white dark:bg-zinc-900 min-h-full">
      {/* Suburb Header */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 text-xs font-semibold px-2 py-0.5 rounded-full uppercase">
            Suburb
          </span>
          <span className="bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 text-xs font-semibold px-2 py-0.5 rounded-full uppercase">
            {state.toUpperCase()}
          </span>
        </div>
        <h1 className="text-2xl font-bold text-zinc-900 dark:text-white tracking-tight">
          {zoneName}
        </h1>
      </div>

      {/* Census Stats Section */}
      {census_stats && (
        <section className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 text-white flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider">
              Demographics
            </h2>
            <span className="text-[10px] bg-blue-500/20 text-blue-300 font-medium px-2 py-0.5 rounded border border-blue-500/30">
              ABS Census 2021
            </span>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col">
              <span className="text-xs text-zinc-400">Population</span>
              <span className="text-lg font-bold text-white">
                {formatNumber(census_stats.population)}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-zinc-400">Median Age</span>
              <span className="text-lg font-bold text-white">
                {census_stats.median_age ? `${census_stats.median_age} yrs` : "—"}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-zinc-400">Household Income</span>
              <span className="text-lg font-bold text-white">
                {census_stats.median_weekly_household_income
                  ? `${formatCurrency(census_stats.median_weekly_household_income)}/wk`
                  : "—"}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-zinc-400">Family Income</span>
              <span className="text-lg font-bold text-white">
                {census_stats.median_total_family_income
                  ? `${formatCurrency(census_stats.median_total_family_income)}/wk`
                  : "—"}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-zinc-400">Median Rent</span>
              <span className="text-lg font-bold text-white">
                {census_stats.median_weekly_rent
                  ? `${formatCurrency(census_stats.median_weekly_rent)}/wk`
                  : "—"}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-zinc-400">Mortgage Repayment</span>
              <span className="text-lg font-bold text-white">
                {census_stats.median_monthly_mortgage
                  ? `${formatCurrency(census_stats.median_monthly_mortgage)}/mo`
                  : "—"}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-zinc-400">Personal Income</span>
              <span className="text-lg font-bold text-white">
                {census_stats.median_total_personal_income
                  ? `${formatCurrency(census_stats.median_total_personal_income)}/wk`
                  : "—"}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-zinc-400">Born Overseas</span>
              <span className="text-lg font-bold text-white">
                {census_stats.born_overseas_pct
                  ? `${census_stats.born_overseas_pct}%`
                  : "—"}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-zinc-400">Born in Australia</span>
              <span className="text-lg font-bold text-white">
                {census_stats.born_in_australia_pct
                  ? `${census_stats.born_in_australia_pct}%`
                  : "—"}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-zinc-400">Indigenous Status</span>
              <span className="text-lg font-bold text-white">
                {census_stats.indigenous_pct
                  ? `${census_stats.indigenous_pct}%`
                  : "—"}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-zinc-400">English Only at Home</span>
              <span className="text-lg font-bold text-white">
                {census_stats.language_english_only_pct
                  ? `${census_stats.language_english_only_pct}%`
                  : "—"}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-zinc-400">Avg Household Size</span>
              <span className="text-lg font-bold text-white">
                {census_stats.average_household_size
                  ? census_stats.average_household_size.toFixed(2)
                  : "—"}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-zinc-400">Avg People / Bedroom</span>
              <span className="text-lg font-bold text-white">
                {census_stats.average_persons_per_bedroom
                  ? census_stats.average_persons_per_bedroom.toFixed(2)
                  : "—"}
              </span>
            </div>
          </div>

          {census_stats.top_birth_countries.length > 0 && (
            <div className="border-t border-zinc-800 pt-3 mt-1 flex flex-col gap-2">
              <h3 className="text-xs text-zinc-400 uppercase tracking-wider">Top Birthplaces</h3>
              <ul className="grid grid-cols-1 gap-1 text-xs text-zinc-200">
                {census_stats.top_birth_countries.slice(0, 5).map((item) => (
                  <li key={item.label} className="flex justify-between">
                    <span>{item.label}</span>
                    <span className="text-zinc-400">{formatNumber(item.count)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(census_stats.male_count !== null || census_stats.female_count !== null) && (
            <div className="border-t border-zinc-800 pt-3 mt-1 grid grid-cols-2 gap-4">
              <div className="flex flex-col">
                <span className="text-xs text-zinc-400">Male Population</span>
                <span className="text-lg font-bold text-white">{formatNumber(census_stats.male_count)}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs text-zinc-400">Female Population</span>
                <span className="text-lg font-bold text-white">{formatNumber(census_stats.female_count)}</span>
              </div>
            </div>
          )}

          {renderMiniBars("Age Profile", census_stats.age_distribution)}
          {renderMiniBars("Income Bands", census_stats.income_distribution)}
          {renderMiniBars("Labour Force", census_stats.labour_force_distribution)}
        </section>
      )}

      {/* Nearby Schools Section */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
          Schools
        </h2>
        
        {nearby_schools.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400 italic">No schools found within 5km.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {nearby_schools.map((school, idx) => (
              <div
                key={idx}
                className="bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 rounded-lg p-3 hover:border-blue-200 dark:hover:border-blue-800 transition-all flex flex-col gap-1 shadow-sm"
              >
                <div className="flex justify-between items-start">
                  <h3 className="font-semibold text-sm text-zinc-900 dark:text-white leading-snug line-clamp-1">
                    {school.catchment_slug && school.catchment_state ? (
                      <Link
                        href={`/school/${school.catchment_state.toLowerCase()}/${school.catchment_slug}`}
                        className="hover:text-blue-600 dark:hover:text-blue-400 hover:underline"
                      >
                        {school.name}
                      </Link>
                    ) : (
                      school.name
                    )}
                  </h3>
                  {school.distance_km !== null && (
                    <span className="text-[11px] text-zinc-500 dark:text-zinc-400 shrink-0 ml-2">
                      {school.distance_km} km
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-1.5 text-xs text-zinc-600 dark:text-zinc-300">
                  {school.school_type && (
                    <span className="bg-zinc-200 dark:bg-zinc-700 text-zinc-700 dark:text-zinc-200 px-1.5 py-0.5 rounded">
                      {school.school_type}
                    </span>
                  )}
                  {school.sector && (
                    <span className="bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 rounded font-medium">
                      {school.sector}
                    </span>
                  )}
                  {school.enrolments && (
                    <span>{school.enrolments} students</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
