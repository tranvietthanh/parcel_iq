type MetricCardProps = {
  label: string;
  value: number | string | null;
  prefix?: string;
  suffix?: string;
  format?: "compact" | "none";
};

/**
 * Stat tile for property metrics (beds, yield, value, etc.).
 */
export default function MetricCard({
  label,
  value,
  prefix = "",
  suffix = "",
  format = "none",
}: MetricCardProps) {
  let displayValue: string;

  if (value == null) {
    displayValue = "—";
  } else if (format === "compact" && typeof value === "number") {
    displayValue =
      prefix +
      new Intl.NumberFormat("en-AU", {
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(value) +
      suffix;
  } else {
    displayValue = `${prefix}${value}${suffix}`;
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-700 dark:bg-zinc-800">
      <p className="text-xs text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-0.5 text-lg font-semibold text-zinc-900 dark:text-white">
        {displayValue}
      </p>
    </div>
  );
}
