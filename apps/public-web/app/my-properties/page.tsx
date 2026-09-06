"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAuth, SignInButton } from "@clerk/nextjs";
import { useApiClient } from "@/lib/api";
import { Turnstile, type TurnstileInstance } from "@marsidev/react-turnstile";

type RequestedItem = {
  property_id: string;
  address: string;
  state: string;
  report_id: string;
  report_status: string;
  requested_at: string | null;
  ready_at: string | null;
  has_downloaded_before: boolean;
  slug: string | null;
};

type Pagination = {
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
};

type RequestedResponse = {
  items: RequestedItem[];
  pagination: Pagination;
};

type SavedProperty = {
  id: string;
  address: string;
  state: string;
  slug: string | null;
};

const STATUS_CONFIG: Record<string, { label: string; classes: string }> = {
  READY: { label: "Ready", classes: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200" },
  PROCESSING: { label: "Processing", classes: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200" },
  QUEUING: { label: "Queued", classes: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200" },
  FAILED: { label: "Failed", classes: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200" },
};

function StatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? { label: status, classes: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300" };
  const isInProgress = status === "PROCESSING" || status === "QUEUING";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${config.classes}`}>
      {isInProgress && (
        <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
      )}
      {config.label}
    </span>
  );
}

function RequestedTab() {
  const api = useApiClient();
  const [data, setData] = useState<RequestedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [retryError, setRetryError] = useState<{ propertyId: string; message: string } | null>(null);

  const turnstileRef = useRef<TurnstileInstance>(null);
  const turnstileTokenRef = useRef<string | null>(null);

  const consumeTurnstileToken = (): string | null => {
    const token = turnstileTokenRef.current;
    if (token) {
      turnstileTokenRef.current = null;
      turnstileRef.current?.reset();
    }
    return token;
  };

  const load = useCallback(async (p: number, silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await api.get<RequestedResponse>(
        `/api/properties/my/requested?page=${p}&page_size=20`
      );
      setData(res);
    } catch (err) {
      console.error("Failed to load requested properties", err);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    load(page);
  }, [load, page]);

  // Background polling when any item is in QUEUING or PROCESSING state
  useEffect(() => {
    if (!data) return;
    const hasInFlight = data.items.some(
      (item) => item.report_status === "QUEUING" || item.report_status === "PROCESSING"
    );
    if (!hasInFlight) return;

    const interval = setInterval(() => {
      load(page, true);
    }, 6000);

    return () => clearInterval(interval);
  }, [data, load, page]);

  const handleRetry = async (propertyId: string) => {
    if (retryingId) return;
    setRetryingId(propertyId);
    setRetryError(null);

    // Optimistically mark this item as QUEUING
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.map((item) =>
          item.property_id === propertyId
            ? { ...item, report_status: "QUEUING" }
            : item
        ),
      };
    });

    try {
      const token = consumeTurnstileToken();
      await api.post(
        `/api/properties/${propertyId}/request-scrape`,
        {},
        token ? { "X-Turnstile-Token": token } : undefined
      );
      // Refresh list to sync with server
      await load(page, true);
    } catch (err: unknown) {
      console.error("Failed to retry property report", err);
      const message = err instanceof Error ? err.message : "Failed to retry. Please try again.";
      setRetryError({ propertyId, message });
      // Revert back to FAILED on error
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          items: prev.items.map((item) =>
            item.property_id === propertyId
              ? { ...item, report_status: "FAILED" }
              : item
          ),
        };
      });
    } finally {
      setRetryingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-800 dark:border-zinc-700 dark:border-t-zinc-300" />
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <div className="py-16 text-center">
        <p className="text-zinc-500 dark:text-zinc-400">No property requests yet.</p>
        <p className="mt-2 text-sm text-zinc-400 dark:text-zinc-500">
          Search for a property and request a report to see it here.
        </p>
        <Link
          href="/"
          className="mt-4 inline-block rounded-lg bg-zinc-900 px-5 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          Search properties
        </Link>
      </div>
    );
  }

  return (
    <div>
      <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 text-xs uppercase tracking-wider text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
            <tr>
              <th className="px-4 py-3 text-left">Property</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-left">Requested</th>
              <th className="px-4 py-3 text-center">Downloaded</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {data.items.map((item) => (
              <tr key={item.report_id} className="hover:bg-zinc-50/50 dark:hover:bg-zinc-800/30 transition-colors">
                <td className="px-4 py-3">
                  <p className="font-medium text-zinc-900 dark:text-white leading-snug">
                    {item.address}
                  </p>
                  <p className="text-xs text-zinc-500">{item.state}</p>
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={item.report_status} />
                  {item.report_status === "READY" && item.ready_at && (
                    <p className="mt-1 text-xs text-zinc-400">
                      Ready {new Date(item.ready_at).toLocaleDateString("en-AU")}
                    </p>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-zinc-500">
                  {item.requested_at
                    ? new Date(item.requested_at).toLocaleDateString("en-AU", { dateStyle: "medium" })
                    : "—"}
                </td>
                <td className="px-4 py-3 text-center">
                  {item.has_downloaded_before ? (
                    <span className="text-emerald-600 dark:text-emerald-400" title="Previously downloaded">
                      ✓
                    </span>
                  ) : (
                    <span className="text-zinc-300 dark:text-zinc-600">—</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right">
                  {item.report_status === "READY" && item.slug && (
                    <Link
                      href={`/property/${item.slug}`}
                      className="inline-flex items-center text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300"
                    >
                      View →
                    </Link>
                  )}
                  {item.report_status === "FAILED" && (
                    <div className="flex flex-col items-end">
                      <button
                        onClick={() => handleRetry(item.property_id)}
                        disabled={retryingId === item.property_id}
                        className="inline-flex items-center gap-1.5 rounded-md bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-900 dark:text-zinc-100 transition-colors disabled:opacity-50 shadow-xs border border-zinc-200/60 dark:border-zinc-700/60"
                        title="Retry processing for this property"
                      >
                        {retryingId === item.property_id ? (
                          <>
                            <div className="h-3 w-3 animate-spin rounded-full border border-zinc-400 border-t-zinc-900 dark:border-zinc-500 dark:border-t-zinc-100" />
                            <span>Retrying...</span>
                          </>
                        ) : (
                          <>
                            <svg className="h-3.5 w-3.5 text-zinc-600 dark:text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                            <span>Retry</span>
                          </>
                        )}
                      </button>
                      {retryError?.propertyId === item.property_id && (
                        <p className="mt-1 text-[11px] text-red-500 max-w-[150px] truncate" title={retryError.message}>
                          {retryError.message}
                        </p>
                      )}
                    </div>
                  )}
                  {(item.report_status === "QUEUING" || item.report_status === "PROCESSING") && (
                    <span className="inline-flex items-center gap-1 text-xs text-zinc-400 dark:text-zinc-500 italic">
                      <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                      Processing...
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Invisible Turnstile widget for verification tokens */}
      <Turnstile
        ref={turnstileRef}
        siteKey={process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? ""}
        options={{ size: "invisible" }}
        onSuccess={(token) => {
          turnstileTokenRef.current = token;
        }}
        onError={() => {
          turnstileTokenRef.current = null;
        }}
        onExpire={() => {
          turnstileTokenRef.current = null;
        }}
      />

      {/* Pagination */}
      {data.pagination.total_pages > 1 && (
        <div className="mt-4 flex items-center justify-between text-sm text-zinc-500">
          <span>
            {(page - 1) * 20 + 1}–{Math.min(page * 20, data.pagination.total_count)} of{" "}
            {data.pagination.total_count}
          </span>
          <div className="flex gap-2">
            {page > 1 && (
              <button
                onClick={() => setPage((p) => p - 1)}
                className="rounded-lg border border-zinc-300 px-3 py-1 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                ← Prev
              </button>
            )}
            {page < data.pagination.total_pages && (
              <button
                onClick={() => setPage((p) => p + 1)}
                className="rounded-lg border border-zinc-300 px-3 py-1 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                Next →
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function SavedTab() {
  const api = useApiClient();
  const [saved, setSaved] = useState<SavedProperty[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<SavedProperty[] | { items: SavedProperty[] }>("/api/saved")
      .then((res) => {
        if (Array.isArray(res)) {
          setSaved(res);
        } else if (res && Array.isArray((res as { items?: SavedProperty[] }).items)) {
          setSaved((res as { items: SavedProperty[] }).items);
        } else {
          setSaved([]);
        }
      })
      .catch((err) => {
        console.error("Failed to load saved properties", err);
        setSaved([]);
      })
      .finally(() => setLoading(false));
  }, [api]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-800 dark:border-zinc-700 dark:border-t-zinc-300" />
      </div>
    );
  }

  if (!saved || saved.length === 0) {
    return (
      <div className="py-16 text-center">
        <p className="text-zinc-500 dark:text-zinc-400">No saved properties yet.</p>
        <Link
          href="/"
          className="mt-4 inline-block rounded-lg bg-zinc-900 px-5 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          Search properties
        </Link>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-zinc-200 overflow-hidden rounded-lg border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
      {saved.map((p) => (
        <li key={p.id} className="flex items-center justify-between px-4 py-3 hover:bg-zinc-50/50 dark:hover:bg-zinc-800/30 transition-colors">
          <div>
            <p className="font-medium text-zinc-900 dark:text-white">{p.address}</p>
            <p className="text-xs text-zinc-500">{p.state}</p>
          </div>
          {p.slug && (
            <Link
              href={`/property/${p.slug}`}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400"
            >
              View →
            </Link>
          )}
        </li>
      ))}
    </ul>
  );
}

export default function MyPropertiesPage() {
  const { isSignedIn, isLoaded } = useAuth();
  const [activeTab, setActiveTab] = useState<"requested" | "saved">("requested");

  if (!isLoaded) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-8">
        <div className="mb-4">
          <Link href="/" className="inline-flex items-center text-sm font-medium text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white">
            ← Back to Map
          </Link>
        </div>
        <div className="flex items-center justify-center py-16">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-800" />
        </div>
      </main>
    );
  }

  if (!isSignedIn) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-16 text-center">
        <div className="mb-8 flex justify-center">
          <Link href="/" className="inline-flex items-center text-sm font-medium text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white">
            ← Back to Map
          </Link>
        </div>
        <h1 className="text-2xl font-bold text-zinc-900 dark:text-white mb-3">My Properties</h1>
        <p className="text-zinc-500 dark:text-zinc-400 mb-6">
          Sign in to view your requested and saved properties.
        </p>
        <SignInButton mode="modal">
          <button className="rounded-lg bg-zinc-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900">
            Sign In
          </button>
        </SignInButton>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 pb-20">
      <div className="mb-6">
        <Link href="/" className="inline-flex items-center text-sm font-medium text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white">
          ← Back to Map
        </Link>
      </div>
      <h1 className="text-2xl font-bold text-zinc-900 dark:text-white mb-6">My Properties</h1>

      {/* Tabs */}
      <div className="mb-6 flex gap-1 border-b border-zinc-200 dark:border-zinc-800">
        <button
          id="tab-requested"
          onClick={() => setActiveTab("requested")}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "requested"
              ? "border-zinc-900 text-zinc-900 dark:border-zinc-100 dark:text-white"
              : "border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          }`}
        >
          Requested
        </button>
        <button
          id="tab-saved"
          onClick={() => setActiveTab("saved")}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "saved"
              ? "border-zinc-900 text-zinc-900 dark:border-zinc-100 dark:text-white"
              : "border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          }`}
        >
          Saved
        </button>
      </div>

      {activeTab === "requested" && <RequestedTab />}
      {activeTab === "saved" && <SavedTab />}
    </main>
  );
}
