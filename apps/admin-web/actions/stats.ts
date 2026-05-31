"use server";

import { adminAction } from "@/lib/admin-action";
import type { DashboardStats } from "@/types";

/**
 * Fetch dashboard statistics.
 */
export async function getStats(): Promise<DashboardStats> {
  return adminAction<DashboardStats>("GET", "/stats");
}
