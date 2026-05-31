import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import type { NextFetchEvent, NextRequest } from "next/server";

const isProtectedRoute = createRouteMatcher([
  "/profile(.*)",
]);

const clerkProxy = clerkMiddleware(async (auth, req) => {
  if (isProtectedRoute(req)) {
    await auth.protect();
  }
});

export function proxy(req: NextRequest, event: NextFetchEvent) {
  return clerkProxy(req, event);
}

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)"],
};
