"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SignInButton, useAuth, useUser } from "@clerk/nextjs";
import Spinner from "@/components/ui/Spinner";
import { useApiClient } from "@/lib/api";
import { useProperty } from "@/hooks/useProperty";
import type {
  PropertyDetail as PropertyDetailData,
  RequestScrapeResponse,
} from "@/types";

type PropertyDetailProps = {
  propertyId: string | null;
  mode?: "panel" | "page";
  onClose?: () => void;
};

type WalletSummary = {
  daily_remaining: number;
  daily_grant: number;
  purchased_balance: number;
  total_spendable: number;
};

type PrecheckResult = {
  is_duplicate_download: boolean;
  previous_download_at: string | null;
  spendable_credits: number;
};

function getFilenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null;
  const match = /filename="?([^";]+)"?/i.exec(header);
  return match?.[1] ?? null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function asList(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => !!item && typeof item === "object");
}

// ── Duplicate-download warning modal ─────────────────────────────────────────

type DuplicateWarningModalProps = {
  previousDownloadAt: string | null;
  spendableCredits: number;
  onConfirm: () => void;
  onCancel: () => void;
};

function DuplicateWarningModal({
  previousDownloadAt,
  spendableCredits,
  onConfirm,
  onCancel,
}: DuplicateWarningModalProps) {
  const prevDate = previousDownloadAt
    ? new Date(previousDownloadAt).toLocaleDateString("en-AU", { dateStyle: "medium" })
    : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-amber-300 bg-white p-6 shadow-2xl dark:border-amber-700 dark:bg-zinc-900">
        <div className="mb-4 flex items-start gap-3">
          <span className="mt-0.5 text-2xl" aria-hidden="true">⚠️</span>
          <div>
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">
              You've downloaded this before
            </h2>
            {prevDate && (
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                Last downloaded on {prevDate}
              </p>
            )}
          </div>
        </div>
        <p className="mb-6 text-sm text-zinc-600 dark:text-zinc-300">
          Downloading again will use{" "}
          <strong className="text-zinc-900 dark:text-white">1 credit</strong>.
          You currently have{" "}
          <span className="font-semibold text-emerald-600 dark:text-emerald-400">
            {spendableCredits} credit{spendableCredits !== 1 ? "s" : ""}
          </span>{" "}
          available.
        </p>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            Download anyway (1 credit)
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Credit balance badge ──────────────────────────────────────────────────────

function CreditBadge({ wallet }: { wallet: WalletSummary }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-800">
      <span className="text-zinc-500 dark:text-zinc-400">Credits:</span>
      <span className="font-semibold text-emerald-600 dark:text-emerald-400">
        {wallet.daily_remaining} daily
      </span>
      {wallet.purchased_balance > 0 && (
        <>
          <span className="text-zinc-300 dark:text-zinc-600">+</span>
          <span className="font-semibold text-blue-600 dark:text-blue-400">
            {wallet.purchased_balance} purchased
          </span>
        </>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function PropertyDetail({
  propertyId,
  mode = "panel",
  onClose,
}: PropertyDetailProps) {
  const { property, isLoading, mutate } = useProperty(propertyId, "detail");
  const data = property as PropertyDetailData | null;
  const api = useApiClient();
  const { isSignedIn, getToken } = useAuth();
  const { user } = useUser();

  const [acknowledged, setAcknowledged] = useState(false);
  const [requestingData, setRequestingData] = useState(false);
  const [scrapeRequested, setScrapeRequested] = useState(false);
  const [pollTimedOut, setPollTimedOut] = useState(false);
  const [liteDownloadsUsedToday, setLiteDownloadsUsedToday] = useState(0);
  const [anonLiteLimitReached, setAnonLiteLimitReached] = useState(false);
  const pollCountRef = useRef(0);

  // Credit state
  const [wallet, setWallet] = useState<WalletSummary | null>(null);
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // Duplicate-download modal state
  const [showDuplicateModal, setShowDuplicateModal] = useState(false);
  const [precheckResult, setPrecheckResult] = useState<PrecheckResult | null>(null);

  const isProcessing =
    !!data?.report_status &&
    ["QUEUING", "PROCESSING"].includes(data.report_status);

  const isFailed = data?.report_status === "FAILED";

  const hasDetailData = useMemo(() => {
    if (!data) return false;
    return Boolean(
      data.education ||
        data.connectivity ||
        data.risk_factors ||
        data.zoning_and_planning ||
        data.demographic_snapshot,
    );
  }, [data]);

  const reportsUnavailable = !hasDetailData || isProcessing;

  // Poll while processing
  useEffect(() => {
    if (!isProcessing) {
      pollCountRef.current = 0;
      setPollTimedOut(false);
      return;
    }
    const MAX_POLLS = 60;
    const interval = setInterval(() => {
      if (pollCountRef.current >= MAX_POLLS) {
        clearInterval(interval);
        setPollTimedOut(true);
        return;
      }
      pollCountRef.current += 1;
      mutate();
    }, 10000);
    return () => clearInterval(interval);
  }, [isProcessing, mutate]);

  // Reset on property change
  useEffect(() => {
    if (!propertyId || typeof window === "undefined") {
      setAcknowledged(false);
      setScrapeRequested(false);
      setDownloadError(null);
      setPrecheckResult(null);
      return;
    }
    setAcknowledged(localStorage.getItem("ack_general_disclaimer") === "true");
    setScrapeRequested(false);
    setDownloadError(null);
    setPrecheckResult(null);
  }, [propertyId]);

  // Anonymous lite download quota tracking (localStorage)
  useEffect(() => {
    if (!propertyId || isSignedIn || typeof window === "undefined") {
      setAnonLiteLimitReached(false);
      return;
    }
    const todayAu = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Australia/Sydney",
    }).format(new Date());
    const storageKey = `anon_lite_downloads_${todayAu}`;
    const raw = localStorage.getItem(storageKey);
    const ids = raw ? (JSON.parse(raw) as string[]) : [];
    const uniqueIds = Array.from(new Set(ids));
    setLiteDownloadsUsedToday(uniqueIds.length);
    setAnonLiteLimitReached(uniqueIds.length >= 3 && !uniqueIds.includes(propertyId));
  }, [propertyId, isSignedIn]);

  // Fetch credit wallet when signed in
  const fetchWallet = useCallback(async () => {
    if (!isSignedIn) return;
    try {
      const summary = await api.get<WalletSummary>("/api/credits/me");
      setWallet(summary);
    } catch {
      // Non-fatal — wallet badge just won't show
    }
  }, [isSignedIn, api]);

  useEffect(() => {
    fetchWallet();
  }, [fetchWallet]);

  const requestPropertyData = async () => {
    if (!propertyId) return;
    setRequestingData(true);
    try {
      const response = await api.post<RequestScrapeResponse>(
        `/api/properties/${propertyId}/request-scrape`,
        {},
      );
      if (response.status === "queued" || response.status === "processing") {
        setScrapeRequested(true);
      }
      if (response.status === "ready") {
        mutate();
      }
    } catch (error) {
      console.error("Failed to request property data:", error);
    } finally {
      setRequestingData(false);
    }
  };

  const handleLiteDownload = async () => {
    if (!data || isSignedIn || anonLiteLimitReached || reportsUnavailable) return;
    try {
      const response = await fetch(`/api/properties/${data.id}/lite-report/pdf`, {
        method: "GET",
        headers: { Accept: "application/pdf" },
      });
      if (!response.ok) {
        console.error(`Lite PDF generation failed: ${response.statusText}`);
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download =
        getFilenameFromContentDisposition(response.headers.get("content-disposition")) ??
        `property-lite-${data.id}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);

      if (typeof window !== "undefined") {
        const todayAu = new Intl.DateTimeFormat("en-CA", {
          timeZone: "Australia/Sydney",
        }).format(new Date());
        const storageKey = `anon_lite_downloads_${todayAu}`;
        const raw = localStorage.getItem(storageKey);
        const ids = raw ? (JSON.parse(raw) as string[]) : [];
        if (!ids.includes(data.id)) ids.push(data.id);
        localStorage.setItem(storageKey, JSON.stringify(ids));
        const uniqueIds = Array.from(new Set(ids));
        setLiteDownloadsUsedToday(uniqueIds.length);
        setAnonLiteLimitReached(uniqueIds.length >= 3);
      }
    } catch (error) {
      console.error("Failed to download lite report:", error);
    }
  };

  // ── Full download with credit check + duplicate modal ──────────────────────

  const executeFullDownload = async () => {
    if (!data || !isSignedIn || reportsUnavailable) return;
    setDownloadLoading(true);
    setDownloadError(null);
    try {
      const token = await getToken();
      const response = await fetch(`/api/properties/${data.id}/full/pdf`, {
        method: "GET",
        headers: {
          Accept: "application/pdf",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });

      if (response.status === 403) {
        const err = await response.json().catch(() => ({ detail: "Insufficient credits." }));
        setDownloadError(err.detail ?? "Insufficient credits. Please check your balance and try again.");
        return;
      }

      if (!response.ok) {
        setDownloadError("Download failed. Please try again.");
        return;
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download =
        getFilenameFromContentDisposition(response.headers.get("content-disposition")) ??
        `property-full-${data.id}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);

      // Refresh wallet to show updated balance
      await fetchWallet();
    } catch (error) {
      console.error("Failed to download full report:", error);
      setDownloadError("An unexpected error occurred. Please try again.");
    } finally {
      setDownloadLoading(false);
      setShowDuplicateModal(false);
    }
  };

  const handleFullDownloadClick = async () => {
    if (!data || !isSignedIn || reportsUnavailable) return;
    setDownloadError(null);

    // Run precheck to detect duplicate downloads
    try {
      const precheck = await api.get<PrecheckResult>(
        `/api/properties/${data.id}/full/precheck`,
      );
      setPrecheckResult(precheck);

      if (precheck.is_duplicate_download) {
        // Show warning modal before deducting a credit
        setShowDuplicateModal(true);
        return;
      }
    } catch {
      // Precheck failure is non-fatal — proceed with download
      setPrecheckResult(null);
    }

    await executeFullDownload();
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  const education = asRecord(data?.education);
  const connectivity = asRecord(data?.connectivity);
  const riskFactors = asRecord(data?.risk_factors);
  const zoning = asRecord(data?.zoning_and_planning);
  const demographics = asRecord(data?.demographic_snapshot);

  const primarySchools = asList(education?.primary_schools).slice(0, 5);
  const secondarySchools = asList(education?.secondary_schools).slice(0, 5);
  const overlays = asList(zoning?.overlays).slice(0, 6);

  const content = (
    <div className="p-4">
      {showDuplicateModal && precheckResult && (
        <DuplicateWarningModal
          previousDownloadAt={precheckResult.previous_download_at}
          spendableCredits={precheckResult.spendable_credits}
          onConfirm={executeFullDownload}
          onCancel={() => setShowDuplicateModal(false)}
        />
      )}

      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Spinner />
        </div>
      )}

      {!isLoading && !data && (
        <p className="py-8 text-center text-sm text-zinc-500">
          {propertyId ? "Report not available" : "No property selected"}
        </p>
      )}

      {data && (
        <>
          {!acknowledged ? (
            <div className="mx-auto max-w-2xl rounded-lg border border-amber-200 bg-amber-50 p-6 dark:border-amber-800 dark:bg-amber-950">
              <h3 className="mb-3 text-lg font-semibold text-amber-900 dark:text-amber-100">
                Important Disclaimer
              </h3>
              <p className="mb-4 text-sm leading-relaxed text-amber-800 dark:text-amber-200">
                This report is provided for <strong>general information only</strong>.
                OZ Property Report aggregates data from publicly available sources and does not
                guarantee its accuracy, completeness, or timeliness. This report does
                not constitute financial, legal, or investment advice. Always seek
                independent professional advice before making investment decisions.
                OZ Property Report accepts no liability for decisions made based on this
                information.
              </p>
              <button
                onClick={() => {
                  localStorage.setItem("ack_general_disclaimer", "true");
                  setAcknowledged(true);
                }}
                className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700"
              >
                I understand - show the report
              </button>
            </div>
          ) : (
            <div className="space-y-6">
              <div>
                <h3 className="text-xl font-bold text-zinc-900 dark:text-white">
                  {data.address}
                </h3>
                <p className="text-sm text-zinc-500">{data.state}</p>
                {isProcessing && (
                  <p className="mt-2 text-xs text-blue-600 dark:text-blue-400">
                    Property data is being processed...
                  </p>
                )}
              </div>

              {!hasDetailData && !isProcessing && !scrapeRequested && !isFailed && (
                <div className="rounded-lg border-2 border-dashed border-zinc-300 bg-zinc-50 p-6 text-center dark:border-zinc-700 dark:bg-zinc-800">
                  <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
                    Detailed property information is not yet available. Request a comprehensive
                    data collection to view education, connectivity, zoning and risk information.
                  </p>
                  <button
                    onClick={requestPropertyData}
                    disabled={requestingData}
                    className="rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {requestingData ? "Requesting..." : "Request Property Information"}
                  </button>
                </div>
              )}

              {(isProcessing || scrapeRequested) && !hasDetailData && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 p-6 dark:border-blue-800 dark:bg-blue-950">
                  <div className="flex items-center gap-3">
                    {!pollTimedOut && <Spinner />}
                    <div>
                      <h4 className="font-semibold text-blue-900 dark:text-blue-100">
                        {pollTimedOut ? "Still Processing" : "Data Being Processed"}
                      </h4>
                      <p className="text-sm text-blue-800 dark:text-blue-200">
                        {pollTimedOut
                          ? "This is taking longer than expected. Please check back in a few minutes."
                          : "We are collecting comprehensive property information. This typically takes 2-5 minutes."}
                      </p>
                      <div className="mt-4">
                        {!isSignedIn ? (
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
                              Sign up or log in to receive an email when this report is ready
                            </p>
                            <SignInButton mode="modal">
                              <button className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700">
                                Sign In
                              </button>
                            </SignInButton>
                          </div>
                        ) : (
                          <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
                            We'll email you{user?.primaryEmailAddress?.emailAddress ? ` at ${user.primaryEmailAddress.emailAddress}` : ""} when your report is ready.
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {isFailed && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-950">
                  <div className="flex items-start gap-3">
                    <svg className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <div>
                      <h4 className="font-semibold text-red-900 dark:text-red-100">Processing Failed</h4>
                      <p className="text-sm text-red-800 dark:text-red-200">
                        We encountered an error while collecting property data. Please try again.
                      </p>
                      <button
                        onClick={requestPropertyData}
                        disabled={requestingData}
                        className="mt-3 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                      >
                        {requestingData ? "Requesting..." : "Try Again"}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {education && (
                <section>
                  <h4 className="mb-2 text-sm font-semibold text-zinc-700 dark:text-zinc-300">Education</h4>
                  {typeof education.nearby_schools_summary === "string" && (
                    <p className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">{education.nearby_schools_summary}</p>
                  )}
                  <div className="grid grid-cols-1 gap-3">
                    {primarySchools.length > 0 && (
                      <div>
                        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">Primary Schools</p>
                        <ul className="space-y-1">
                          {primarySchools.map((school, idx) => (
                            <li key={`primary-${idx}`} className="text-sm text-zinc-700 dark:text-zinc-300">
                              {String(school.name ?? "Unknown")} ({Number(school.distance_km ?? 0).toFixed(2)} km)
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {secondarySchools.length > 0 && (
                      <div>
                        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">Secondary Schools</p>
                        <ul className="space-y-1">
                          {secondarySchools.map((school, idx) => (
                            <li key={`secondary-${idx}`} className="text-sm text-zinc-700 dark:text-zinc-300">
                              {String(school.name ?? "Unknown")} ({Number(school.distance_km ?? 0).toFixed(2)} km)
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </section>
              )}

              {connectivity && (
                <section>
                  <h4 className="mb-2 text-sm font-semibold text-zinc-700 dark:text-zinc-300">Connectivity</h4>
                  <dl className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-zinc-500">NBN Technology</dt>
                      <dd className="font-medium text-zinc-900 dark:text-white">
                        {String(connectivity.nbn_tech_type ?? connectivity.nbn_technology ?? "N/A")}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500">Service Status</dt>
                      <dd className="font-medium text-zinc-900 dark:text-white">
                        {String(connectivity.nbn_service_status ?? connectivity.nbn_status ?? "N/A")}
                      </dd>
                    </div>
                  </dl>
                </section>
              )}

              {riskFactors && (
                <section>
                  <h4 className="mb-2 text-sm font-semibold text-zinc-700 dark:text-zinc-300">Risk Factors</h4>
                  <dl className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-zinc-500">Flood</dt>
                      <dd className="font-medium text-zinc-900 dark:text-white">
                        {String(asRecord(riskFactors.flood)?.risk ?? riskFactors.flood_risk ?? "Unknown")}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500">Bushfire</dt>
                      <dd className="font-medium text-zinc-900 dark:text-white">
                        {String(asRecord(riskFactors.bushfire)?.risk ?? riskFactors.bushfire_risk ?? "Unknown")}
                      </dd>
                    </div>
                  </dl>
                </section>
              )}

              {zoning && (
                <section>
                  <h4 className="mb-2 text-sm font-semibold text-zinc-700 dark:text-zinc-300">Zoning and Planning</h4>
                  <dl className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-zinc-500">Zoning Code</dt>
                      <dd className="font-medium text-zinc-900 dark:text-white">{String(zoning.zoning_code ?? "N/A")}</dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500">Zone Label</dt>
                      <dd className="font-medium text-zinc-900 dark:text-white">{String(zoning.zoning_label ?? "N/A")}</dd>
                    </div>
                  </dl>
                  {overlays.length > 0 && (
                    <ul className="mt-3 space-y-1">
                      {overlays.map((overlay, idx) => (
                        <li key={`overlay-${idx}`} className="text-sm text-zinc-700 dark:text-zinc-300">
                          {String(overlay.code ?? "-")}: {String(overlay.summary ?? "Overlay applies")}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              )}

              {demographics && (
                <section>
                  <h4 className="mb-2 text-sm font-semibold text-zinc-700 dark:text-zinc-300">Demographic Snapshot</h4>
                  <dl className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-zinc-500">Population</dt>
                      <dd className="font-medium text-zinc-900 dark:text-white">{String(demographics.total_population ?? "N/A")}</dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500">Median Age</dt>
                      <dd className="font-medium text-zinc-900 dark:text-white">{String(demographics.median_age ?? "N/A")}</dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500">Population YoY</dt>
                      <dd className="font-medium text-zinc-900 dark:text-white">{String(demographics.population_growth_pct_yoy ?? "N/A")}%</dd>
                    </div>
                    <div>
                      <dt className="text-zinc-500">House Price YoY</dt>
                      <dd className="font-medium text-zinc-900 dark:text-white">{String(demographics.house_price_growth_pct_yoy ?? "N/A")}%</dd>
                    </div>
                  </dl>
                </section>
              )}

              {/* ── Download actions ─────────────────────────────────────── */}
              <div className="rounded-lg border border-zinc-200 p-3 space-y-3 dark:border-zinc-700">

                {/* Credit balance badge — shown to signed-in users */}
                {isSignedIn && wallet && (
                  <CreditBadge wallet={wallet} />
                )}

                {!isSignedIn && (
                  <>
                    <p className="text-xs text-zinc-600 dark:text-zinc-400">
                      Sign in to download full reports using your daily free credits.
                    </p>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">
                      Anonymous lite downloads today: {liteDownloadsUsedToday}/3
                    </p>
                    <button
                      onClick={handleLiteDownload}
                      disabled={anonLiteLimitReached || reportsUnavailable}
                      className="w-full rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
                    >
                      Download Lite Report
                    </button>
                  </>
                )}

                {isSignedIn ? (
                  <button
                    id="download-full-report-btn"
                    onClick={handleFullDownloadClick}
                    disabled={reportsUnavailable || downloadLoading}
                    className="w-full rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
                  >
                    {downloadLoading
                      ? "Downloading…"
                      : "Download Full Report (1 credit)"}
                  </button>
                ) : (
                  <SignInButton mode="modal">
                    <button
                      disabled={reportsUnavailable}
                      className="w-full rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
                    >
                      Sign in to download full report
                    </button>
                  </SignInButton>
                )}

                {/* Error message for failed/exhausted downloads */}
                {downloadError && (
                  <div className="rounded-lg border border-red-200 bg-red-50 p-3 dark:border-red-800 dark:bg-red-950">
                    <p className="text-xs text-red-700 dark:text-red-300">{downloadError}</p>
                    {downloadError.toLowerCase().includes("credit") && (
                      <a
                        href="/pricing"
                        className="mt-1 inline-block text-xs font-medium text-red-600 hover:text-red-500 dark:text-red-400 underline"
                      >
                        View credit options →
                      </a>
                    )}
                  </div>
                )}

                {reportsUnavailable && (
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    Download is unavailable while property data is processing or not ready.
                  </p>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );

  if (mode === "page") {
    return content;
  }

  return (
    <div
      className={`fixed right-0 top-0 z-40 h-full w-full max-w-md transform overflow-y-auto bg-white shadow-xl transition-transform duration-300 dark:bg-zinc-900 ${
        propertyId ? "translate-x-0" : "translate-x-full"
      }`}
      role="dialog"
      aria-label="Property preview"
    >
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-zinc-200 bg-white px-4 py-3 dark:border-zinc-700 dark:bg-zinc-900">
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">Property Details</h2>
        <button
          onClick={onClose}
          className="rounded-md p-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          aria-label="Close panel"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      {content}
    </div>
  );
}
