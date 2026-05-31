"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useAuth, SignInButton } from "@clerk/nextjs";
import { useApiClient } from "@/lib/api";

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
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${config.classes}`}>
      {config.label}
    </span>
  );
}

function RequestedTab() {
  const api = useApiClient();
  const [data, setData] = useState<RequestedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);

  const load = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const res = await api.get<RequestedResponse>(
        `/api/properties/my/requested?page=${p}&page_size=20`
      );
      setData(res);
    } catch (err) {
      console.error("Failed to load requested properties", err);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    load(page);
  }, [load, page]);

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
              <th className="px-4 py-3" />
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
                      className="text-xs font-medium text-indigo-600 hover:text-indigo-500 dark:text-indigo-400 dark:hover:text-indigo-300"
                    >
                      View →
                    </Link>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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
    api.get<{ items: SavedProperty[] }>("/api/saved")
      .then((res) => setSaved(res.items))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [api]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-800 dark:border-zinc-700 dark:border-t-zinc-300" />
      </div>
    );
  }

  if (saved.length === 0) {
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
