"use client";

import { useState } from "react";
import { useAuth, SignInButton } from "@clerk/nextjs";
import { useApiClient } from "@/lib/api";
import Button from "@/components/ui/Button";
import { showToast } from "@/components/ui/Toast";

type UnlockButtonProps = {
  propertyId: string;
};

/**
 * Stripe checkout trigger button.
 * Flow:
 * 1. If not signed in → Clerk modal
 * 2. If signed in → POST /api/payments/checkout → redirect to Stripe
 */
export default function UnlockButton({ propertyId }: UnlockButtonProps) {
  const { isSignedIn } = useAuth();
  const api = useApiClient();
  const [loading, setLoading] = useState(false);

  const handleCheckout = async () => {
    setLoading(true);
    try {
      const { checkout_url } = await api.post<{ checkout_url: string }>(
        "/api/payments/checkout",
        { property_id: propertyId },
      );
      window.location.href = checkout_url;
    } catch {
      showToast("error", "Failed to start checkout. Please try again.");
      setLoading(false);
    }
  };

  if (!isSignedIn) {
    return (
      <SignInButton mode="modal">
        <Button>Unlock Full Report</Button>
      </SignInButton>
    );
  }

  return (
    <Button onClick={handleCheckout} loading={loading}>
      Unlock Full Report
    </Button>
  );
}
