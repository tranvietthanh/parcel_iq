import { describe, it, expect, vi } from "vitest";

// Mock loadStripe
vi.mock("@stripe/stripe-js", () => ({
  loadStripe: vi.fn(() => Promise.resolve({ fake: "stripe" })),
}));

import { getStripe } from "@/lib/stripe";
import { loadStripe } from "@stripe/stripe-js";

describe("stripe lib", () => {
  it("returns a stripe promise", async () => {
    const stripe = await getStripe();
    expect(stripe).toEqual({ fake: "stripe" });
  });

  it("caches the stripe instance (only calls loadStripe once)", async () => {
    await getStripe();
    await getStripe();
    // loadStripe was already called once in the previous test and cached
    expect(loadStripe).toHaveBeenCalledTimes(1);
  });
});
