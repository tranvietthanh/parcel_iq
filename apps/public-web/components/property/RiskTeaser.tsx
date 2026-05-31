"use client";

import Button from "@/components/ui/Button";

type RiskTeaserProps = {
  propertyId: string;
  onUnlock: () => void;
};

/**
 * Blurred risk section with "Unlock Full Report" CTA.
 * Shown in the lite panel when the user hasn't purchased the report.
 */
export default function RiskTeaser({ onUnlock }: RiskTeaserProps) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-700">
      {/* Blurred placeholder content */}
      <div className="select-none p-4 blur-sm">
        <h4 className="mb-2 text-sm font-semibold text-zinc-700">
          Risk Assessment
        </h4>
        <div className="space-y-2">
          <div className="h-3 w-3/4 rounded bg-zinc-200" />
          <div className="h-3 w-1/2 rounded bg-zinc-200" />
          <div className="h-3 w-2/3 rounded bg-zinc-200" />
          <div className="h-3 w-5/6 rounded bg-zinc-200" />
        </div>
        <h4 className="mb-2 mt-4 text-sm font-semibold text-zinc-700">
          Planning Details
        </h4>
        <div className="space-y-2">
          <div className="h-3 w-2/3 rounded bg-zinc-200" />
          <div className="h-3 w-1/2 rounded bg-zinc-200" />
        </div>
      </div>

      {/* Overlay CTA */}
      <div className="absolute inset-0 flex flex-col items-center justify-center bg-white/80 dark:bg-zinc-900/80">
        <p className="mb-3 text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Unlock the full risk &amp; planning report
        </p>
        <Button onClick={onUnlock}>Unlock Full Report</Button>
      </div>
    </div>
  );
}
