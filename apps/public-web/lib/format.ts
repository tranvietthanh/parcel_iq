/**
 * Shared formatting utilities for Australian locale display values.
 */

export const formatCurrency = (val: number | null | undefined): string => {
  if (val === null || val === undefined) return "—";
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: "AUD",
    maximumFractionDigits: 0,
  }).format(val);
};

export const formatNumber = (val: number | null | undefined): string => {
  if (val === null || val === undefined) return "—";
  return Math.round(val).toLocaleString("en-AU");
};
