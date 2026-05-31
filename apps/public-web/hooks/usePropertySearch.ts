"use client";

import useSWR from "swr";
import { useApiClient } from "@/lib/api";
import type { BBox, PropertyPin, SearchSuggestion } from "@/types";

/**
 * Search properties by bounding box or text query.
 * Returns clustered pins for map display or search results for omnibox.
 * If `zoneId` is provided, only properties within that spatial zone are returned.
 */
export function usePropertySearch(bbox: BBox | null, query?: string, zoneId?: string) {
  const api = useApiClient();

  const key = bbox
    ? `/api/search?bbox=${bbox.join(",")}${zoneId ? `&zone_id=${zoneId}` : ""}`
    : query
      ? `/api/search?q=${encodeURIComponent(query)}`
      : null;

  const { data, error, isLoading } = useSWR<PropertyPin[] | SearchSuggestion[]>(
    key,
    (url: string) => api.get(url),
    {
      revalidateOnFocus: false,
      dedupingInterval: 1000,
    },
  );

  return {
    results: data ?? [],
    error,
    isLoading,
  };
}

