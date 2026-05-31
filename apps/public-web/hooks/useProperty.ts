"use client";

import useSWR from "swr";
import { useApiClient } from "@/lib/api";
import type { PropertyDetail } from "@/types";

/**
 * Fetch a single property by ID using the curated detail endpoint.
 */
export function useProperty(
  id: string | null,
  variant: "detail" = "detail",
) {
  const api = useApiClient();

  const key = id ? `/api/properties/${id}/${variant}` : null;

  const { data, error, isLoading, mutate } = useSWR<PropertyDetail>(
    key,
    (url: string) => api.get(url),
    {
    revalidateOnFocus: false,
    },
  );

  return {
    property: data ?? null,
    error,
    isLoading,
    mutate,
  };
}
