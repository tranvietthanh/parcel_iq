import type { RoiScenarios, RoiScenario } from "@/types";

type RoiScenariosSectionProps = {
  roiScenarios: RoiScenarios;
};

function formatAud(amount: number | null | undefined): string {
  if (typeof amount !== "number" || isNaN(amount)) return "N/A";
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: "AUD",
    maximumFractionDigits: 0,
  }).format(amount);
}

function formatPercent(value: number | null | undefined): string {
  if (typeof value !== "number" || isNaN(value)) return "N/A";
  return `${value.toFixed(2)}%`;
}

function getScenarioColor(label: string): {
  badge: string;
  highlight: string;
} {
  switch (label.toLowerCase()) {
    case "conservative":
      return {
        badge: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-800",
        highlight: "text-blue-700 dark:text-blue-300",
      };
    case "optimistic":
      return {
        badge: "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-950/60 dark:text-purple-300 dark:border-purple-800",
        highlight: "text-purple-700 dark:text-purple-300",
      };
    case "base":
    default:
      return {
        badge: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800",
        highlight: "text-emerald-700 dark:text-emerald-300",
      };
  }
}

export default function RoiScenariosSection({ roiScenarios }: RoiScenariosSectionProps) {
  if (!roiScenarios || typeof roiScenarios !== "object") {
    return null;
  }

  const scenarios: RoiScenario[] = Array.isArray(roiScenarios.scenarios) ? roiScenarios.scenarios : [];
  const disclaimer = roiScenarios.disclaimer;

  if (scenarios.length === 0 && !disclaimer) {
    return null;
  }

  return (
    <section
      className="rounded-xl border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900/60"
      aria-labelledby="roi-heading"
    >
      <div className="mb-4 flex items-center justify-between border-b border-zinc-100 pb-3 dark:border-zinc-800">
        <div>
          <h3 id="roi-heading" className="text-base font-semibold text-zinc-900 dark:text-white">
            Projected ROI & Cash Flow Scenarios
          </h3>
          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
            Estimated returns based on local rents, vacancy assumptions, and holding costs
          </p>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden="true" />
          Indicative Projections
        </span>
      </div>

      {/* Scenario Cards Grid */}
      {scenarios.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {scenarios.map((scenario, index) => {
            const colors = getScenarioColor(scenario.label);
            const assumptions = scenario.assumptions || {};

            return (
              <div
                key={`scenario-${index}-${scenario.label}`}
                className="flex flex-col justify-between rounded-lg border border-zinc-200/80 bg-zinc-50/50 p-4 transition-all hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-800/30 dark:hover:border-zinc-700"
              >
                <div>
                  <div className="mb-3 flex items-center justify-between">
                    <span
                      className={`rounded-md border px-2 py-0.5 text-xs font-semibold uppercase tracking-wider ${colors.badge}`}
                    >
                      {scenario.label} Case
                    </span>
                  </div>

                  <div className="space-y-2.5">
                    <div className="flex items-baseline justify-between">
                      <span className="text-xs text-zinc-500 dark:text-zinc-400">Gross Yield</span>
                      <span className="text-sm font-semibold text-zinc-900 dark:text-white">
                        {formatPercent(scenario.gross_yield_percent)}
                      </span>
                    </div>

                    <div className="flex items-baseline justify-between">
                      <span className="text-xs text-zinc-500 dark:text-zinc-400">Net Yield</span>
                      <span className={`text-sm font-semibold ${colors.highlight}`}>
                        {formatPercent(scenario.net_yield_percent)}
                      </span>
                    </div>

                    <div className="flex items-baseline justify-between border-t border-zinc-200/60 pt-2 dark:border-zinc-700/60">
                      <span className="text-xs text-zinc-500 dark:text-zinc-400">
                        Annual Cash Flow
                      </span>
                      <span className="text-sm font-bold text-zinc-900 dark:text-white">
                        {formatAud(scenario.annual_cash_flow_aud)}
                      </span>
                    </div>
                  </div>

                  {/* Key Assumptions */}
                  <div className="mt-4 border-t border-zinc-200/60 pt-3 dark:border-zinc-700/60">
                    <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                      Key Assumptions
                    </p>
                    <dl className="space-y-1 text-xs">
                      {typeof assumptions.weekly_rent_aud === "number" && !isNaN(assumptions.weekly_rent_aud) && (
                        <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                          <dt>Weekly Rent:</dt>
                          <dd className="font-medium text-zinc-900 dark:text-zinc-200">
                            {formatAud(assumptions.weekly_rent_aud)}/wk
                          </dd>
                        </div>
                      )}
                      {typeof assumptions.interest_rate_percent === "number" && !isNaN(assumptions.interest_rate_percent) && (
                        <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                          <dt>Interest Rate:</dt>
                          <dd className="font-medium text-zinc-900 dark:text-zinc-200">
                            {formatPercent(assumptions.interest_rate_percent)}
                          </dd>
                        </div>
                      )}
                      {typeof assumptions.vacancy_rate_percent === "number" && !isNaN(assumptions.vacancy_rate_percent) && (
                        <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                          <dt>Vacancy Rate:</dt>
                          <dd className="font-medium text-zinc-900 dark:text-zinc-200">
                            {formatPercent(assumptions.vacancy_rate_percent)}
                          </dd>
                        </div>
                      )}
                      {typeof assumptions.maintenance_percent === "number" && !isNaN(assumptions.maintenance_percent) && (
                        <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                          <dt>Maintenance:</dt>
                          <dd className="font-medium text-zinc-900 dark:text-zinc-200">
                            {formatPercent(assumptions.maintenance_percent)}
                          </dd>
                        </div>
                      )}
                      {typeof assumptions.council_rates_annual_aud === "number" && !isNaN(assumptions.council_rates_annual_aud) && (
                        <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                          <dt>Council Rates:</dt>
                          <dd className="font-medium text-zinc-900 dark:text-zinc-200">
                            {formatAud(assumptions.council_rates_annual_aud)}/yr
                          </dd>
                        </div>
                      )}
                      {typeof assumptions.insurance_annual_aud === "number" && !isNaN(assumptions.insurance_annual_aud) && (
                        <div className="flex justify-between text-zinc-600 dark:text-zinc-400">
                          <dt>Insurance:</dt>
                          <dd className="font-medium text-zinc-900 dark:text-zinc-200">
                            {formatAud(assumptions.insurance_annual_aud)}/yr
                          </dd>
                        </div>
                      )}
                    </dl>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Mandatory Regulatory Disclaimer Callout Box */}
      {disclaimer && (
        <div
          role="note"
          aria-label="Financial disclaimer"
          className="mt-4 rounded-lg border border-amber-200/80 bg-amber-50/60 p-3.5 text-xs text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300"
        >
          <div className="flex items-start gap-2">
            <span className="shrink-0 text-sm" aria-hidden="true">
              ⚖️
            </span>
            <div className="space-y-1">
              <strong className="font-semibold text-amber-950 dark:text-amber-200">
                General Financial & Regulatory Disclaimer:
              </strong>
              <p className="leading-relaxed opacity-95">{disclaimer}</p>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
