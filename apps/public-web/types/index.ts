/* ── Search & Map ─────────────────────────────────────────── */

export type BBox = [number, number, number, number]; // [minLng, minLat, maxLng, maxLat]

export type SearchSuggestion = {
  type: string; // ADDRESS, LGA, SUBURB, SCHOOL, etc
  label: string; // display name
  property_id: string | null; // UUID for ADDRESS type
  zone_id: string | null; // UUID for zone types (LGA, SUBURB, SCHOOL)
  coordinates: [number, number] | null; // [lng, lat] for properties
  bbox: BBox | null; // bounding box for zones
  slug: string | null;
  zone_state: string | null;
};

export type TextSearchResponse = {
  suggestions: SearchSuggestion[];
};

export type BBoxSearchResponse = {
  features: Array<{
    properties: {
      id: string;
      address: string;
      report_status: string | null;
      estimated_value: number | null;
      slug: string | null;
    };
    geometry: Record<string, unknown>; // GeoJSON Point
  }>;
};

/* ── Property ────────────────────────────────────────────── */

export type PropertyDetail = {
  id: string;
  address: string;
  state: string;
  slug?: string;
  report_status: string | null;
  latitude: number | null;
  longitude: number | null;
  education: Record<string, unknown> | null;
  connectivity: Record<string, unknown> | null;
  risk_factors: Record<string, unknown> | null;
  zoning_and_planning: Record<string, unknown> | null;
  demographic_snapshot: Record<string, unknown> | null;
};

export type PropertyPin = {
  id: string;
  latitude: number;
  longitude: number;
  estimated_value: number | null;
  report_status: string | null;
  slug?: string | null;
  address?: string | null;
};

/* ── Payment ─────────────────────────────────────────────── */

export type CheckoutSession = {
  checkout_url: string;
};

export type RequestScrapeResponse = {
  status: "queued" | "processing" | "ready";
  report_status?: string;
  task_id?: string;
  message: string;
};

/* ── API ─────────────────────────────────────────────────── */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/* ── Zones & Demographics ────────────────────────────────── */

export type CensusStats = {
  population: number | null;
  male_count: number | null;
  female_count: number | null;
  median_age: number | null;
  median_weekly_household_income: number | null;
  median_total_family_income: number | null;
  median_total_personal_income: number | null;
  median_weekly_rent: number | null;
  median_monthly_mortgage: number | null;
  average_household_size: number | null;
  average_persons_per_bedroom: number | null;
  renting_pct: number | null;
  born_overseas_pct: number | null;
  born_in_australia_pct: number | null;
  indigenous_pct: number | null;
  language_english_only_pct: number | null;
  age_distribution: Array<{ label: string; count: number }>;
  top_birth_countries: Array<{ label: string; count: number }>;
  income_distribution: Array<{ label: string; count: number }>;
  labour_force_distribution: Array<{ label: string; count: number }>;
};

export type NearbySchool = {
  name: string;
  school_type: string | null;
  sector: string | null;
  enrolments: number | null;
  distance_km: number | null;
  catchment_slug: string | null;
  catchment_state: string | null;
};

export type PropertyStats = {
  total_count: number;
  with_reports: number;
  median_estimated_value: number | null;
  median_land_size_sqm: number | null;
};

export type ZoneInfo = {
  id: string;
  name: string;
  state: string;
  zone_type: string;
  slug: string;
};

export type ZoneSummary = {
  zone: ZoneInfo;
  property_stats: PropertyStats;
  nearby_schools: NearbySchool[];
  census_stats: CensusStats | null;
};

export type SchoolData = {
  id: string;
  name: string;
  address: string | null;
  suburb: string | null;
  postcode: string | null;
  state: string;
  school_type: string | null;
  gender: string | null;
  sector: string | null;
  enrolments: number | null;
  year_range: string | null;
  website: string | null;
  phone: string | null;
};

