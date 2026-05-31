"use server";

import { adminAction, getCurrentAdminId } from "@/lib/admin-action";
import type { PropertyReport } from "@/types";
import { revalidatePath } from "next/cache";

export type GetReportsFilters = {
  status?: string;

  state?: string;
  limit?: number;
  offset?: number;
};

/**
 * Get a list of property reports (with optional status filter).
 */
export async function getReports(
  filters: GetReportsFilters = {}
): Promise<PropertyReport[]> {
  const params = new URLSearchParams();

  if (filters.status) params.append("status", filters.status);

  if (filters.state) params.append("state", filters.state);
  params.append("limit", String(filters.limit ?? 100));
  if (typeof filters.offset === "number") {
    params.append("offset", String(filters.offset));
  }

  return adminAction<PropertyReport[]>("GET", `/reports?${params.toString()}`);
}

