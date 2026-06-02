"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useApiClient } from "@/lib/api";

type OrderStatus = "PENDING" | "PAID" | "FAILED" | "loading" | "error";

function CreditSuccessContent() {
  const searchParams = useSearchParams();
  const orderId = searchParams.get("order_id");
  const api = useApiClient();
  const apiRef = useRef(api);
  apiRef.current = api;
  const [status, setStatus] = useState<OrderStatus>("loading");

  useEffect(() => {
    if (!orderId) {
      setStatus("error");
      return;
    }

    // Poll the purchase history to detect when the order transitions from PENDING → PAID
    let attempts = 0;
    const MAX_ATTEMPTS = 10;
    const INTERVAL_MS = 2000;
    let cancelled = false;

    async function checkStatus() {
      if (cancelled) return;
      try {
        const res = await apiRef.current.get<{ items: { id: string; status: string }[] }>(
          "/api/credits/purchases"
        );
        if (cancelled) return;
        const order = res.items.find((o) => o.id === orderId);
        if (!order) {
          setStatus("error");
          return;
        }
        if (order.status === "PAID") {
          setStatus("PAID");
          return;
        }
        if (order.status === "FAILED") {
          setStatus("FAILED");
          return;
        }
        // Still PENDING — retry up to MAX_ATTEMPTS
        if (++attempts < MAX_ATTEMPTS) {
          setTimeout(checkStatus, INTERVAL_MS);
        } else {
          // Webhook may be delayed — show PENDING UI with explanation
          setStatus("PENDING");
        }
      } catch {
        if (!cancelled) setStatus("error");
      }
    }

    checkStatus();
    return () => { cancelled = true; };
  }, [orderId]);

  return (
    <main className="mx-auto max-w-xl px-4 py-20 text-center">
      {status === "loading" && (
        <div className="flex flex-col items-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-300 border-t-indigo-700" />
          <p className="text-zinc-500 dark:text-zinc-400">Confirming your payment…</p>
        </div>
      )}

      {status === "PAID" && (
        <>
          <div className="mb-4 text-5xl">🎉</div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-white mb-2">Credits added!</h1>
          <p className="text-zinc-500 dark:text-zinc-400 mb-8">
            Your credits have been added to your account and are ready to use.
          </p>
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
            <Link
              href="/"
              className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
            >
              Search properties
            </Link>
            <Link
              href="/pricing"
              className="rounded-lg border border-zinc-300 px-6 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              Buy more credits
            </Link>
          </div>
        </>
      )}

      {status === "PENDING" && (
        <>
          <div className="mb-4 text-5xl">⏳</div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-white mb-2">Payment received</h1>
          <p className="text-zinc-500 dark:text-zinc-400 mb-6">
            Your payment was successful. Credits may take a moment to appear —
            this usually resolves within a minute.
          </p>
          <p className="text-sm text-zinc-400 dark:text-zinc-500 mb-6">
            Refresh the page to check, or continue browsing — your credits will appear automatically.
          </p>
          <Link
            href="/"
            className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
          >
            Continue to site
          </Link>
        </>
      )}

      {status === "FAILED" && (
        <>
          <div className="mb-4 text-5xl">❌</div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-white mb-2">Payment not completed</h1>
          <p className="text-zinc-500 dark:text-zinc-400 mb-8">
            Your payment could not be processed. You have not been charged.
          </p>
          <Link
            href="/pricing"
            className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
          >
            Try again
          </Link>
        </>
      )}

      {status === "error" && (
        <>
          <div className="mb-4 text-5xl">⚠️</div>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-white mb-2">Something went wrong</h1>
          <p className="text-zinc-500 dark:text-zinc-400 mb-8">
            We couldn&apos;t verify your payment status. If you were charged,
            please contact support with your order ID:{" "}
            <code className="rounded bg-zinc-100 px-1 text-xs dark:bg-zinc-800">
              {orderId ?? "unknown"}
            </code>
          </p>
          <Link
            href="/pricing"
            className="rounded-lg border border-zinc-300 px-5 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300"
          >
            Back to pricing
          </Link>
        </>
      )}
    </main>
  );
}

export default function CreditSuccessPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-xl px-4 py-20 text-center">
          <div className="flex flex-col items-center gap-4">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-300 border-t-indigo-700" />
            <p className="text-zinc-500 dark:text-zinc-400">Loading payment status…</p>
          </div>
        </main>
      }
    >
      <CreditSuccessContent />
    </Suspense>
  );
}
