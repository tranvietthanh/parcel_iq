export type GeminiQuotaStats = {
  used_today: number;
  daily_limit: number;
  remaining: number;
  reset_time: string; // ISO 8601 format
};

export type DashboardStats = {
  total_properties: number;
  reports_ready: number;
  awaiting_review: number;
  failed_7d: number;
  lga_coverage: number;
  sales_mtd: number;
  revenue_mtd: number;
  gemini_quota: GeminiQuotaStats;
};

export type ScrapeHistoryItem = {
  id: string;
  clerk_admin_id: string | null;
  action: string;
  detail: string | null;
  created_at: string;
};

export type PropertyReport = {
  id: string;
  property_id: string;
  property_address: string;
  status: string;
  overall_confidence: "HIGH" | "MEDIUM" | "LOW" | null;
  updated_at: string;
  state: string | null;
};

export type DataSource = {
  id: string;
  lga_code: string;
  lga_name: string;
  adapter_name: string;
  base_url: string;
  config: Record<string, unknown>;
  last_scraped_at: string | null;
  is_active: boolean;
};

export type LGA = {
  id: string;
  name: string;
  state: string;
  total_properties?: number;
  coverage_pct?: number;
};

export type PropertyListItem = {
  id: string;
  gnaf_pid: string;
  address_string: string;
  state: string;
  lga_name: string | null;
  last_scraped_at: string | null;
  scrape_status: "NEVER_SCRAPED" | "UP_TO_DATE" | "NEEDS_REFRESH" | "FAILED";
  report_status: string | null;
  overall_confidence: "HIGH" | "MEDIUM" | "LOW" | null;
};

export type PropertyDetail = {
  id: string;
  gnaf_pid: string;
  address_string: string;
  state: string;
  lga_name: string | null;
  suburb_name: string | null;
  latitude: number;
  longitude: number;
  beds: number | null;
  baths: number | null;
  cars: number | null;
  land_size_sqm: number | null;
  estimated_value: number | null;
  estimated_rent: number | null;
  last_scraped_at: string | null;
  created_at: string;
  updated_at: string;
};

export type PropertyReportFull = {
  id: string;
  property_id: string;
  status: string;
  overall_confidence: "HIGH" | "MEDIUM" | "LOW" | null;
  raw_scraped_data: Record<string, unknown> | null;
  llm_parsed_insights: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type PropertyReportListItem = {
  id: string;
  property_id: string;
  status: string;
  overall_confidence: "HIGH" | "MEDIUM" | "LOW" | null;
  can_delete: boolean;
  created_at: string;
  updated_at: string;
};

export type TriggerScrapeResponse = {
  property_id: string;
  task_id: string | null;
  message: string;
};

export type DeletePropertyReportResponse = {
  property_id: string;
  report_id: string;
  message: string;
};

export type PropertyReportPdfPayload = {
  report_id: string;
  property_id: string;
  mode: "full" | "lite";
  filename: string;
  generated: boolean;
  content_type: string;
  pdf_base64: string;
};

export type DeletePropertyReportPdfResponse = {
  report_id: string;
  property_id: string;
  mode: "full" | "lite" | "all";
  deleted: Array<"full" | "lite">;
  message: string;
};
