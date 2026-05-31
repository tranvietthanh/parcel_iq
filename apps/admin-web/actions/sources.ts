"use server";

import { adminAction } from "@/lib/admin-action";
import type { DataSource } from "@/types";
import { revalidatePath } from "next/cache";

/**
 * Get all data source configurations.
 */
export async function getDataSources(): Promise<DataSource[]> {
  return adminAction<DataSource[]>("GET", "/data-sources");
}

/**
 * Create a new data source configuration.
 */
export async function createDataSource(
  data: Omit<DataSource, "id" | "last_scraped_at">
): Promise<DataSource> {
  const result = await adminAction<DataSource>("POST", "/data-sources", data);
  revalidatePath("/sources");
  return result;
}

/**
 * Update an existing data source configuration.
 */
export async function updateDataSource(
  id: string,
  data: Partial<Omit<DataSource, "id">>
): Promise<DataSource> {
  const result = await adminAction<DataSource>(
    "PUT",
    `/data-sources/${id}`,
    data
  );
  revalidatePath("/sources");
  return result;
}

/**
 * Test a data source adapter connectivity.
 */
export async function testDataSource(id: string): Promise<{
  success: boolean;
  message: string;
}> {
  return adminAction("POST", `/data-sources/${id}/test`);
}
