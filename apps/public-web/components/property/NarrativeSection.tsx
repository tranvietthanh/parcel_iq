import type { NarrativeInsights } from "@/types";

type NarrativeSectionProps = {
  narrative: NarrativeInsights;
};

type NarrativeField = {
  key: keyof NarrativeInsights;
  title: string;
  badge?: string;
};

const NARRATIVE_FIELDS: NarrativeField[] = [
  { key: "executive_summary", title: "Executive Summary", badge: "Overview" },
  { key: "zoning_summary", title: "Zoning & Development Potential", badge: "Planning" },
  { key: "demographic_story", title: "Demographic Insights", badge: "Demographics" },
  { key: "market_momentum", title: "Market Momentum & Growth", badge: "Market" },
  { key: "rental_case", title: "Rental Investment Case", badge: "Yield" },
  { key: "risk_summary", title: "Risk & Due Diligence Summary", badge: "Due Diligence" },
  { key: "investor_context", title: "Investor Context & Strategy", badge: "Strategy" },
];

export default function NarrativeSection({ narrative }: NarrativeSectionProps) {
  if (!narrative || typeof narrative !== "object") {
    return null;
  }

  const populatedFields = NARRATIVE_FIELDS.filter(
    (field) => typeof narrative[field.key] === "string" && (narrative[field.key] as string).trim().length > 0
  );

  if (populatedFields.length === 0) {
    return null;
  }

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900/60" aria-labelledby="narrative-heading">
      <div className="mb-4 flex items-center justify-between border-b border-zinc-100 pb-3 dark:border-zinc-800">
        <div>
          <h3 id="narrative-heading" className="text-base font-semibold text-zinc-900 dark:text-white">
            AI Investment Narrative
          </h3>
          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
            Synthesized intelligence from planning schemes, census data, and market metrics
          </p>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
          <span className="h-1.5 w-1.5 rounded-full bg-indigo-500" aria-hidden="true" />
          Full Report
        </span>
      </div>

      <div className="space-y-4">
        {populatedFields.map((field) => (
          <div
            key={field.key}
            className="rounded-lg bg-zinc-50/70 p-3.5 transition-colors dark:bg-zinc-800/40"
          >
            <div className="mb-1.5 flex items-center gap-2">
              <span className="rounded-md bg-zinc-200/80 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300">
                {field.badge}
              </span>
              <h4 className="text-xs font-semibold text-zinc-800 dark:text-zinc-200">
                {field.title}
              </h4>
            </div>
            <p className="text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">
              {narrative[field.key]}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
