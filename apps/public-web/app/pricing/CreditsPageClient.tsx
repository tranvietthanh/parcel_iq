"use client";

import { useState } from "react";
import { useAuth, SignInButton } from "@clerk/nextjs";
import Link from "next/link";
import { useApiClient } from "@/lib/api";

const CREDIT_PURCHASE_ENABLED =
  process.env.NEXT_PUBLIC_CREDIT_PURCHASE_ENABLED === "true";

// Preset credit bundles — $1 AUD per credit
const BUNDLES = [
  { credits: 5, label: "Starter", highlight: false },
  { credits: 10, label: "Popular", highlight: true },
  { credits: 25, label: "Pro", highlight: false },
  { credits: 50, label: "Power", highlight: false },
] as const;

const MIN_CREDITS = 5;

type CheckoutResponse = {
  checkout_url: string;
  order_id: string;
  credits: number;
  total_aud: number;
};

function BuyCreditsSection() {
  const api = useApiClient();
  const [selected, setSelected] = useState<number>(10);
  const [custom, setCustom] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const effectiveCredits = custom !== "" ? parseInt(custom, 10) || 0 : selected;
  const isValid = effectiveCredits >= MIN_CREDITS;

  async function handleCheckout() {
    if (!isValid) return;
    setLoading(true);
    setError(null);
    try {
      const { checkout_url } = await api.post<CheckoutResponse>(
        "/api/credits/checkout",
        { credits: effectiveCredits }
      );
      window.location.href = checkout_url;
    } catch (err: unknown) {
      const detail = (err as { detail?: string })?.detail;
      setError(detail ?? "Failed to start checkout. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-6 dark:border-indigo-800 dark:bg-indigo-950">
      <div className="mb-2 text-sm font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-400">
        Top-Up Credits
      </div>
      <p className="mb-1 text-4xl font-bold text-indigo-900 dark:text-indigo-100">
        $1 <span className="text-xl font-medium">AUD / credit</span>
      </p>
      <p className="mb-5 text-sm text-indigo-600 dark:text-indigo-400">
        Minimum 5 credits · Never expire · Used after daily credits run out
      </p>

      {/* Bundle presets */}
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {BUNDLES.map((b) => (
          <button
            key={b.credits}
            id={`bundle-${b.credits}`}
            onClick={() => { setSelected(b.credits); setCustom(""); }}
            className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
              effectiveCredits === b.credits && custom === ""
                ? "border-indigo-600 bg-indigo-600 text-white dark:border-indigo-400 dark:bg-indigo-500"
                : "border-indigo-300 bg-white text-indigo-800 hover:border-indigo-500 dark:border-indigo-700 dark:bg-indigo-900 dark:text-indigo-200"
            } ${b.highlight ? "ring-2 ring-indigo-400 ring-offset-1" : ""}`}
          >
            <span className="block font-bold">{b.credits}</span>
            <span className="text-xs opacity-75">{b.label}</span>
          </button>
        ))}
      </div>

      {/* Custom amount */}
      <div className="mb-4">
        <label
          htmlFor="custom-credits"
          className="mb-1 block text-xs font-medium text-indigo-700 dark:text-indigo-400"
        >
          Custom amount
        </label>
        <div className="flex items-center gap-2">
          <input
            id="custom-credits"
            type="number"
            min={MIN_CREDITS}
            step={1}
            placeholder={`Min ${MIN_CREDITS}`}
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            className="w-28 rounded-lg border border-indigo-300 bg-white px-3 py-1.5 text-sm text-indigo-900 placeholder:text-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-indigo-700 dark:bg-indigo-900 dark:text-indigo-100"
          />
          <span className="text-sm text-indigo-600 dark:text-indigo-400">
            credits = ${effectiveCredits >= MIN_CREDITS ? effectiveCredits : "—"} AUD
          </span>
        </div>
      </div>

      {error && (
        <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-400">
          {error}
        </p>
      )}

      <button
        id="checkout-btn"
        onClick={handleCheckout}
        disabled={!isValid || loading}
        className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-indigo-500 dark:hover:bg-indigo-400"
      >
        {loading
          ? "Redirecting to checkout…"
          : isValid
          ? `Buy ${effectiveCredits} credit${effectiveCredits !== 1 ? "s" : ""} — $${effectiveCredits} AUD`
          : `Minimum ${MIN_CREDITS} credits`}
      </button>

      <p className="mt-3 text-xs text-indigo-500 dark:text-indigo-400">
        Secure checkout via Stripe. Credits are non-refundable.
      </p>
    </div>
  );
}

export default function CreditsPageClient() {
  const { isSignedIn, isLoaded } = useAuth();

  return (
    <main className="mx-auto max-w-3xl px-4 py-16">
      <div className="mb-6">
        <Link href="/" className="inline-flex items-center text-sm font-medium text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white">
          ← Back to Map
        </Link>
      </div>
      <div className="mb-10 text-center">
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          Download Credits
        </h1>
        <p className="mt-2 text-zinc-500 dark:text-zinc-400">
          Use credits to download full property reports. Each successful download
          costs 1 credit. You receive free daily credits every day.
        </p>
      </div>

      <div className="grid gap-6 sm:grid-cols-2">
        {/* Daily free credits */}
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 dark:border-emerald-800 dark:bg-emerald-950">
          <div className="mb-2 text-sm font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-400">
            Daily Free Credits
          </div>
          <p className="mb-4 text-4xl font-bold text-emerald-900 dark:text-emerald-100">
            Free
          </p>
          <ul className="space-y-2 text-sm text-emerald-800 dark:text-emerald-200">
            <li>✓ Free credits every day (resets midnight AEST)</li>
            <li>✓ Download full reports with your free credits</li>
            <li>✓ Unused daily credits do not roll over</li>
          </ul>
        </div>

        {/* Top-up credits — feature flag gate, then auth gate */}
        {!CREDIT_PURCHASE_ENABLED ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-amber-200 bg-amber-50 p-6 text-center dark:border-amber-800 dark:bg-amber-950">
            <div className="mb-2 text-sm font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
              Top-Up Credits
            </div>
            <p className="mb-1 text-4xl font-bold text-amber-900 dark:text-amber-100">
              $1 <span className="text-xl font-medium">AUD / credit</span>
            </p>
            <div className="mb-3 mt-3 inline-flex items-center gap-2 rounded-full bg-amber-100 px-4 py-1.5 text-sm font-medium text-amber-800 dark:bg-amber-900 dark:text-amber-200">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
              </svg>
              Coming Soon
            </div>
            <p className="text-sm text-amber-700 dark:text-amber-300">
              Credit purchasing is currently under development. In the meantime, enjoy your free daily credits!
            </p>
          </div>
        ) : !isLoaded ? (
          <div className="flex items-center justify-center rounded-xl border border-indigo-200 bg-indigo-50 p-6 dark:border-indigo-800 dark:bg-indigo-950">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-300 border-t-indigo-700" />
          </div>
        ) : isSignedIn ? (
          <BuyCreditsSection />
        ) : (
          <div className="flex flex-col items-center justify-center rounded-xl border border-indigo-200 bg-indigo-50 p-6 text-center dark:border-indigo-800 dark:bg-indigo-950">
            <div className="mb-2 text-sm font-semibold uppercase tracking-wide text-indigo-700 dark:text-indigo-400">
              Top-Up Credits
            </div>
            <p className="mb-1 text-4xl font-bold text-indigo-900 dark:text-indigo-100">
              $1 <span className="text-xl font-medium">AUD / credit</span>
            </p>
            <p className="mb-5 text-sm text-indigo-600 dark:text-indigo-400">
              Sign in to purchase additional credits.
            </p>
            <SignInButton mode="modal">
              <button
                id="signin-to-buy-btn"
                className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 dark:bg-indigo-500"
              >
                Sign In to Buy Credits
              </button>
            </SignInButton>
          </div>
        )}
      </div>

      <p className="mt-8 text-center text-xs text-zinc-400">
        Purchase history available in{" "}
        <Link href="/my-properties" className="underline hover:text-zinc-600">
          My Properties
        </Link>
        . Credits are non-refundable once purchased.
      </p>
    </main>
  );
}
