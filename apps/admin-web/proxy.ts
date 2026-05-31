import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";
import type { NextFetchEvent, NextRequest } from "next/server";

const isPublicRoute = createRouteMatcher(["/sign-in(.*)"]);

const clerkProxy = clerkMiddleware(async (auth, req) => {
  if (isPublicRoute(req)) return;

  const session = await auth();

  if (!session.userId) {
    const signInUrl = new URL("/sign-in", req.url);
    signInUrl.searchParams.set("redirect_url", req.url);
    return NextResponse.redirect(signInUrl);
  }

  if (session.orgId !== process.env.CLERK_ADMIN_ORG_ID) {
    return new NextResponse(
      "Access denied. Admin organisation membership required.",
      { status: 403 }
    );
  }
});

export function proxy(req: NextRequest, event: NextFetchEvent) {
  return clerkProxy(req, event);
}

export const config = { matcher: ["/((?!_next|.*\\..*).*)"] };
