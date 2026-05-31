import React from "react";
import { auth } from "@clerk/nextjs/server";
import { serverApiRequest } from "@/lib/api-server";
import { formatNumber } from "@/lib/format";
import { SchoolData } from "@/types";

type SchoolDetailPanelProps = {
  zoneId: string;
  zoneName: string;
  state: string;
};

export default async function SchoolDetailPanel({
  zoneId,
  zoneName,
  state,
}: SchoolDetailPanelProps) {
  let school: SchoolData | null = null;

  const { getToken } = await auth();

  // 1. Fetch school metadata (can return 404 if no school linked)
  try {
    school = await serverApiRequest<SchoolData>(
      `/api/schools/by-catchment/${zoneId}`,
      getToken,
    );
  } catch (err: any) {
    if (err?.status === 404) {
      console.log(`No school found for catchment zone ${zoneId}`);
    } else {
      console.error("Error fetching school data:", err);
    }
  }

  const titleName = school?.name || zoneName || "School Catchment";

  return (
    <div className="p-6 flex flex-col gap-6 text-zinc-800 dark:text-zinc-200 bg-white dark:bg-zinc-900 min-h-full">
      {/* Catchment Header */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 text-xs font-semibold px-2 py-0.5 rounded-full uppercase">
            {school?.sector ? `${school.sector} ${school.school_type}` : "School Catchment"}
          </span>
          <span className="bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 text-xs font-semibold px-2 py-0.5 rounded-full uppercase">
            {state.toUpperCase()}
          </span>
        </div>
        <h1 className="text-2xl font-bold text-zinc-900 dark:text-white tracking-tight leading-tight">
          {titleName} {!(school?.name ?? "").toLowerCase().includes("catchment") && "Catchment"}
        </h1>
      </div>

      {/* School Metadata Section */}
      {school ? (
        <section className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl p-4 flex flex-col gap-4 shadow-sm">
          <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">
            School Overview
          </h2>

          <div className="flex flex-col gap-3">
            {/* Sector, Type & Gender */}
            <div className="flex flex-wrap gap-2">
              {school.sector && (
                <span className="bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 text-xs font-semibold px-2 py-0.5 rounded">
                  {school.sector}
                </span>
              )}
              {school.school_type && (
                <span className="bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 text-xs px-2 py-0.5 rounded">
                  {school.school_type} School
                </span>
              )}
              {school.gender && (
                <span className="bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 text-xs px-2 py-0.5 rounded">
                  {school.gender}
                </span>
              )}
            </div>

            {/* Enrolments and Year Range */}
            <div className="grid grid-cols-2 gap-3 border-t border-zinc-100 dark:border-zinc-800 pt-3">
              {school.enrolments !== null && (
                <div className="flex flex-col">
                  <span className="text-xs text-zinc-400">Enrolments</span>
                  <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                    {formatNumber(school.enrolments)} students
                  </span>
                </div>
              )}
              {school.year_range && (
                <div className="flex flex-col">
                  <span className="text-xs text-zinc-400">Year Range</span>
                  <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                    {school.year_range}
                  </span>
                </div>
              )}
            </div>

            {/* Contact details */}
            <div className="border-t border-zinc-100 dark:border-zinc-800 pt-3 flex flex-col gap-2">
              {school.address && (
                <div className="flex flex-col text-xs text-zinc-500 dark:text-zinc-400">
                  <span className="text-zinc-400 dark:text-zinc-500 font-medium">Address</span>
                  <span>{school.address}</span>
                </div>
              )}
              {school.phone && (
                <div className="flex flex-col text-xs text-zinc-500 dark:text-zinc-400">
                  <span className="text-zinc-400 dark:text-zinc-500 font-medium">Phone</span>
                  <a href={`tel:${school.phone}`} className="hover:text-blue-600 dark:hover:text-blue-400">
                    {school.phone}
                  </a>
                </div>
              )}
              {school.website && (
                <div className="flex flex-col text-xs text-zinc-500 dark:text-zinc-400">
                  <span className="text-zinc-400 dark:text-zinc-500 font-medium">Website</span>
                  <a
                    href={
                      school.website.startsWith("http")
                        ? school.website
                        : `https://${school.website}`
                    }
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 dark:text-blue-400 hover:underline break-all"
                  >
                    {school.website}
                  </a>
                </div>
              )}
            </div>
          </div>
        </section>
      ) : (
        <div className="bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 rounded-xl p-4 text-zinc-500 dark:text-zinc-400 text-sm italic">
          School details not available for this catchment.
        </div>
      )}
    </div>
  );
}
