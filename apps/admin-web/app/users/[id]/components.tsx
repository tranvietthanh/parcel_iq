"use client";

import { useState, useTransition } from "react";
import { topUpUserCredits } from "@/actions/users";

type Props = {
  userId: string;
  currentSpendable: number;
};

const ENTRY_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  DAILY_GRANT: { label: "Daily Grant", color: "text-emerald-400" },
  DOWNLOAD_DEBIT: { label: "Download", color: "text-red-400" },
  ADMIN_TOPUP: { label: "Admin Top-up", color: "text-blue-400" },
};

export function TopUpForm({ userId, currentSpendable }: Props) {
  const [credits, setCredits] = useState("");
  const [reason, setReason] = useState("");
  const [isPending, startTransition] = useTransition();
  const [result, setResult] = useState<
    { type: "success"; message: string } | { type: "error"; message: string } | null
  >(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const creditAmount = parseInt(credits, 10);

    if (!creditAmount || creditAmount <= 0) {
      setResult({ type: "error", message: "Credits must be a positive integer." });
      return;
    }
    if (!reason.trim()) {
      setResult({ type: "error", message: "Reason is required." });
      return;
    }
    if (creditAmount > 10000) {
      setResult({ type: "error", message: "Cannot exceed 10,000 credits per top-up." });
      return;
    }

    setResult(null);
    startTransition(async () => {
      try {
        const res = await topUpUserCredits(userId, creditAmount, reason.trim());
        setResult({
          type: "success",
          message: `Successfully added ${res.credits_added} credit${res.credits_added === 1 ? "" : "s"}. New balance: ${res.new_balance_after}.`,
        });
        setCredits("");
        setReason("");
      } catch (err: unknown) {
        setResult({
          type: "error",
          message: err instanceof Error ? err.message : "Top-up failed. Please try again.",
        });
      }
    });
  }

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
      <h2 className="text-lg font-semibold text-white mb-1">Manual Top-Up</h2>
      <p className="text-gray-400 text-sm mb-5">
        Current spendable balance:{" "}
        <span className="text-white font-medium">{currentSpendable}</span> credits
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm text-gray-300 mb-1" htmlFor="credits">
            Credits to add
          </label>
          <input
            id="credits"
            type="number"
            min={1}
            max={10000}
            value={credits}
            onChange={(e) => setCredits(e.target.value)}
            placeholder="e.g. 10"
            className="w-full px-4 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 text-sm focus:outline-none focus:border-indigo-500 transition-colors"
            required
          />
        </div>

        <div>
          <label className="block text-sm text-gray-300 mb-1" htmlFor="reason">
            Reason
          </label>
          <input
            id="reason"
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Support request #1234 — credits lost due to billing issue"
            className="w-full px-4 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 text-sm focus:outline-none focus:border-indigo-500 transition-colors"
            required
          />
        </div>

        {result && (
          <div
            className={`px-4 py-3 rounded-lg text-sm ${
              result.type === "success"
                ? "bg-emerald-900/40 border border-emerald-700 text-emerald-300"
                : "bg-red-900/40 border border-red-700 text-red-300"
            }`}
          >
            {result.message}
          </div>
        )}

        <button
          type="submit"
          disabled={isPending}
          className="w-full py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
        >
          {isPending ? "Processing…" : "Add Credits"}
        </button>
      </form>
    </div>
  );
}

type LedgerEntry = {
  id: string;
  entry_type: string;
  delta_credits: number;
  balance_after: number;
  related_property_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export function LedgerTable({ entries }: { entries: LedgerEntry[] }) {
  if (entries.length === 0) {
    return (
      <p className="text-gray-500 text-sm py-6 text-center">
        No credit activity yet.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="w-full text-sm">
        <thead className="bg-gray-900 text-gray-400 text-xs uppercase tracking-wider">
          <tr>
            <th className="px-4 py-3 text-left">Date</th>
            <th className="px-4 py-3 text-left">Type</th>
            <th className="px-4 py-3 text-right">Delta</th>
            <th className="px-4 py-3 text-right">Balance After</th>
            <th className="px-4 py-3 text-left">Details</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {entries.map((entry) => {
            const typeInfo = ENTRY_TYPE_LABELS[entry.entry_type] ?? {
              label: entry.entry_type,
              color: "text-gray-400",
            };
            return (
              <tr key={entry.id} className="hover:bg-gray-900/30 transition-colors">
                <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">
                  {new Date(entry.created_at).toLocaleString("en-AU")}
                </td>
                <td className={`px-4 py-3 font-medium ${typeInfo.color}`}>
                  {typeInfo.label}
                </td>
                <td
                  className={`px-4 py-3 text-right font-mono font-semibold ${
                    entry.delta_credits > 0 ? "text-emerald-400" : "text-red-400"
                  }`}
                >
                  {entry.delta_credits > 0 ? "+" : ""}
                  {entry.delta_credits}
                </td>
                <td className="px-4 py-3 text-right text-white font-mono">
                  {entry.balance_after}
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {entry.entry_type === "ADMIN_TOPUP" && entry.metadata?.reason
                    ? String(entry.metadata.reason)
                    : entry.related_property_id
                    ? `Property ${entry.related_property_id.slice(0, 8)}…`
                    : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
