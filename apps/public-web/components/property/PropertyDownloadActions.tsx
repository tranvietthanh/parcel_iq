"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { SignInButton, useAuth } from "@clerk/nextjs";
import { Turnstile, type TurnstileInstance } from "@marsidev/react-turnstile";

type WalletSummary = {
  daily_remaining: number;
  purchased_balance: number;
};

type PropertyDownloadActionsProps = {
  propertyId: string;
  reportStatus: string | null;
};

function getFilenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null;
  const match = /filename="?([^";]+)"?/i.exec(header);
  return match?.[1] ?? null;
}

export default function PropertyDownloadActions({ propertyId, reportStatus }: PropertyDownloadActionsProps) {
  const { isSignedIn, getToken } = useAuth();
  const [wallet, setWallet] = useState<WalletSummary | null>(null);
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [liteDownloadError, setLiteDownloadError] = useState<string | null>(null);
  const [liteDownloadsUsedToday, setLiteDownloadsUsedToday] = useState(0);
  const [anonLiteLimitReached, setAnonLiteLimitReached] = useState(false);
  const turnstileRef = useRef<TurnstileInstance>(null);
  const turnstileTokenRef = useRef<string | null>(null);

  const isProcessing = !!reportStatus && ["QUEUING", "PROCESSING"].includes(reportStatus);
  const liteAvailable = !!reportStatus && !isProcessing;

  useEffect(() => {
    if (isSignedIn || typeof window === "undefined") {
      setAnonLiteLimitReached(false);
      return;
    }
    const todayAu = new Intl.DateTimeFormat("en-CA", { timeZone: "Australia/Sydney" }).format(new Date());
    const storageKey = `anon_lite_downloads_${todayAu}`;
    const ids = JSON.parse(localStorage.getItem(storageKey) ?? "[]") as string[];
    const unique = Array.from(new Set(ids));
    setLiteDownloadsUsedToday(unique.length);
    setAnonLiteLimitReached(unique.length >= 3 && !unique.includes(propertyId));
  }, [propertyId, isSignedIn]);

  const fetchWallet = useCallback(async () => {
    if (!isSignedIn) return;
    try {
      const token = await getToken();
      const res = await fetch("/api/credits/me", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) setWallet(await res.json());
    } catch { /* non-fatal */ }
  }, [isSignedIn, getToken]);

  useEffect(() => { fetchWallet(); }, [fetchWallet]);

  const consumeTurnstileToken = () => {
    const token = turnstileTokenRef.current;
    if (token) { turnstileTokenRef.current = null; turnstileRef.current?.reset(); }
    return token;
  };

  const handleLiteDownload = async () => {
    if (anonLiteLimitReached || isSignedIn || !liteAvailable) return;
    setLiteDownloadError(null);
    try {
      const token = consumeTurnstileToken();
      const res = await fetch(`/api/properties/${propertyId}/lite-report/pdf`, {
        headers: {
          Accept: "application/pdf",
          ...(token ? { "X-Turnstile-Token": token } : {}),
        },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setLiteDownloadError(err.detail ?? "Failed to generate lite report. Please try again.");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = getFilenameFromContentDisposition(res.headers.get("content-disposition")) ?? `property-lite-${propertyId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);

      const todayAu = new Intl.DateTimeFormat("en-CA", { timeZone: "Australia/Sydney" }).format(new Date());
      const storageKey = `anon_lite_downloads_${todayAu}`;
      const ids = JSON.parse(localStorage.getItem(storageKey) ?? "[]") as string[];
      if (!ids.includes(propertyId)) ids.push(propertyId);
      localStorage.setItem(storageKey, JSON.stringify(ids));
      const unique = Array.from(new Set(ids));
      setLiteDownloadsUsedToday(unique.length);
      setAnonLiteLimitReached(unique.length >= 3);
    } catch {
      setLiteDownloadError("An unexpected error occurred. Please try again.");
    }
  };

  const handleFullDownload = async () => {
    if (!isSignedIn || downloadLoading) return;
    setDownloadLoading(true);
    setDownloadError(null);
    try {
      const token = await getToken();
      const res = await fetch(`/api/properties/${propertyId}/full/pdf`, {
        headers: {
          Accept: "application/pdf",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (res.status === 403) {
        const err = await res.json().catch(() => ({ detail: "Insufficient credits." }));
        setDownloadError(err.detail ?? "Insufficient credits.");
        return;
      }
      if (!res.ok) {
        setDownloadError("Download failed. Please try again.");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = getFilenameFromContentDisposition(res.headers.get("content-disposition")) ?? `property-full-${propertyId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      await fetchWallet();
    } catch {
      setDownloadError("An unexpected error occurred. Please try again.");
    } finally {
      setDownloadLoading(false);
    }
  };

  return (
    <div className="rounded-lg border border-zinc-200 p-3 space-y-3 dark:border-zinc-700">
      <Turnstile
        ref={turnstileRef}
        siteKey={process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? ""}
        options={{ appearance: "interaction-only", size: "invisible", execution: "render" }}
        onSuccess={(t) => { turnstileTokenRef.current = t; }}
        onError={() => { turnstileTokenRef.current = null; }}
        onExpire={() => { turnstileTokenRef.current = null; }}
      />

      {isSignedIn && wallet && (
        <div className="flex items-center gap-2 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-xs dark:border-zinc-700 dark:bg-zinc-800">
          <span className="text-zinc-500 dark:text-zinc-400">Credits:</span>
          <span className="font-semibold text-emerald-600 dark:text-emerald-400">{wallet.daily_remaining} daily</span>
          {wallet.purchased_balance > 0 && (
            <>
              <span className="text-zinc-300 dark:text-zinc-600">+</span>
              <span className="font-semibold text-blue-600 dark:text-blue-400">{wallet.purchased_balance} purchased</span>
            </>
          )}
        </div>
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
            disabled={anonLiteLimitReached || !liteAvailable}
            className="w-full rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
          >
            Download Lite Report
          </button>
          {liteDownloadError && (
            <p className="text-xs text-red-600 dark:text-red-400">{liteDownloadError}</p>
          )}
        </>
      )}

      {isSignedIn ? (
        <button
          onClick={handleFullDownload}
          disabled={downloadLoading}
          className="w-full rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          {downloadLoading ? "Downloading…" : "Download Full Report (1 credit)"}
        </button>
      ) : (
        <SignInButton mode="modal">
          <button className="w-full rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300">
            Sign in to download full report
          </button>
        </SignInButton>
      )}

      {downloadError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 dark:border-red-800 dark:bg-red-950">
          <p className="text-xs text-red-700 dark:text-red-300">{downloadError}</p>
          {downloadError.toLowerCase().includes("credit") && (
            <a href="/pricing" className="mt-1 inline-block text-xs font-medium text-red-600 hover:text-red-500 dark:text-red-400 underline">
              View credit options →
            </a>
          )}
        </div>
      )}
    </div>
  );
}
