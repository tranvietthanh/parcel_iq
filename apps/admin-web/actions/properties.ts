"use server";

import { adminAction } from "@/lib/admin-action";
import type {
  PropertyListItem,
  PropertyDetail,
  PropertyReportFull,
  PropertyReportListItem,
  TriggerScrapeResponse,
  DeletePropertyReportResponse,
  PropertyReportPdfPayload,
  DeletePropertyReportPdfResponse,
} from "@/types";

export type GetPropertiesFilters = {
  state?: string;
  lga_id?: string;
  status?: string;
  search?: string;
  limit?: number;
  offset?: number;
};

export async function getProperties(
  filters: GetPropertiesFilters = {}
): Promise<PropertyListItem[]> {
  const params = new URLSearchParams();

  if (filters.state) params.append("state", filters.state);
  if (filters.lga_id) params.append("lga_id", filters.lga_id);
  if (filters.status) params.append("status", filters.status);
  if (filters.search) params.append("search", filters.search);
  if (filters.limit) params.append("limit", filters.limit.toString());
  if (filters.offset) params.append("offset", filters.offset.toString());

  const queryString = params.toString();
  const url = `/properties${queryString ? `?${queryString}` : ""}`;

  return adminAction<PropertyListItem[]>("GET", url);
}

export async function getPropertyDetail(
  propertyId: string
): Promise<PropertyDetail> {
  return adminAction<PropertyDetail>("GET", `/properties/${propertyId}`);
}

export async function getPropertyReport(
  propertyId: string,
  mode: "lite" | "full" = "lite"
): Promise<PropertyReportFull> {
  return adminAction<PropertyReportFull>(
    "GET",
    `/properties/${propertyId}/report?mode=${mode}`
  );
}

export async function getPropertyReports(
  propertyId: string
): Promise<PropertyReportListItem[]> {
  return adminAction<PropertyReportListItem[]>(
    "GET",
    `/properties/${propertyId}/reports`
  );
}

export async function getPropertyReportById(
  propertyId: string,
  reportId: string,
  mode: "lite" | "full" = "lite"
): Promise<PropertyReportFull> {
  return adminAction<PropertyReportFull>(
    "GET",
    `/reports/${reportId}`
  ).then((report) => {
    if (String(report.property_id) !== propertyId) {
      throw new Error("Report does not belong to property");
    }

    if (mode === "lite") {
      return {
        ...report,
        raw_scraped_data: null,
        llm_parsed_insights: null,
      };
    }

    return report;
  });
}

export async function getPropertyReportPdf(
  propertyId: string,
  reportId: string,
  mode: "full" | "lite" = "full"
): Promise<PropertyReportPdfPayload> {
  return adminAction<PropertyReportPdfPayload>(
    "GET",
    `/reports/${reportId}/pdf?mode=${mode}`
  ).then((payload) => {
    if (String(payload.property_id) !== propertyId) {
      throw new Error("Report does not belong to property");
    }
    return payload;
  });
}

export async function deletePropertyReport(
  propertyId: string,
  reportId: string
): Promise<DeletePropertyReportResponse> {
  return adminAction<DeletePropertyReportResponse>(
    "DELETE",
    `/properties/${propertyId}/reports/${reportId}`
  );
}

export async function deletePropertyReportPdf(
  propertyId: string,
  reportId: string,
  mode: "full" | "lite" | "all" = "all"
): Promise<DeletePropertyReportPdfResponse> {
  return adminAction<DeletePropertyReportPdfResponse>(
    "DELETE",
    `/reports/${reportId}/pdf?mode=${mode}`
  ).then((payload) => {
    if (String(payload.property_id) !== propertyId) {
      throw new Error("Report does not belong to property");
    }
    return payload;
  });
}

export async function forceRescrape(
  propertyId: string,
  priority: "NORMAL" | "HIGH" = "NORMAL"
): Promise<TriggerScrapeResponse> {
  return adminAction<TriggerScrapeResponse>(
    "POST",
    `/properties/${propertyId}/force-scrape`,
    { priority, mode: "FORCE_ALL" }
  );
}

export async function forceAiValidate(
  propertyId: string
): Promise<TriggerScrapeResponse> {
  return adminAction<TriggerScrapeResponse>(
    "POST",
    `/properties/${propertyId}/re-ai-validate`
  );
}
