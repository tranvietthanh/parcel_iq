import type { InfrastructureItem } from "@/types";

type InfrastructureListProps = {
  infrastructure: InfrastructureItem[];
};

function getTypeBadge(type: string): { bg: string; text: string } {
  switch (type.toUpperCase()) {
    case "TRANSPORT":
      return {
        bg: "bg-blue-50 dark:bg-blue-950/60 border-blue-200 dark:border-blue-800",
        text: "text-blue-700 dark:text-blue-300",
      };
    case "HEALTH":
      return {
        bg: "bg-rose-50 dark:bg-rose-950/60 border-rose-200 dark:border-rose-800",
        text: "text-rose-700 dark:text-rose-300",
      };
    case "EDUCATION":
      return {
        bg: "bg-purple-50 dark:bg-purple-950/60 border-purple-200 dark:border-purple-800",
        text: "text-purple-700 dark:text-purple-300",
      };
    case "COMMERCIAL":
      return {
        bg: "bg-emerald-50 dark:bg-emerald-950/60 border-emerald-200 dark:border-emerald-800",
        text: "text-emerald-700 dark:text-emerald-300",
      };
    default:
      return {
        bg: "bg-zinc-100 dark:bg-zinc-800 border-zinc-200 dark:border-zinc-700",
        text: "text-zinc-700 dark:text-zinc-300",
      };
  }
}

export default function InfrastructureList({ infrastructure }: InfrastructureListProps) {
  if (!Array.isArray(infrastructure) || infrastructure.length === 0) {
    return null;
  }

  return (
    <section
      className="rounded-xl border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-900/60"
      aria-labelledby="infrastructure-heading"
    >
      <div className="mb-4 flex items-center justify-between border-b border-zinc-100 pb-3 dark:border-zinc-800">
        <div>
          <h3
            id="infrastructure-heading"
            className="text-base font-semibold text-zinc-900 dark:text-white"
          >
            Nearby Infrastructure & Pipeline
          </h3>
          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
            Major transport, health, education, and community infrastructure developments
          </p>
        </div>
        <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 dark:bg-blue-950/60 dark:text-blue-300">
          {infrastructure.length} Project{infrastructure.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="space-y-3">
        {infrastructure.map((item, index) => {
          const typeStyle = getTypeBadge(item.type || "OTHER");
          const hasDistance = typeof item.distance_km === "number" && !isNaN(item.distance_km);
          const hasYear = typeof item.expected_completion_year === "number" && item.expected_completion_year > 0;

          return (
            <div
              key={`infra-${index}`}
              className="flex flex-col gap-2 rounded-lg border border-zinc-200/70 bg-zinc-50/50 p-3.5 transition-colors sm:flex-row sm:items-start sm:justify-between dark:border-zinc-800/80 dark:bg-zinc-800/30"
            >
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`inline-block rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${typeStyle.bg} ${typeStyle.text}`}
                  >
                    {item.type || "OTHER"}
                  </span>
                  {hasYear && (
                    <span className="rounded-md bg-zinc-200/80 px-2 py-0.5 text-[10px] font-medium text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300">
                      Est. {item.expected_completion_year}
                    </span>
                  )}
                  {hasDistance && (
                    <span className="text-xs text-zinc-500 dark:text-zinc-400">
                      ~{item.distance_km!.toFixed(1)} km away
                    </span>
                  )}
                </div>
                <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
                  {item.description}
                </p>
              </div>

              {item.source_url && /^https?:\/\//i.test(item.source_url) && (
                <a
                  href={item.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700 hover:underline dark:text-indigo-400 dark:hover:text-indigo-300"
                >
                  Source
                  <span aria-hidden="true">↗</span>
                </a>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
