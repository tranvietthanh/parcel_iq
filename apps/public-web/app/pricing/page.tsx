import type { Metadata } from "next";
import CreditsPageClient from "./CreditsPageClient";

export const metadata: Metadata = {
  title: "Credits — OZ Property Report",
  description:
    "Purchase credits to download full property reports. Credits never expire.",
};

export default function CreditsPage() {
  return <CreditsPageClient />;
}
