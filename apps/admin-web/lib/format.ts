import { format, formatDistanceToNow } from "date-fns";

/**
 * Format ISO date string to readable format.
 */
export function formatDate(isoString: string | null): string {
  if (!isoString) return "—";
  try {
    return format(new Date(isoString), "dd MMM yyyy, h:mm a");
  } catch {
    return "—";
  }
}

/**
 * Format date as relative time ("2 hours ago").
 */
export function formatRelative(isoString: string | null): string {
  if (!isoString) return "—";
  try {
    return formatDistanceToNow(new Date(isoString), { addSuffix: true });
  } catch {
    return "—";
  }
}

/**
 * Format number with thousands separator.
 */
export function formatNumber(value: number | null): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-AU").format(value);
}

/**
 * Format percentage (0-1 → 0-100%).
 */
export function formatPercent(value: number | null): string {
  if (value == null) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

/**
 * Status badge color map.
 */
export function getStatusColor(
  status: string
): "green" | "yellow" | "red" | "gray" {
  const map: Record<string, "green" | "yellow" | "red" | "gray"> = {
    completed: "green",
    approved: "green",
    running: "yellow",
    pending: "yellow",
    review_required: "yellow",
    failed: "red",
    rejected: "red",
  };
  return map[status] || "gray";
}
