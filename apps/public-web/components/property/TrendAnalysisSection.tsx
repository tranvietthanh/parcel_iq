import type { DemographicTrendAnalysis } from "@/types";

type TrendAnalysisSectionProps = {
  analysis: DemographicTrendAnalysis;
};

type TrendSignalConfig = {
  label: string;
  valueKey: keyof DemographicTrendAnalysis;
  noteKey: keyof DemographicTrendAnalysis;
};

const TREND_SIGNALS: TrendSignalConfig[] = [
  {
    label: "Overall Investment Signal",
    valueKey: "overall_investment_signal",
    noteKey: "overall_investment_signal_note",
  },
  {
    label: "Population Momentum",
    valueKey: "population_momentum",
    noteKey: "population_momentum_note",
  },
  {
    label: "Migration Trend",
    valueKey: "migration_trend",
    noteKey: "migration_trend_note",
  },
  {
    label: "Housing Supply Pressure",
    valueKey: "housing_supply_pressure",
    noteKey: "housing_supply_pressure_note",
  },
  {
    label: "Price Growth Trend",
    valueKey: "price_growth_trend",
    noteKey: "price_growth_trend_note",
  },
  {
    label: "Business Health Trend",
    valueKey: "business_health_trend",
    noteKey: "business_health_trend_note",
  },
  {
    label: "Rental Demand Outlook",
    valueKey: "rental_demand_outlook",
    noteKey: "rental_demand_outlook_note",
  },
];

function getBadgeVariant(value: string | null | undefined): {
  bg: string;
  text: string;
  dot: string;
} {
  const normalized = (value ?? "").toUpperCase();
  // Positive / Growth signals
  if (
    ["POSITIVE", "ACCELERATING", "STRENGTHENING", "UNDERSUPPLY", "IMPROVING", "STRONG"].includes(
      normalized
    )
  ) {
    return {
      bg: "bg-emerald-50 dark:bg-emerald-950/60 border-emerald-200 dark:border-emerald-800",
      text: "text-emerald-700 dark:text-emerald-300",
      dot: "bg-emerald-500",
    };
  }

  // Cautionary / Weakening signals
  if (
    [
      "CAUTIONARY",
      "DECELERATING",
      "WEAKENING",
      "OVERSUPPLY",
      "NEGATIVE",
      "DETERIORATING",
      "WEAK",
    ].includes(normalized)
  ) {
    return {
      bg: "bg-rose-50 dark:bg-rose-950/60 border-rose-200 dark:border-rose-800",
      text: "text-rose-700 dark:text-rose-300",
      dot: "bg-rose-500",
    };
  }

  // Neutral / Stable
  return {
    bg: "bg-amber-50 dark:bg-amber-950/60 border-amber-200 dark:border-amber-800",
    text: "text-amber-700 dark:text-amber-300",
    dot: "bg-amber-500",
  };
}

export default function TrendAnalysisSection({ analysis }: TrendAnalysisSectionProps) {
  if (!analysis || typeof analysis !== "object") {
    return null;
  }

  const populatedSignals = TREND_SIGNALS.filter((signal) => {
    const value = analysis[signal.valueKey];
    return typeof value === "string" && value.trim().length > 0;
  });

  if (populatedSignals.length === 0) {
    return null;
  }

  return (
    <section
      className="rounded-xl border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900/60"
      aria-labelledby="trend-heading"
    >
      <div className="mb-4 flex items-center justify-between border-b border-zinc-100 pb-3 dark:border-zinc-800">
        <div>
          <h3 id="trend-heading" className="text-base font-semibold text-zinc-900 dark:text-white">
            Demographic Trend Analysis
          </h3>
          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
            Multi-year momentum and macroeconomic investment indicators
          </p>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
          Trend Signals
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {populatedSignals.map((signal) => {
          const value = analysis[signal.valueKey] as string;
          const note = analysis[signal.noteKey] as string | undefined;
          const badge = getBadgeVariant(value);
          const isOverall = signal.valueKey === "overall_investment_signal";

          return (
            <div
              key={signal.valueKey}
              className={`rounded-lg border p-3.5 transition-colors ${
                isOverall
                  ? "sm:col-span-2 border-indigo-200 bg-indigo-50/40 dark:border-indigo-800 dark:bg-indigo-950/20"
                  : "border-zinc-200/70 bg-zinc-50/50 dark:border-zinc-800/80 dark:bg-zinc-800/30"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                  {signal.label}
                </span>
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${badge.bg} ${badge.text}`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden="true" />
                  {value}
                </span>
              </div>
              {typeof note === "string" && note.trim().length > 0 && (
                <p className="mt-2 text-xs leading-relaxed text-zinc-600 dark:text-zinc-300">
                  {note}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
