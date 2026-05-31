import { describe, it, expect, vi } from "vitest";
import { NextRequest } from "next/server";

// We can't easily test Clerk middleware integration without mocking the full
// Clerk SDK. Instead, we validate the route matcher configuration.

describe("middleware configuration", () => {
  it("middleware file exports config with correct matcher", async () => {
    // The middleware module uses Clerk which needs env vars at import time.
    // We test the config export by dynamically importing and checking.
    vi.mock("@clerk/nextjs/server", () => ({
      clerkMiddleware: vi.fn((handler) => handler),
      createRouteMatcher: vi.fn((patterns: string[]) => {
        return (req: NextRequest) => {
          return patterns.some((p) => {
            const regex = new RegExp(p.replace("(.*)", "(.*)"));
            return regex.test(req.nextUrl.pathname);
          });
        };
      }),
    }));

    const mod = await import("@/proxy");

    // Check exported config
    expect(mod.config).toBeDefined();
    expect(mod.config.matcher).toEqual(["/((?!_next|.*\\..*).*)"]); 
  });
});
