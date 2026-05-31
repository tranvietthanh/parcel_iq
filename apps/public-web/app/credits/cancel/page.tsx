import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Checkout Cancelled — OZ Property Report",
};

export default function CreditCancelPage() {
  return (
    <main className="mx-auto max-w-xl px-4 py-20 text-center">
      <div className="mb-4 text-5xl">↩️</div>
      <h1 className="text-2xl font-bold text-zinc-900 dark:text-white mb-2">
        Checkout cancelled
      </h1>
      <p className="text-zinc-500 dark:text-zinc-400 mb-8">
        No charges were made. You can return to purchase credits whenever you&apos;re ready.
      </p>
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
        <Link
          href="/pricing"
          className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
        >
          Back to credits
        </Link>
        <Link
          href="/"
          className="rounded-lg border border-zinc-300 px-6 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          Search properties
        </Link>
      </div>
    </main>
  );
}
