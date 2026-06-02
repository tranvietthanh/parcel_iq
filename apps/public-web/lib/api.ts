"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useMemo } from "react";
import { ApiError } from "@/types";

/* ── Client-side hook (for use in client components) ───── */

export function useApiClient() {
  const { getToken } = useAuth();

  const request = useCallback(
    async function request<T>(
      method: string,
      path: string,
      body?: unknown,
      extraHeaders?: Record<string, string>,
    ): Promise<T> {
      const token = await getToken();
      const res = await fetch(path, {
        method,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...extraHeaders,
        },
        body: body ? JSON.stringify(body) : undefined,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new ApiError(res.status, err.detail ?? "Request failed");
      }

      return res.json();
    },
    [getToken],
  );

  return useMemo(
    () => ({
      get: <T>(path: string, extraHeaders?: Record<string, string>) =>
        request<T>("GET", path, undefined, extraHeaders),
      post: <T>(path: string, body: unknown, extraHeaders?: Record<string, string>) =>
        request<T>("POST", path, body, extraHeaders),
    }),
    [request],
  );
}

