"use client";

import { useEffect, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { useApiClient } from "@/lib/api";

/**
 * Fires once after the user signs in to claim any anonymous report requests
 * made in the same browser session (within the 7-day window).
 *
 * This is a side-effect-only component — it renders nothing.
 * It watches for the isSignedIn transition from false → true.
 */
export function AfterSignInClaimEffect() {
  const { isSignedIn, isLoaded } = useAuth();
  const api = useApiClient();
  const hasClaimed = useRef(false);
  const prevSignedIn = useRef<boolean | null>(null);

  useEffect(() => {
    if (!isLoaded) return;

    const justSignedIn =
      prevSignedIn.current === false && isSignedIn === true;

    prevSignedIn.current = isSignedIn ?? false;

    if (!justSignedIn || hasClaimed.current) return;
    if (!isSignedIn) return;

    hasClaimed.current = true;

    // Fire claim and ignore errors — claim is best-effort
    api
      .post<{ claimed_count: number }>("/api/properties/claim-anonymous-requests", {})
      .then(({ claimed_count }) => {
        if (claimed_count > 0) {
          console.log(`[OZPropertyReport] Claimed ${claimed_count} anonymous request(s).`);
        }
      })
      .catch(() => {
        // Non-fatal — user can still see their direct requests
      });
  }, [isSignedIn, isLoaded, api]);

  return null;
}
